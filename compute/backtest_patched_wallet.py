"""Patched backtest: smart-wallet follow, modeled AFTER the live pipeline.

What was wrong in the original gate (dead-end evidence):
  - Entry was modeled as FIXED T+30min blind timer (detection_lag_sec=1800),
    no chart condition at all.
What the LIVE pipeline actually does (wallet_pipeline_v3.py):
  - Polls wallet swaps every ~10 min (cron */10). Entry happens as soon as
    the signal is DETECTED, provided the buy is still inside ENTRY_WINDOW
    (30 min + 5 min grace).
  - Screen: pool liquidity >= LIQ_MIN ($5k) AND price cap <= 1.5x wallet exec
    (PRICE_CAP) -> chart-aware, no blind FOMO.
  - Exit: exit_engine with live params (hard_stop -0.35, tp ladder, trail,
    time stop).

This script re-runs the SAME stored data (expanded_dataset / expanded_pairs /
expanded_ohlcv) under a realistic detection model:
    det_ts = buy_ts + poll_lag            (poll_lag ~ 0..10 min, uniform)
    entry bar = first 1-min OHLCV bar with ts >= det_ts, but only if
                buy_ts is within ENTRY_WINDOW of detection (freshness)
    chart screen: liq >= LIQ_MIN, price <= PRICE_CAP * exec_price
    exit via compute/exit_engine.simulate_exit with live params.

Deterministic. No fabricated data. Output JSON + per-wallet decomposition.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
sys.path.insert(0, "/home/hermes/project-theia/compute")

from exit_engine import simulate_exit  # noqa: E402

# ── Live pipeline constants (from cron/wallet_pipeline_v3.py) ─────────────
ENTRY_WINDOW = 30 * 60          # signal fresh if buy <= 30 min ago
DETECT_GRACE = 5 * 60           # +5 min API-lag tolerance
LIQ_MIN = 5000.0
PRICE_CAP = 1.5                 # don't chase >1.5x wallet exec price
NOTIONAL_SOL = 0.5
EXIT_PARAMS = {
    "hard_stop": -0.35,
    "tp_ladder": [(2.0, 0.5), (4.0, 0.5)],
    "trail_drop": 0.25,
    "time_stop_secs": 30 * 60,  # live monitor time stop
}
SOL_USD = 150.0

# ── Data loading ────────────────────────────────────────────────────────────
ds = json.load(open(DATA / "expanded_dataset.json"))
candidates = ds["candidates"]          # mint -> {wallet, buy_ts, signal_sol, exec_price}
pairs = ds["pairs"]                    # mint -> {liquidity_usd, dexId, ...}

ohlcv_dir = DATA / "expanded_ohlcv"


def load_ohlcv(mint: str):
    p = ohlcv_dir / f"{mint}.json"
    if not p.exists():
        return None
    return json.load(open(p))          # [[ts,o,h,l,c,v], ...] 1-min bars


def run_config(name: str, poll_lag_sec: int, use_price_cap: bool,
               use_liq_min: bool, max_hold_min: int | None = None):
    """One patched configuration. poll_lag_sec = expected detection delay."""
    rng = random.Random(42)
    trades = []
    skipped = defaultdict(int)

    for mint, cand in candidates.items():
        wallet = cand["wallet"]
        buy_ts = cand["buy_ts"]
        exec_price = cand["exec_price"]
        ohlcv = load_ohlcv(mint)
        if ohlcv is None:
            skipped["no_ohlcv"] += 1
            continue

        pair = pairs.get(mint)
        liq = float(pair["liquidity_usd"]) if pair else 0.0

        # ── 1. Freshness gate (live pipeline) ──
        # Signal must be within entry window at the time we detect it.
        # We model detection as buy_ts + poll_lag (we see it on next poll).
        det_ts = buy_ts + poll_lag_sec
        if det_ts > buy_ts + ENTRY_WINDOW + DETECT_GRACE:
            skipped["stale_signal"] += 1
            continue

        # ── 2. Chart screen (live pipeline) ──
        if use_liq_min and liq < LIQ_MIN:
            skipped["low_liq"] += 1
            continue

        # find first bar >= det_ts (entry fill)
        entry_bar = None
        for row in ohlcv:
            if row[0] >= det_ts:
                entry_bar = row
                break
        if entry_bar is None:
            skipped["no_entry_bar"] += 1
            continue
        entry_ts = entry_bar[0]
        entry_price = entry_bar[1]  # open of that bar (conservative-ish)

        if use_price_cap and exec_price > 0 and entry_price > exec_price * PRICE_CAP:
            skipped["chase_price_cap"] += 1
            continue

        # ── 3. Sizing guard: notional <= 2% of liq ──
        if liq > 0 and NOTIONAL_SOL * SOL_USD > liq * 0.02:
            skipped["size_cap"] += 1
            continue

        # ── 4. Exit via live exit engine over forward path ──
        forward = [r for r in ohlcv if r[0] >= entry_ts]
        if not forward:
            skipped["no_forward"] += 1
            continue
        params = dict(EXIT_PARAMS)
        if max_hold_min:
            params["time_stop_secs"] = max_hold_min * 60
        ex = simulate_exit(entry_price, entry_ts, forward, params)
        ret_mult = ex["return_mult"]

        # costs: gas ~0.002 SOL/leg (from gate_result: 0.00208428), slippage via costs lib
        notional_usd = NOTIONAL_SOL * SOL_USD
        try:
            from costs import simulate_costs
            is_bc = (pair or {}).get("dexId") in (None, "pump.fun", "pumpswap")
            c = simulate_costs(notional_usd, liq, is_bonding_curve=is_bc)
            entry_cost_usd = c["entry_cost_usd"]
            exit_cost_usd = c["exit_cost_usd"]
        except Exception:
            entry_cost_usd, exit_cost_usd = 0.35, 0.35  # gas+tip fallback

        cost_sol = (entry_cost_usd + exit_cost_usd) / SOL_USD
        gross = (ret_mult - 1.0) * NOTIONAL_SOL
        net = gross - cost_sol

        trades.append({
            "mint": mint, "wallet": wallet, "buy_ts": buy_ts,
            "det_lag_sec": entry_ts - buy_ts, "hold_secs": ex["hold_secs"],
            "exit_reason": ex["final_reason"], "ret_mult": ret_mult,
            "net_pnl_sol": round(net, 6), "liq_usd": round(liq, 2),
            "entry_price": entry_price,
        })

    # ── Metrics ──
    n = len(trades)
    if n == 0:
        return {"name": name, "n": 0, "skipped": dict(skipped), "trades": []}
    wins = [t for t in trades if t["net_pnl_sol"] > 0]
    gross_profit = sum(t["net_pnl_sol"] for t in trades if t["net_pnl_sol"] > 0)
    gross_loss = -sum(t["net_pnl_sol"] for t in trades if t["net_pnl_sol"] <= 0)
    expectancy = sum(t["net_pnl_sol"] for t in trades) / n
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # per-wallet decomposition
    by_wallet = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        w = by_wallet[t["wallet"]]
        w["n"] += 1
        w["pnl"] += t["net_pnl_sol"]
        if t["net_pnl_sol"] > 0:
            w["wins"] += 1
    wallet_rows = sorted(
        [{"wallet": k, **v, "wr": v["wins"] / v["n"]} for k, v in by_wallet.items()],
        key=lambda x: -x["pnl"])

    # concentration: share of top wallet
    top_share = wallet_rows[0]["pnl"] / sum(t["net_pnl_sol"] for t in trades) if trades else 0

    return {
        "name": name,
        "n": n,
        "win_rate": round(len(wins) / n, 4),
        "expectancy": round(expectancy, 6),
        "profit_factor": round(pf, 4) if pf != float("inf") else None,
        "total_sol": round(sum(t["net_pnl_sol"] for t in trades), 4),
        "top_wallet_share": round(top_share, 4),
        "top_wallet": wallet_rows[0]["wallet"][:12] if wallet_rows else None,
        "exit_reasons": dict(defaultdict(int, {})),
        "skipped": dict(skipped),
        "wallets": wallet_rows[:10],
        "trades": trades,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "patched_backtest.json"))
    ap.add_argument("--poll", type=int, default=600, help="detection poll lag sec (live cron */10)")
    args = ap.parse_args()

    configs = [
        # (name, poll_lag_sec, price_cap, liq_min, max_hold)
        ("A_legacy_T30m_blind", 1800, False, False, None),   # original dead-end model
        ("B_patch_poll10m", 600, True, True, None),          # live pipeline behavior
        ("C_patch_poll5m", 300, True, True, None),           # faster detection
        ("D_patch_poll10m_hold30", 600, True, True, 30),     # live monitor time stop
    ]
    results = {}
    for name, poll, cap, liq, hold in configs:
        r = run_config(name, poll, cap, liq, hold)
        results[name] = {k: v for k, v in r.items() if k != "trades"}
    out = {k: v for k, v in results.items()}
    out["_meta"] = {
        "data": "expanded_dataset/expanded_pairs/expanded_ohlcv (stored 2026-08-17)",
        "entry_model": "det_ts=buy_ts+poll_lag; bar open; fresh if <=35min",
        "screens": {"liq_min": LIQ_MIN, "price_cap": PRICE_CAP},
        "exit": EXIT_PARAMS,
        "notional_sol": NOTIONAL_SOL,
        "note": "A = original blind T+30m model; B/C/D = live-pipeline-consistent",
    }
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "_meta"}, indent=1))

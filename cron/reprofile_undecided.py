#!/usr/bin/env python3
"""Re-profile discovery wallets whose sims all failed (train=0/test=0).

The 10s OHLCV timeout used to kill the sim before it ran (see 2026-08-26
analysis: 40/46 rejects were test_n<3, mostly Gecko timeout, not a failed
test). This script:

  1. Reads the discovery_swaps.json cache (already-fetched Helius swaps).
  2. Re-runs the same latency-tolerance profile as profile_discovered.py,
     but with the NEW wallet_common (60s timeout + gecko_ohlcv_for retries)
     and per-mint pool memo + parallel fetch/compute (OHLCV window per buy).
  3. Only wallets that are NOT already smart money are re-evaluated —
     a wallet that already cleared the OOS gate keeps its status.

Usage: python reprofile_undecided.py [--limit N] [--wallet WALLET ...]
0 LLM. Deterministic compute only.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
sys.path.insert(0, str(DEPLOY / "common"))
sys.path.insert(0, "/home/hermes/project-theia")

from compute.wallet_profiler import profile_wallet  # noqa: E402
from compute import costs, expectancy, gas_sim  # noqa: E402


def _load_wallet_common():
    for p in (Path(__file__).resolve().parent / "wallet_common.py",
              Path("/home/hermes/project-theia/cron/wallet_common.py"),
              Path("/home/hermes/theia-gate/wallet_common.py")):
        if p.exists():
            spec = importlib.util.spec_from_file_location("wallet_common", p)
            if spec is None or spec.loader is None:
                continue
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("wallet_common.py not found")


wc = _load_wallet_common()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


chainrpc = load("chainrpc", DEPLOY / "theia-chainrpc" / "server.py")
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

RECENT_DAYS = 14
MIN_TEST_N = 5
MAX_SIMS_PER_SPLIT = 8
NOTIONAL = 0.5
# full-history fetch: 14-day window, up to 100 pages (10k txs) — fixes the
# shallow-cache bias (pages=1/5 missed most buys/sells of active wallets).
FETCH_MAX_AGE_S = 14 * 86400
FETCH_PAGES = 100

ap = argparse.ArgumentParser()
ap.add_argument("--wallet", action="append", default=[])
ap.add_argument("--limit", type=int, default=10, help="max wallets to process (default 10)")
ap.add_argument("--refresh", action="store_true",
                help="re-fetch full 14d swap history for all cached wallets first "
                     "(default: reuse discovery_swaps.json as-is)")
args = ap.parse_args()

con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
now = int(time.time())

cache_path = DATA / "discovery_swaps.json"
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

# ── REFRESH FULL-HISTORY SWAPS (14-day window) ─────────────────────────────
# Old shallow caches (pages=1/5) miss most of an active wallet's history and
# bias win_rate. Fetch full 14d for every candidate here, then cache to disk
# so the latency sim below uses complete data.
_full = {}
if args.refresh:
    cands = list(cache.keys())
    print(f"[reprofile] refreshing full 14d swaps for {len(cands)} cached wallets...")
    for i, w in enumerate(cands):
        try:
            txs = chainrpc.wallet_swaps(w, pages=FETCH_PAGES, max_age_s=FETCH_MAX_AGE_S)
            _full[w] = txs
            buys = sum(1 for t in txs if t.get("side") == "buy")
            sells = sum(1 for t in txs if t.get("side") == "sell")
            print(f"  [{i+1}/{len(cands)}] {w[:12]} n={len(txs)} buy={buys} sell={sells}")
        except Exception as e:
            print(f"  [{i+1}/{len(cands)}] {w[:12]} ERR {e}")
    cache = _full
    cache_path.write_text(json.dumps(cache))

stored = {w: is_sm for w, is_sm in
          con.execute("SELECT wallet, is_smart_money FROM wallet_profiles").fetchall()}

# Candidates: swaps cache with >=20 txs, NOT already smart money, AND with
# SOL buys inside RECENT_DAYS (buys outside the window are filtered out later,
# so such wallets would just produce train=0/test=0 again — pointless).
cand_ids = set(args.wallet) or set(cache.keys())
todo = []
for w in sorted(cand_ids):
    txs = cache.get(w) or []
    if len(txs) < 20:
        continue
    if stored.get(w) == 1:
        print(f"  skip {w[:12]} (already smart money)")
        continue
    recent_buys = [t for t in txs if t.get("side") == "buy"
                   and t.get("quote_mint") == "So11111111111111111111111111111111111111112"
                   and t.get("ts", 0) >= now - RECENT_DAYS * 86400]
    if len(recent_buys) < 4:
        print(f"  skip {w[:12]} (only {len(recent_buys)} SOL buys in {RECENT_DAYS}d window)")
        continue
    todo.append(w)
if args.limit:
    todo = todo[: args.limit]

print(f"[reprofile] candidates={len(cand_ids)} to_process={len(todo)}")
if not todo:
    print("[reprofile] nothing to do")
    sys.exit(0)

SOL_USD = json.loads((DATA / "sol_usd.json").read_text())["sol_usd"]
# round-trip cost model (SOL) applied to every profile PnL — gas entry+exit +
# dex fees; slippage is per-trade (bonding/AMM) so applied in _compute only.
RT_COST_SOL = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol()
results = []
for w in todo:
    txs = sorted(cache[w], key=lambda x: x.get("ts", 0))
    p = profile_wallet(w, txs, costs_per_rt=RT_COST_SOL, max_buy_ratio=0.85)

    buys = [t for t in txs if t.get("side") == "buy"
            and t.get("quote_mint") == "So11111111111111111111111111111111111111112"
            and t.get("ts", 0) >= now - RECENT_DAYS * 86400]
    buys = sorted(buys, key=lambda x: x.get("ts", 0))
    split = len(buys) // 2
    train_buys, test_buys = buys[:split], buys[split:]
    train_buys = train_buys[-MAX_SIMS_PER_SPLIT:]
    test_buys = test_buys[-MAX_SIMS_PER_SPLIT:]

    def _get_pool(mint: str):
        try:
            info = wc.resolve_pool(dexdata, mint)
            if not info or info.get("liq_usd", 0) < 5000:
                return mint, None
            return mint, info
        except Exception as e:
            print(f"    {w[:8]}/{mint[:8]} err: {e}")
            return mint, None

    mints = sorted({b.get("base_mint") for b in train_buys + test_buys if b.get("base_mint")})
    pool_info = {}
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for mint, info in ex.map(_get_pool, mints):
            pool_info[mint] = info

    def _fetch(b):
        mint = b.get("base_mint")
        info = pool_info.get(mint)
        if not info:
            return b, None
        try:
            rows = wc.gecko_ohlcv_for(dexdata, mint, before_ts=b["ts"] + 4 * 3600, ttl=86400)
            if not rows or len(rows) < 35:
                return b, None
            return b, (info, rows)
        except Exception as e:
            print(f"    {w[:8]}/{mint[:8]} err: {e}")
            return b, None

    def _compute(b_rows):
        b, got = b_rows
        if not got:
            return None
        info, rows = got
        try:
            liq = info["liq_usd"]
            entry_ts_target = b["ts"] + 1800
            ce = next((r for r in rows if r[0] >= entry_ts_target), None)
            if not ce or ce[4] <= 0:
                return None
            entry_price, entry_ts = ce[4], ce[0]
            fwd = [r for r in rows if r[0] > entry_ts]
            if not fwd:
                return None
            ei = min(30, len(fwd) - 1)
            exit_price = fwd[ei][4]
            if exit_price <= 0:
                return None
            is_bonding = "pump" in (info.get("dex_id") or "").lower()
            # costs: gas entry+exit, slippage both directions (bonding cap 50%)
            slip_e = costs.slippage_estimate(NOTIONAL * SOL_USD, max(liq, 100), is_bonding)
            slip_x = costs.slippage_estimate(NOTIONAL * SOL_USD, max(liq * 0.7, 100), is_bonding)
            cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * (slip_e + slip_x)
            return (NOTIONAL / entry_price) * exit_price - NOTIONAL - cost
        except Exception as e:
            print(f"    {w[:8]}/{mint[:8]} err: {e}")
            return None

    all_buys = train_buys + test_buys
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        fetched = list(ex.map(_fetch, all_buys))
    train_pnls = [x for x in (_compute(p) for p in fetched[:len(train_buys)]) if x is not None]
    test_pnls = [x for x in (_compute(p) for p in fetched[len(train_buys):]) if x is not None]

    lt = {}
    if len(test_pnls) >= 3:
        m = expectancy.evaluate(test_pnls)
        lt = {"n": m["n"], "win_rate": m["win_rate"], "expectancy": m["expectancy"],
              "profit_factor": m["profit_factor"] if m["profit_factor"] != float("inf") else 999.0,
              "train_n": len(train_pnls), "test_n": len(test_pnls)}

    results.append({"wallet": w, "profile": p, "latency_test": lt})
    # gate: latency OOS positive AND not buy-heavy-biased (biased win_rate
    # would otherwise fake a pass from mostly-open buys)
    is_sm = 1 if (lt and lt.get("expectancy", 0) > 0 and lt.get("n", 0) >= MIN_TEST_N
                  and not p.get("biased_buy_heavy")) else 0
    marker = "★ LATENCY-TOLERANT" if is_sm else ("(biased-buy)" if p.get("biased_buy_heavy") else "")
    print(f"  {w[:12]}: profile_exp={(p.get('expectancy_sol') or 0):+.3f} "
          f"train_n={lt.get('train_n',0)} test_n={lt.get('n',0)} "
          f"test_exp={lt.get('expectancy',0):+.4f} {marker}")

    con.execute("""INSERT INTO wallet_profiles
        (wallet, first_seen_ts, last_active_ts, total_trades, total_buys, total_sells,
         unique_tokens, median_buy_sol, mean_buy_sol, median_hold_min, median_pnl_pct,
         win_rate, profit_factor, expectancy_sol, pattern_cluster, is_smart_money, source,
         created_ts, updated_ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (w, p.get("first_seen_ts"), p.get("last_active_ts"), p.get("total_trades", 0),
         p.get("total_buys", 0), p.get("total_sells", 0), p.get("unique_tokens", 0),
         p.get("median_buy_sol"), p.get("mean_buy_sol"), p.get("median_hold_min"),
         p.get("median_pnl_pct"), p.get("win_rate"),
         (p.get("profit_factor") or 0) if p.get("profit_factor") != float("inf") else 999.0,
         p.get("expectancy_sol"), p.get("pattern_cluster", "unknown"),
         is_sm, "gmgn_winrate_reprofile", now, now))
    con.commit()

(DATA / "reprofile_results.json").write_text(json.dumps(results, indent=1, default=str))
con.close()
n_lt = sum(1 for r in results if r["latency_test"] and r["latency_test"].get("expectancy", 0) > 0)
print(f"\n[done] reprofiled={len(results)}, latency-tolerant={n_lt}")
print("saved → data/reprofile_results.json")

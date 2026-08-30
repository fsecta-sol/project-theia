"""Anti-Falling-Knife re-backtest for the wallet-follow hypothesis.

Re-implements the wallet-pipeline latency-tolerance sim (profile_discovered._compute)
but adds an ENTRY-SIDE chart condition: at the T+30m entry point, skip the trade if
price has already fallen X% or more below its post-launch peak (falling knife).

This directly tests the claim that the current live pipeline enters "blind" at
T+30m regardless of price structure, and whether an anti-falling-knife screen
improves expectancy vs the blind baseline.

Design (deterministic, point-in-time, API-free on cached data):
  - Inputs: SOL buys of a wallet (wallet, ts, base_mint, exec_price), cached OHLCV
    rows [[ts,o,h,l,c,v]...] per mint (gecko/birdeye/dex), cached pool info.
  - Sim: entry at first candle >= buy_ts + 1800 (T+30m), exit at candle index +30
    (30m hold, matching profile_discovered), costs identical to the pipeline
    (gas first_buy + gas + slippage estimate).
  - AFK filter: at entry candle, compute running peak of candle highs from the
    earliest candle in the fetched window up to entry. Skip trade if
    entry_close < (1 - X) * peak_high, for X in sweep list (default 0.30, 0.50, 0.70).
  - Output: per-threshold expectancy metrics (expectancy.evaluate) vs baseline
    (no filter), n retained, and the blind-baseline numbers for comparison.

Usage (from project root):
    from compute.afk_backtest import run_afk_backtest, load_dataset
    ds = load_dataset()                 # builds from discovery_swaps.json + caches
    res = run_afk_backtest(ds, sweep=[0.30, 0.50, 0.70])
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from compute import costs, expectancy, gas_sim

WSOL = "So11111111111111111111111111111111111111112"
NOTIONAL = 0.5  # SOL per paper trade (matches pipeline)
ENTRY_LAG = 1800  # T+30m
HOLD_CANDLES = 30  # exit at +30 candles (~30m hold)

# path resolution helpers (mirror the pipeline's own)
DATA = Path("/home/hermes/theia-gate/data")
SWAPS_CACHE = DATA / "discovery_swaps.json"
OHLCV_CACHE = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
POOLS_CACHE = Path.home() / ".hermes/theia/wallet_cache/pools"
DB = Path.home() / ".hermes/theia/theia.db"


def load_ohlcv_rows(mint: str) -> list:
    """Return the DEEPEST cached OHLCV for mint across all cache files (any source).

    Cache filenames embed the mint + a day/now suffix; gecko keys are
    'gecko_<mint>_<day>', birdeye 'bird_<mint>_<hour>_<hours>h', dex 'dex_...'.
    We take the file with the most rows and load its rows (files store the raw
    rows list directly, or a {'rows': [...]} dict).
    """
    best = []
    if not OHLCV_CACHE.exists():
        return best
    for f in OHLCV_CACHE.iterdir():
        if mint not in f.name:
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        rows = data.get("rows", data) if isinstance(data, dict) else data
        if isinstance(rows, list) and len(rows) > len(best):
            best = rows
    return best


def load_pool_info(mint: str) -> dict | None:
    pf = POOLS_CACHE / f"{mint}.json"
    if pf.exists():
        try:
            return json.loads(pf.read_text())
        except Exception:
            return None
    return None


def load_dataset(only_smart: bool = True, min_cached_candles: int = 35) -> dict:
    """Build the dataset: buys (wallet, ts, mint, exec_price) + cached OHLCV + pool.

    only_smart=True restricts to wallets currently marked is_smart_money=1 in
    wallet_profiles (the wallets the live pipeline actually follows).
    """
    con = sqlite3.connect(DB)
    tracked = {r[0] for r in con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1")} if only_smart else None
    con.close()

    swaps = json.loads(SWAPS_CACHE.read_text())
    by_mint: dict[str, list] = defaultdict(list)
    for w, txs in swaps.items():
        if not isinstance(txs, list):
            continue
        if tracked is not None and w not in tracked:
            continue
        for t in txs:
            if t.get("side") == "buy" and t.get("quote_mint") == WSOL and t.get("base_mint"):
                by_mint[t["base_mint"]].append({
                    "wallet": w, "ts": int(t["ts"]), "exec_price": float(t.get("exec_price") or 0),
                })

    rows_by_mint, pool_by_mint, dropped = {}, {}, 0
    for mint, bl in by_mint.items():
        rows = load_ohlcv_rows(mint)
        if len(rows) < min_cached_candles:
            dropped += 1
            continue
        rows_by_mint[mint] = rows
        pool_by_mint[mint] = load_pool_info(mint)

    return {
        "buys_by_mint": dict(by_mint),
        "rows_by_mint": rows_by_mint,
        "pool_by_mint": pool_by_mint,
        "dropped_no_cache": dropped,
        "mints_total": len(by_mint),
        "mints_usable": len(rows_by_mint),
    }


def _sim_trade(buy_ts: int, rows: list, pool: dict | None,
               usd: float) -> dict | None:
    """Mirror profile_discovered._compute: entry at T+30m, 30-candle hold, net cost.

    Returns dict with entry_ts, entry_price, exit_price, peak_high (running peak
    of highs from window start through entry), pnl_net, or None if unusable.
    """
    if not pool or not rows:
        return None
    liq = pool.get("liq_usd") or 0
    if liq <= 0:
        return None
    entry_target = buy_ts + ENTRY_LAG
    ce = next((r for r in rows if r[0] >= entry_target), None)
    if not ce or ce[4] <= 0:
        return None
    entry_ts, entry_price = ce[0], ce[4]
    fwd = [r for r in rows if r[0] > entry_ts]
    if not fwd:
        return None
    ei = min(HOLD_CANDLES, len(fwd) - 1)
    exit_price = fwd[ei][4]
    if exit_price <= 0:
        return None
    # running peak of highs from window start to entry (inclusive of entry candle)
    peak_high = max((r[2] for r in rows if r[0] <= entry_ts), default=entry_price)
    is_bonding = "pump" in (pool.get("dex_id") or "").lower()
    slip = (costs.slippage_estimate(NOTIONAL * usd, max(liq, 100), is_bonding) +
            costs.slippage_estimate(NOTIONAL * usd, max(liq * 0.7, 100), is_bonding))
    cost = (gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() +
            NOTIONAL * slip)
    pnl_net = (NOTIONAL / entry_price) * exit_price - NOTIONAL - cost
    return {
        "entry_ts": entry_ts, "entry_price": entry_price, "exit_price": exit_price,
        "peak_high": peak_high, "pnl_net": pnl_net,
    }


def run_afk_backtest(ds: dict, sweep: list[float] | None = None,
                     usd: float = 75.45) -> dict:
    """Run baseline + AFK-sweep over the dataset. Returns per-threshold metrics."""
    sweep = sweep if sweep is not None else [0.30, 0.50, 0.70]
    rows_by_mint, pool_by_mint = ds["rows_by_mint"], ds["pool_by_mint"]

    # one sim per (mint, wallet) buy — the pipeline can open one trade per signal
    sims: list[dict] = []
    for mint, buys in ds["buys_by_mint"].items():
        rows = rows_by_mint.get(mint)
        if not rows:
            continue
        pool = pool_by_mint.get(mint)
        for b in buys:
            s = _sim_trade(b["ts"], rows, pool, usd)
            if s is not None:
                s["mint"] = mint
                s["wallet"] = b["wallet"]
                s["buy_ts"] = b["ts"]
                sims.append(s)

    # guard against a single wallet dominating the sample (postmortem lesson)
    from collections import Counter
    wcount = Counter(s["wallet"] for s in sims)
    dominant = wcount.most_common(1)[0] if wcount else ("", 0)

    def _pnls(slice_sims):
        return [s["pnl_net"] for s in slice_sims]

    def _entry_sim(s):
        # fraction below peak at entry: 1 - entry/peak
        return 1.0 - (s["entry_price"] / s["peak_high"]) if s["peak_high"] > 0 else 0.0

    baseline = expectancy.evaluate(_pnls(sims))
    out = {
        "baseline": baseline,
        "baseline_n": len(sims),
        "dominant_wallet": dominant[0][:12] if dominant[0] else "",
        "dominant_pct": round(dominant[1] / max(len(sims), 1), 4),
        "sweep": {},
        "dataset": {"mints_total": ds["mints_total"], "mints_usable": ds["mints_usable"],
                    "dropped_no_cache": ds["dropped_no_cache"]},
    }
    for x in sweep:
        kept = [s for s in sims if _entry_sim(s) <= x]
        out["sweep"][f"afk_{int(x*100)}"] = {
            "metrics": expectancy.evaluate(_pnls(kept)),
            "n": len(kept),
            "n_skipped": len(sims) - len(kept),
            "avg_drawdown_from_peak": round(sum(_entry_sim(s) for s in kept) / max(len(kept), 1), 4),
        }
    return out


def load_top10_map() -> dict[str, float]:
    """Load mint -> top10_share from early_holders summary rows (source goplus_top10).

    Returns {} if the snapshot hasn't run yet.
    """
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT mint, pct_of_supply FROM early_holders "
        "WHERE wallet='__TOP10__' AND source='goplus_top10'").fetchall()
    con.close()
    return {m: float(p or 0) for m, p in rows}


def run_holder_backtest(ds: dict, top10_caps: list[float] | None = None,
                        usd: float = 75.45) -> dict:
    """Baseline + top10-holder-concentration filter sweep.

    Tests the user's signal: skip tokens whose top-10 holders hold > cap fraction
    of supply (concentration = who can control price). Uses early_holders top10
    data; mints without a snapshot are EXCLUDED (kept honest — no assumption).
    """
    caps = top10_caps if top10_caps is not None else [0.30, 0.50, 0.70]
    top10 = load_top10_map()
    rows_by_mint, pool_by_mint = ds["rows_by_mint"], ds["pool_by_mint"]

    sims: list[dict] = []
    for mint, buys in ds["buys_by_mint"].items():
        rows = rows_by_mint.get(mint)
        if not rows:
            continue
        pool = pool_by_mint.get(mint)
        t10 = top10.get(mint)
        for b in buys:
            s = _sim_trade(b["ts"], rows, pool, usd)
            if s is None:
                continue
            s["mint"] = mint
            s["wallet"] = b["wallet"]
            s["buy_ts"] = b["ts"]
            s["top10"] = t10
            sims.append(s)

    # only mints with holder data are evaluable
    with_holder = [s for s in sims if s["top10"] is not None]
    baseline = expectancy.evaluate([s["pnl_net"] for s in with_holder])
    out = {
        "baseline": baseline,
        "baseline_n": len(with_holder),
        "mints_with_holder_data": len({s["mint"] for s in with_holder}),
        "total_sims": len(sims),
        "top10_map_size": len(top10),
        "sweep": {},
    }
    for cap in caps:
        kept = [s for s in with_holder if s["top10"] <= cap]
        out["sweep"][f"top10_le_{int(cap*100)}"] = {
            "metrics": expectancy.evaluate([s["pnl_net"] for s in kept]),
            "n": len(kept),
            "n_skipped": len(with_holder) - len(kept),
            "avg_top10": round(sum(s["top10"] for s in kept) / max(len(kept), 1), 4),
        }
    return out


def run_peakprox_backtest(ds: dict, max_dd_from_peak: list[float] | None = None,
                          usd: float = 75.45) -> dict:
    """Entry only when price is within X drawdown of its recent peak (momentum intact).

    The bucket analysis showed the ONLY positive-expectancy bucket is 0-10%
    drawdown at entry (exp +0.0194, PF 1.80). This variant tests that as an
    explicit entry rule: skip trades where entry_close < (1 - max_dd) * peak_high.
    """
    caps = max_dd_from_peak if max_dd_from_peak is not None else [0.10, 0.20, 0.30]
    rows_by_mint, pool_by_mint = ds["rows_by_mint"], ds["pool_by_mint"]

    sims: list[dict] = []
    for mint, buys in ds["buys_by_mint"].items():
        rows = rows_by_mint.get(mint)
        if not rows:
            continue
        pool = pool_by_mint.get(mint)
        for b in buys:
            s = _sim_trade(b["ts"], rows, pool, usd)
            if s is None:
                continue
            s["mint"] = mint
            s["wallet"] = b["wallet"]
            s["buy_ts"] = b["ts"]
            s["dd"] = 1.0 - (s["entry_price"] / s["peak_high"]) if s["peak_high"] > 0 else 0.0
            sims.append(s)

    baseline = expectancy.evaluate([s["pnl_net"] for s in sims])
    out = {
        "baseline": baseline,
        "baseline_n": len(sims),
        "sweep": {},
    }
    for cap in caps:
        kept = [s for s in sims if s["dd"] <= cap]
        out["sweep"][f"dd_le_{int(cap*100)}"] = {
            "metrics": expectancy.evaluate([s["pnl_net"] for s in kept]),
            "n": len(kept),
            "n_skipped": len(sims) - len(kept),
        }
    return out


def run_oos_holdout(ds: dict, rules: dict, split_frac: float = 0.7,
                    usd: float = 75.45) -> dict:
    """Time-based OOS hold-out: design rules on TRAIN window, test on TEST window.

    Splits buys by timestamp (not random — point-in-time honest). Rules dict:
        {"peakprox_10": {"dd_max": 0.10}, "holder_90": {"top10_max": 0.90}}
    Returns per-rule train/test expectancy metrics + per-wallet decompose in
    the test window, so a rule that is a single-wallet artifact gets exposed.
    """
    from compute.afk_backtest import load_top10_map
    top10 = load_top10_map()
    rows_by_mint, pool_by_mint = ds["rows_by_mint"], ds["pool_by_mint"]

    # gather all (buy_ts, wallet, mint, sim) tuples
    all_events = []
    for mint, buys in ds["buys_by_mint"].items():
        rows = rows_by_mint.get(mint)
        if not rows:
            continue
        pool = pool_by_mint.get(mint)
        for b in buys:
            s = _sim_trade(b["ts"], rows, pool, usd)
            if s is None:
                continue
            s["mint"] = mint
            s["wallet"] = b["wallet"]
            s["buy_ts"] = b["ts"]
            dd = 1.0 - (s["entry_price"] / s["peak_high"]) if s["peak_high"] > 0 else 0
            s["dd"] = dd
            s["top10"] = top10.get(mint)
            all_events.append(s)

    # time split: sort by buy_ts, take first split_frac as train
    all_events.sort(key=lambda s: s["buy_ts"])
    n = len(all_events)
    split_at = int(n * split_frac)
    train, test = all_events[:split_at], all_events[split_at:]
    t_train_end = train[-1]["buy_ts"] if train else 0

    def _apply(rule, events):
        if "dd_max" in rule:
            return [s for s in events if s["dd"] <= rule["dd_max"]]
        if "top10_max" in rule:
            return [s for s in events if s["top10"] is not None and s["top10"] <= rule["top10_max"]]
        return events

    out = {"split": {"n_total": n, "n_train": len(train), "n_test": len(test),
                     "train_end_ts": t_train_end}, "rules": {}}
    for name, rule in rules.items():
        tr = _apply(rule, train)
        te = _apply(rule, test)
        mtr = expectancy.evaluate([s["pnl_net"] for s in tr])
        mte = expectancy.evaluate([s["pnl_net"] for s in te])
        # per-wallet decompose in TEST
        per_wallet = defaultdict(list)
        for s in te:
            per_wallet[s["wallet"]].append(s["pnl_net"])
        pw = {}
        for w, pnls in sorted(per_wallet.items(), key=lambda kv: -len(kv[1])):
            m = expectancy.evaluate(pnls)
            pw[w[:12]] = {"n": len(pnls), "expectancy": m["expectancy"],
                          "pf": m["profit_factor"]}
        out["rules"][name] = {
            "train": {"n": len(tr), "expectancy": mtr["expectancy"],
                      "pf": mtr["profit_factor"], "wr": mtr["win_rate"]},
            "test": {"n": len(te), "expectancy": mte["expectancy"],
                     "pf": mte["profit_factor"], "wr": mte["win_rate"]},
            "test_per_wallet": pw,
        }
    return out


def fmt_oos(oos: dict) -> str:
    lines = [f"split: train n={oos['split']['n_train']} | test n={oos['split']['n_test']}"]
    for name, r in oos["rules"].items():
        tr, te = r["train"], r["test"]
        lines.append(f"\n{name}:")
        lines.append(f"  TRAIN n={tr['n']} exp={tr['expectancy']:+.4f} PF={tr['pf']:.2f} WR={tr['wr']*100:.0f}%")
        lines.append(f"  TEST  n={te['n']} exp={te['expectancy']:+.4f} PF={te['pf']:.2f} WR={te['wr']*100:.0f}%")
        pw = r["test_per_wallet"]
        if pw:
            lines.append("  TEST per-wallet:")
            for w, d in sorted(pw.items(), key=lambda kv: -kv[1]["n"]):
                lines.append(f"    {w:<14} n={d['n']:>4} exp={d['expectancy']:+.4f} PF={d['pf']:.2f}")
    return "\n".join(lines)


def fmt_result(r: dict) -> str:
    lines = [
        f"mints usable: {r['dataset']['mints_usable']}/{r['dataset']['mints_total']} "
        f"(dropped no-cache: {r['dataset']['dropped_no_cache']})",
        f"sims: {r['baseline_n']} | dominant wallet {r['dominant_wallet']} = {r['dominant_pct']*100:.0f}%",
        "",
        f"{'variant':<12} {'n':>5} {'skip':>5} {'exp':>9} {'PF':>6} {'WR':>6} {'pass':>5}",
        f"{'blind':<12} {r['baseline']['n']:>5} {'':>5} {r['baseline']['expectancy']:>9.4f} "
        f"{r['baseline']['profit_factor']:>6.2f} {r['baseline']['win_rate']*100:>5.1f}% "
        f"{str(r['baseline']['passes']):>5}",
    ]
    for k, v in r["sweep"].items():
        m = v["metrics"]
        lines.append(f"{k:<12} {v['n']:>5} {v['n_skipped']:>5} {m['expectancy']:>9.4f} "
                     f"{m['profit_factor']:>6.2f} {m['win_rate']*100:>5.1f}% {str(m['passes']):>5}")
    return "\n".join(lines)

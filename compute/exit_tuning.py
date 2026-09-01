#!/usr/bin/env python3
"""Exit-engine tuning battery (A1/A2/A3) — organic-only OHLCV, costs charged.

Question: since all killed verdicts were ENTRY rules, is the EXIT config the
untuned lever? Sweep exit params over the same entry rule (source2-style
dip-reversal, organic-only, T+30m copy window as in forward pipeline) and
measure expectancy/PF per exit config. Provenance guard: exclude `_now`
retro-fetch cache keys (2026-08-31 lesson), charge 0.00432 SOL/trade costs.

Configs to test (exit_engine DEFAULTS: hard_stop -0.35, ladder [(2,0.5),(4,0.25)],
trail 0.25, time 4h — live monitor uses time60):
  - hard_stop: -0.25 / -0.35 (live) / -0.50
  - time_stop: 60m (live) / 90m / 120m / 4h
  - tp_ladder: [(2,0.5),(4,0.25)] (live) / [(1.5,0.5),(3,0.5)] / [(3,1.0)] /
               [(2,1.0)] (all-out) / no-ladder trail-only
  - trail_drop: 0.25 (live) / 0.35 / 0.50
Entry: for each mint with >=60 candles, first entry candidate = 25-50% dip off
rolling 120-high confirmed by bull candle; fill at next open (conservative).
This mirrors the source2 chart-entry backtest but focuses on EXIT variation.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import exit_engine, expectancy, costs, gas_sim  # noqa: E402
from compute.volume_lowbuy_backtest import load_mints  # noqa: E402

TZ = timezone(timedelta(hours=7))
OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
NOTIONAL = 0.5
COST = (gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol()
        + NOTIONAL * costs.slippage_estimate(NOTIONAL * 150.0, 5000, False))


def organic_mints(min_candles=60):
    mints = load_mints(min_candles=min_candles)
    new_files = {f.stem[:-4] for f in OHLCV.iterdir()
                 if f.is_file() and f.stem.endswith("_now")}
    return {k: r for k, r in mints.items() if k not in new_files}


def entry_candidates(rows):
    """Dip-off-120-high + bull confirm; fill next open. Returns entry indices."""
    n = len(rows)
    highs = [r[2] for r in rows]
    opens = [r[1] for r in rows]
    closes = [r[4] for r in rows]
    lows = [r[3] for r in rows]
    cand = []
    i = 0
    while i < n:
        hh = max(highs[max(0, i - 120):i + 1])
        if hh <= 0 or closes[i] > 0.60 * hh:  # not dipped enough
            i += 1
            continue
        # confirm: bull candle within next 10
        found = None
        for j in range(i + 1, min(n, i + 11)):
            if opens[j] < closes[j]:
                found = j
                break
        if found is None or found + 1 >= n:
            i += 1
            continue
        k = found + 1
        if opens[k] > 0:
            cand.append(k)
            i = found + 1
        else:
            i += 1
    return cand


def run_exit_config(mints, params, label):
    trades = []
    for key, rows in mints.items():
        for k in entry_candidates(rows):
            entry_price = rows[k][1]
            path = rows[k + 1:]
            if len(path) < 5:
                continue
            res = exit_engine.simulate_exit(entry_price, rows[k][0], path, params)
            pnl = (res["return_mult"] - 1.0) * NOTIONAL - COST
            trades.append(pnl)
    m = expectancy.evaluate(trades)
    m["config"] = label
    # exit reason breakdown
    return m, trades


def main():
    mints = organic_mints(60)
    print(f"organic mints (>=60 candles): {len(mints)}")
    print(f"cost per trade: {COST:.5f} SOL\n")

    results = []

    # A1: hard_stop sweep (live ladder+trail, time 60m)
    for hs in (-0.25, -0.35, -0.50):
        params = {"hard_stop": hs, "time_stop_secs": 60 * 60}
        m, _ = run_exit_config(mints, params, f"hard_stop={hs}")
        results.append(m)
        print(f"{m['config']:<22} n={m['n']:>5} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"win={m['win_rate']:.2f}")

    # A1b: time_stop sweep (live stop -0.35, ladder+trail)
    for ts_min in (60, 90, 120, 240):
        params = {"hard_stop": -0.35, "time_stop_secs": ts_min * 60}
        m, _ = run_exit_config(mints, params, f"time_stop={ts_min}m")
        results.append(m)
        print(f"{m['config']:<22} n={m['n']:>5} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"win={m['win_rate']:.2f}")

    # A2: tp_ladder sweep
    ladder_variants = [
        ("ladder live", [(2.0, 0.5), (4.0, 0.25)]),
        ("ladder 1.5x/3x", [(1.5, 0.5), (3.0, 0.5)]),
        ("single TP 3x", [(3.0, 1.0)]),
        ("single TP 2x", [(2.0, 1.0)]),
        ("no ladder (trail-only)", []),
    ]
    for label, ladder in ladder_variants:
        params = {"hard_stop": -0.35, "time_stop_secs": 60 * 60, "tp_ladder": ladder}
        m, _ = run_exit_config(mints, params, label)
        results.append(m)
        print(f"{m['config']:<22} n={m['n']:>5} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"win={m['win_rate']:.2f}")

    # A3: trail_drop sweep
    for td in (0.25, 0.35, 0.50):
        params = {"hard_stop": -0.35, "time_stop_secs": 60 * 60, "trail_drop": td}
        m, _ = run_exit_config(mints, params, f"trail_drop={td}")
        results.append(m)
        print(f"{m['config']:<22} n={m['n']:>5} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"win={m['win_rate']:.2f}")

    results.sort(key=lambda m: -m["expectancy"])
    print("\n== TOP 5 configs ==")
    for m in results[:5]:
        print(f"  {m['config']:<24} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"n={m['n']} win={m['win_rate']:.2f}")

    Path("/home/hermes/project-theia/compute/_exit_tuning.json").write_text(
        json.dumps(results, indent=1, default=str))
    print("\nsaved _exit_tuning.json")


if __name__ == "__main__":
    main()
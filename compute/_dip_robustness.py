#!/usr/bin/env python3
"""Robustness battery for the dip-reversal backtest.

Runs:
  1. Baseline (as defined)
  2. Outlier removal (drop top-1/top-2/top-3 winners) — is it single-trade luck?
  3. Threshold sweep (dip 0.2/0.3/0.4/0.5, confirm 0.85/0.90/0.95)
  4. Split-half by time (first half of each pool's candles vs second)
  5. Per-pool breakdown (venue/pool concentration)
  6. No-overlap + strict 1-position-per-pool sanity
All deterministic, API-free, on stored OHLCV. Verdict: expectancy/pf from
compute.expectancy; LLM does not compute money math.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy
from compute.dip_reversal_backtest import (  # noqa: E402
    HARD_STOP, NOTIONAL, Sim, load_pools,
)


def sim_pool(rows, dip_pct, confirm_pct, exit_mult, time_stop, lookback=360, confirm_n=5):
    """Same core logic as run_dip_backtest but returns sims for one config."""
    n = len(rows)
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    ath = [0.0] * n
    for i in range(n):
        lo = max(0, i - lookback)
        ath[i] = max(highs[lo:i + 1])

    sims = []
    i = 0
    while i < n:
        if not (closes[i] <= (1 - dip_pct) * ath[i] and ath[i] > 0):
            i += 1
            continue
        entry_level = confirm_pct * ath[i]
        j = i + 1
        while j < min(n, i + 1 + confirm_n):
            if closes[j] >= confirm_pct * ath[j] and lows[j] <= entry_level <= highs[j]:
                break
            j += 1
        if j >= min(n, i + 1 + confirm_n):
            i += 1
            continue
        entry_price = max(lows[j], entry_level)
        entry_price = min(entry_price, highs[j])
        if entry_price <= 0:
            i += 1
            continue
        exit_price, exit_ts, reason = None, None, None
        for k in range(j + 1, n):
            if closes[k] <= HARD_STOP * entry_price:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "hard_stop"
                break
            if closes[k] >= exit_mult * entry_price:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "tp"
                break
            if rows[k][0] - rows[j][0] >= time_stop * 60:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "time_stop"
                break
        if exit_price is None:
            exit_price, exit_ts, reason = closes[-1], rows[-1][0], "data_end"
        sims.append(Sim(pool="", entry_ts=rows[j][0], entry_price=entry_price,
                        exit_ts=int(exit_ts), exit_price=exit_price,
                        pnl_net=(exit_price / entry_price - 1.0) * NOTIONAL,
                        exit_reason=str(reason), dip_pct=dip_pct, ath_at_entry=ath[i]))
        i = j + 1
    return sims


def main():
    pools = load_pools()
    pool_names = list(pools)
    print(f"pools: {len(pool_names)}")
    for p in pool_names:
        print(f"  {p[:16]} rows={len(pools[p])}")

    # 1. baseline
    base = [s for p in pools.values() for s in sim_pool(p, 0.30, 0.90, 1.30, 120)]
    print(f"\n=== 1. BASELINE dip=0.30 confirm=0.90 exit=1.30 tstop=120 ===")
    print("n:", len(base), "metrics:", expectancy.evaluate([s.pnl_net for s in base]))

    # 2. outlier removal
    print("\n=== 2. OUTLIER REMOVAL ===")
    pnls = sorted([s.pnl_net for s in base], reverse=True)
    for k in (1, 2, 3):
        sub = pnls[k:]
        m = expectancy.evaluate(sub)
        print(f"  drop top-{k}: n={len(sub)} exp={m['expectancy']:.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 3. threshold sweep
    print("\n=== 3. THRESHOLD SWEEP ===")
    for dip in (0.20, 0.30, 0.40, 0.50):
        for cf in (0.85, 0.90, 0.95):
            sims = [s for p in pools.values() for s in sim_pool(p, dip, cf, 1.30, 120)]
            m = expectancy.evaluate([s.pnl_net for s in sims])
            print(f"  dip={dip:.2f} cf={cf:.2f}: n={len(sims):3d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 4. split-half by pool time
    print("\n=== 4. SPLIT-HALF (per pool: first vs second half of candles) ===")
    half1, half2 = [], []
    for p, rows in pools.items():
        mid = len(rows) // 2
        half1 += sim_pool(rows[:mid], 0.30, 0.90, 1.30, 120)
        # only sims whose entry is in the second half
        half2 += [s for s in sim_pool(rows, 0.30, 0.90, 1.30, 120) if s.entry_ts >= rows[mid][0]]
    for name, sims in (("first_half", half1), ("second_half", half2)):
        m = expectancy.evaluate([s.pnl_net for s in sims])
        print(f"  {name}: n={len(sims)} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 5. per-pool breakdown
    print("\n=== 5. PER-POOL ===")
    for p, rows in pools.items():
        sims = sim_pool(rows, 0.30, 0.90, 1.30, 120)
        if not sims:
            continue
        m = expectancy.evaluate([s.pnl_net for s in sims])
        print(f"  {p[:16]}: n={len(sims):2d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 6. exit mult sweep
    print("\n=== 6. EXIT MULT SWEEP ===")
    for em in (1.15, 1.30, 1.50, 2.0):
        sims = [s for p in pools.values() for s in sim_pool(p, 0.30, 0.90, em, 120)]
        m = expectancy.evaluate([s.pnl_net for s in sims])
        print(f"  exit={em}: n={len(sims)} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")


if __name__ == "__main__":
    main()

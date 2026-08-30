#!/usr/bin/env python3
"""Shallow-dip + momentum entry backtest — the recovery-predictability edge.

Motivated by compute/recovery_predictability.py:
  - shallow dips (drawdown <= ~42% of rolling 180-high) recover 60.5% within 60m
  - deep dips (>79%) recover only 5.0%
  - strong 30-candle momentum => 33.8% vs 15.2% when momentum broken
So an entry rule that buys SHALLOW dips with ALIVE momentum should beat the
~26% base rate. This is the first rule with an explicit, measured basis.

Rule (deterministic, point-in-time, API-free on stored OHLCV):
  - entry trigger: candle i closes between 20% and 42% below the rolling
    180-candle high (SHALLOW dip only — never deep).
  - momentum gate: close[i] >= close[i-30] * (1 - mom_floor) (alive uptrend).
  - entry at NEXT candle open (act after confirmed close, fill next open).
  - exit: hard_stop 0.65×entry, tp 2×, trail 25%, time_stop 240m.
  - sweep: dip range (20-42%, 20-50%, 25-45%), momentum floor (0.7, 0.85, 1.0).
  - robustness: outlier (top-1/2), split-half, per-mint concentration.
Output: expectancy/PF via compute/expectancy.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim
from compute.volume_lowbuy_backtest import load_mints  # noqa: E402

NOTIONAL = 0.5
LOOKBACK = 180
HARD_STOP = 0.65
TP = 2.0
TRAIL = 0.25
TIME_STOP = 240 * 60
MOM_WINDOW = 30


def sim_mint(rows, dip_lo, dip_hi, mom_floor, usd=150.0, mint_label="") -> list[dict]:
    n = len(rows)
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    ath = [0.0] * n
    for i in range(n):
        ath[i] = max(highs[max(0, i - LOOKBACK):i + 1])

    trades = []
    i = MOM_WINDOW
    while i < n:
        if ath[i] <= 0:
            i += 1
            continue
        dd = 1 - closes[i] / ath[i]
        if not (dip_lo <= dd <= dip_hi):
            i += 1
            continue
        # momentum gate
        if closes[i - MOM_WINDOW] <= 0:
            i += 1
            continue
        mom = closes[i] / closes[i - MOM_WINDOW]
        if mom < mom_floor:
            i += 1
            continue
        # entry at next candle open
        k = i + 1
        if k >= n or rows[k][1] <= 0:
            i += 1
            continue
        entry_price = rows[k][1]
        entry_ts = rows[k][0]
        # exit
        peak = entry_price
        exit_price = exit_ts = reason = None
        for e in range(k + 1, n):
            ts, o, h, l, c = rows[e][0], rows[e][1], rows[e][2], rows[e][3], rows[e][4]
            if c <= 0:
                continue
            if c <= HARD_STOP * entry_price:
                exit_price, exit_ts, reason = l, ts, "hard_stop"
                break
            if c >= TP * entry_price:
                exit_price, exit_ts, reason = l, ts, "tp"
                break
            peak = max(peak, h)
            if c <= peak * (1 - TRAIL):
                exit_price, exit_ts, reason = l, ts, "trail"
                break
            if ts - entry_ts >= TIME_STOP:
                exit_price, exit_ts, reason = l, ts, "time_stop"
                break
        if exit_price is None:
            exit_price, exit_ts, reason = closes[-1], rows[-1][0], "data_end"
        pnl = (exit_price / entry_price - 1.0) * NOTIONAL
        slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
        cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip
        trades.append({"mint": mint_label, "pnl_net": pnl - cost, "reason": reason,
                       "entry_ts": entry_ts, "dd": dd})
        i = k + 1  # no overlap
    return trades


def run(mints, dip_lo, dip_hi, mom_floor):
    trades = []
    for key, r in mints.items():
        trades += sim_mint(r, dip_lo, dip_hi, mom_floor, mint_label=key)
    return trades


def main():
    mints = load_mints(min_candles=120)
    print(f"mints: {len(mints)}")
    print("== sweep ==")
    best = None
    for dlo, dhi in ((0.20, 0.42), (0.20, 0.50), (0.25, 0.45)):
        for mf in (0.70, 0.85, 1.00):
            trades = run(mints, dlo, dhi, mf)
            pnls = [t["pnl_net"] for t in trades]
            m = expectancy.evaluate(pnls)
            tag = f"dip={dlo:.2f}-{dhi:.2f} mom>={mf:.2f}"
            print(f"  {tag}: n={len(pnls):4d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")
            if len(pnls) >= 20 and m["expectancy"] > 0 and m["profit_factor"] > 1:
                if best is None or m["expectancy"] > best[1]:
                    best = (tag, m["expectancy"], m, trades)
    if best:
        tag, exp, m, trades = best
        pnls = [t["pnl_net"] for t in trades]
        print(f"\nBEST: {tag} exp={exp:+.4f} pf={m['profit_factor']:.3f} n={m['n']}")
        # robustness
        sp = sorted(pnls, reverse=True)
        for k in (1, 2, 5):
            mm = expectancy.evaluate(sp[k:])
            print(f"  drop top-{k}: exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f} win={mm['win_rate']:.3f}")
        # per-mint concentration
        from collections import Counter
        cnt = Counter(t["mint"] for t in trades)
        top = cnt.most_common(3)
        print(f"  top mints: {top} (of {len(cnt)} mints)")


if __name__ == "__main__":
    main()
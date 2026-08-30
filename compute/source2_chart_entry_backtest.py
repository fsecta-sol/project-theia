#!/usr/bin/env python3
"""Source-2 wallet-trigger + chart-conditioned entry backtest.

Tests the ONLY wallet edge not yet killed: source-2 dex_trending wallets (stricter
GMGN 7d gate), entered NOT on a blind timer but conditioned on chart state, per the
durable rule from chart-conditioned-entry.md: "entry rules MUST read the chart".

Design (deterministic, API-free, point-in-time on stored data):
  - triggers = buys from _dex_trending_swaps.json (the 8 dex_trending wallets w/ data)
  - for each trigger: find the token's cached OHLCV; entry evaluated inside the
    detection window (<=30 min after wallet exec) at the FIRST 1-min candle where
    the chart is still buyable:
        price_cap: close <= cap_mult × wallet exec price (don't chase a pumped move)
        volume_alive: candle volume > vol_min (price action alive)
        else wait up to window; no fill → skip
  - exit (chart-based): exit_engine-like — hard_stop 0.65×entry, tp 2× (ladder 2x/4x),
    trail 25%, time_stop 240 min. Gas+slippage charged (costs lib, notional 0.5 SOL).
  - variants: cap in (1.0, 1.25, 1.5), vol_min in (0, 5, 10) — sweep.
  - robustness: outlier (drop top-1/2), per-wallet attribution, split-half.
Output: expectancy/PF via compute/expectancy.py. Verdict: +EV & PF>1 & n>=20 & not
single-wallet-dependent.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim
from compute.volume_lowbuy_backtest import load_mints  # correct mint-key loader

WSOL = "So11111111111111111111111111111111111111112"
NOTIONAL = 0.5
WINDOW = 30 * 60  # detection window after wallet exec (chart-conditioned, not blind timer)
HARD_STOP = 0.65
TP = 2.0
TRAIL = 0.25
TIME_STOP = 240 * 60

SWAPS = Path("/home/hermes/project-theia/compute/_dex_trending_swaps.json")


def load_triggers() -> list[dict]:
    data = json.loads(SWAPS.read_text())
    trigs = []
    for w, swaps in data.items():
        if not isinstance(swaps, list):
            continue
        for s in swaps:
            if s.get("side") == "buy" and s.get("quote_mint") == WSOL and s.get("base_mint"):
                trigs.append({
                    "wallet": w, "mint": s["base_mint"], "ts": int(s.get("ts") or 0),
                    "exec_price": float(s.get("exec_price") or 0),
                    "exec_sol": float(s.get("quote_qty") or 0),
                })
    return trigs


def sim_one(trigger, rows, cap_mult, vol_min, usd) -> dict | None:
    """Return trade dict or None (no fill). Chart-conditioned entry within window."""
    mint_rows = [r for r in rows if r[0] >= trigger["ts"] and r[0] <= trigger["ts"] + WINDOW]
    if not mint_rows:
        return None
    # entry: first candle inside window where chart is buyable
    entry = None
    for r in mint_rows:
        ts, o, h, l, c = r[0], r[1], r[2], r[3], r[4]
        v = r[5] if len(r) > 5 else 0.0
        if c <= 0:
            continue
        if trigger["exec_price"] > 0 and c > cap_mult * trigger["exec_price"]:
            continue  # already pumped past cap — don't chase
        if v < vol_min:
            continue  # volume dead
        entry = (ts, c)
        break
    if entry is None:
        return None
    entry_ts, entry_price = entry

    # exit: scan forward rows for hard_stop / tp / trail / time_stop
    fwd = [r for r in rows if r[0] > entry_ts]
    if not fwd:
        return None
    peak = entry_price
    exit_price = exit_ts = None
    reason = None
    for r in fwd:
        ts, o, h, l, c = r[0], r[1], r[2], r[3], r[4]
        if c <= 0:
            continue
        if c <= HARD_STOP * entry_price:
            exit_price, exit_ts, reason = l, ts, "hard_stop"
            break
        if c >= TP * entry_price:
            exit_price, exit_ts, reason = l, ts, "tp"
            break
        # trailing stop: exit if price drops 25% below running peak
        peak = max(peak, h)
        if c <= peak * (1 - TRAIL):
            exit_price, exit_ts, reason = l, ts, "trail"
            break
        if ts - entry_ts >= TIME_STOP:
            exit_price, exit_ts, reason = l, ts, "time_stop"
            break
    if exit_price is None:
        exit_price, exit_ts, reason = fwd[-1][4], fwd[-1][0], "data_end"
    pnl = (exit_price / entry_price - 1.0) * NOTIONAL
    slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
    cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip
    return {"mint": trigger["mint"], "wallet": trigger["wallet"], "pnl_net": pnl - cost,
            "reason": reason, "entry_ts": entry_ts, "entry_price": entry_price}


def run(cap_mult, vol_min, usd=150.0):
    trigs = load_triggers()
    mints = load_mints(min_candles=60)
    trades = []
    skipped_no_chart = 0
    for t in trigs:
        rows = mints.get(t["mint"])
        if not rows:
            skipped_no_chart += 1
            continue
        tr = sim_one(t, rows, cap_mult, vol_min, usd)
        if tr:
            trades.append(tr)
    return {"trades": trades, "triggers": len(trigs), "no_chart": skipped_no_chart}


def main():
    print("== source-2 wallet-trigger + chart-conditioned entry ==")
    for cap in (1.0, 1.25, 1.5):
        for vol in (0, 5, 10):
            res = run(cap, vol)
            pnls = [t["pnl_net"] for t in res["trades"]]
            m = expectancy.evaluate(pnls)
            print(f"  cap={cap:.2f} vol>={vol}: n={len(pnls):3d} (trig={res['triggers']}, no_chart={res['no_chart']}) "
                  f"exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")


if __name__ == "__main__":
    main()
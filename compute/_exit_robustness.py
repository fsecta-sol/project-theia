#!/usr/bin/env python3
"""Robustness of time_stop=240m (winning exit config): provenance split +
day-bucket guard (guard against the 08-31 GATE_HIT-style concentration)."""
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


def entries(rows):
    n = len(rows)
    highs = [r[2] for r in rows]
    opens = [r[1] for r in rows]
    closes = [r[4] for r in rows]
    out, i = [], 0
    while i < n:
        hh = max(highs[max(0, i - 120):i + 1])
        if hh <= 0 or closes[i] > 0.60 * hh:
            i += 1
            continue
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
            out.append(k)
            i = found + 1
        else:
            i += 1
    return out


def run(mm, params):
    trades, by_day = [], defaultdict(list)
    for key, rows in mm.items():
        for k in entries(rows):
            ep = rows[k][1]
            path = rows[k + 1:]
            if len(path) < 5:
                continue
            res = exit_engine.simulate_exit(ep, rows[k][0], path, params)
            pnl = (res["return_mult"] - 1.0) * NOTIONAL - COST
            trades.append(pnl)
            by_day[datetime.fromtimestamp(rows[k][0], TZ).strftime("%m-%d")].append(pnl)
    return expectancy.evaluate(trades), by_day


mints = load_mints(min_candles=60)
new = {f.stem[:-4] for f in OHLCV.iterdir() if f.is_file() and f.stem.endswith("_now")}
org = {k: r for k, r in mints.items() if k not in new}
retro = {k: r for k, r in mints.items() if k in new}

for name, mm in (("ORGANIC", org), ("RETRO", retro)):
    m, by_day = run(mm, {"hard_stop": -0.35, "time_stop_secs": 240 * 60})
    print(f"{name}: n={m['n']} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f}")
    pos = sum(1 for d, v in by_day.items() if sum(v) / len(v) > 0)
    print(f"   days pos={pos} neg={len(by_day) - pos}")

# also the runner-config (60m) for comparison on organic
m60, _ = run(org, {"hard_stop": -0.35, "time_stop_secs": 60 * 60})
print(f"\nORGANIC time60 (live): exp={m60['expectancy']:+.4f} pf={m60['profit_factor']:.3f} n={m60['n']}")

# drop-top-outlier robustness on organic 240m
m, by_day = run(org, {"hard_stop": -0.35, "time_stop_secs": 240 * 60})
# drop-top-outlier on organic 240m
trades = []
for key, rows in org.items():
    for k in entries(rows):
        ep = rows[k][1]
        path = rows[k + 1:]
        if len(path) < 5:
            continue
        res = exit_engine.simulate_exit(ep, rows[k][0], path, {"hard_stop": -0.35, "time_stop_secs": 240 * 60})
        trades.append((res["return_mult"] - 1.0) * NOTIONAL - COST)
sp = sorted(trades, reverse=True)
for drop in (0, 1, 5, 10, 50):
    mm2 = expectancy.evaluate(sp[drop:])
    print(f"drop top-{drop}: exp={mm2['expectancy']:+.4f} pf={mm2['profit_factor']:.3f}")
half = len(sp) // 2
for nm, lst in (("first_half", sp[:half]), ("second_half", sp[half:])):
    mm2 = expectancy.evaluate(lst)
    print(f"{nm}: n={mm2['n']} exp={mm2['expectancy']:+.4f} pf={mm2['profit_factor']:.3f}")

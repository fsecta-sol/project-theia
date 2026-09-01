#!/usr/bin/env python3
"""Sanity check the research-runner GATE_HIT numbers: they show exp +0.52 / PF 7.5
(dip_reversal) and exp +1.58 / PF 16.9 (volume_lowbuy) — but our own verdicts
(from 2026-08-30/31) were NEGATIVE on the organic universe. Where does the
discrepancy come from? Candidate explanations to test:
  A) no costs charged in sim_mint (pnl = raw return × NOTIONAL, no gas/slippage)
  B) retro-fetched cache mixing (the fetch-bias trap, shallow-dip verdict)
  C) exit_mult 1.30/2.0 with time-stop 120m vs our prior configs
Run the same sim with costs applied and provenance split to reconcile.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim  # noqa: E402
from compute.volume_lowbuy_backtest import load_mints, sim_mint, NOTIONAL  # noqa: E402

# A) replicate the runner's best config, then subtract costs
mints = load_mints(min_candles=120)
print(f"mints cached: {len(mints)}")

best = None
for dip in (0.20, 0.30, 0.40):
    for cf in (0.85, 0.90, 0.95):
        s = [x for r in mints.values() for x in sim_mint(r, dip, cf, 1.30, 120)]
        m = expectancy.evaluate([x["pnl"] for x in s])
        if best is None or m["expectancy"] > best["expectancy"]:
            best = {"rule": "dip_reversal", "dip": dip, "cf": cf, **m}
print(f"\nrunner-style best dip_reversal (no costs): exp={best['expectancy']:+.4f} "
      f"pf={best['profit_factor']:.3f} n={best['n']}")

# A-check: same sim with costs applied per trade
s = [x for r in mints.values() for x in sim_mint(*[None], 0.40, 0.95, 1.30, 120)] if False else \
    [x for r in mints.values() for x in sim_mint(r, best["dip"], best["cf"], 1.30, 120)]
usd = 150.0
slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip
pnls_net = [x["pnl"] - cost for x in s]
m2 = expectancy.evaluate(pnls_net)
print(f"same config WITH costs: exp={m2['expectancy']:+.4f} pf={m2['profit_factor']:.3f} n={m2['n']}")
print(f"  cost per trade: {cost:.5f} SOL (gas+slip on 0.5 notional)")

# B-check: provenance split (organic cache files vs fetched _now files)
OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
new_files = {f.stem[:-4] for f in OHLCV.iterdir()
             if f.is_file() and f.stem.endswith("_now")}
organic_trades, fetched_trades = [], []
for key, r in mints.items():
    ts = sim_mint(r, best["dip"], best["cf"], 1.30, 120)
    if key in new_files:
        fetched_trades += ts
    else:
        organic_trades += ts
for name, lst in (("ORGANIC cache", organic_trades), ("RETRO-fetched (_now)", fetched_trades)):
    mm = expectancy.evaluate([x["pnl"] for x in lst])
    print(f"{name}: n={mm['n']} exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f}")

# C-check: exit_mult effect (1.3 vs 2.0)
for em in (1.30, 2.00):
    ts = [x for r in mints.values() for x in sim_mint(r, best["dip"], best["cf"], em, 120)]
    mm = expectancy.evaluate([x["pnl"] for x in ts])
    print(f"exit_mult={em}: exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f} n={mm['n']}")
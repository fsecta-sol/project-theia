#!/usr/bin/env python3
"""Reconcile the runner GATE_HIT vs our verdicts — full battery.

Findings so far (from _gatehit_reconcile.py):
- runner-style dip_reversal no-costs: +0.52/PF 7.5 (n=11k) — matches GATE_HIT
- with costs: +0.52 → +0.52 (cost 0.0043/trade, small)
- provenance split: ORGANIC +0.18/PF 3.3 (n=9.3k) | RETRO +2.32/PF 29 (n=1.7k)
  → the +0.52 headline is STILL fetch-bias-dressed: organic-only is +0.18.

Now verify the organic-only number honestly:
  1. organic-only dip_reversal grid: is +0.18 stable across configs?
  2. organic-only with costs: does it survive 0.0043/trade?
  3. organic-only split-half + drop-top-outlier robustness
  4. same for volume_lowbuy battery (runner's +1.58/PF 16.9 headline)
Then update the GATE_HIT consumption rule: runner gate must run ORGANIC-ONLY
+ costs before flagging HIT.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim  # noqa: E402
from compute.volume_lowbuy_backtest import load_mints, sim_mint, NOTIONAL  # noqa: E402
from compute.dip_reversal_backtest import load_pools  # noqa: E402

mints = load_mints(min_candles=120)
OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
new_files = {f.stem[:-4] for f in OHLCV.iterdir()
             if f.is_file() and f.stem.endswith("_now")}

usd = 150.0
slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip

print(f"mints: {len(mints)} | organic keys: "
      f"{sum(1 for k in mints if k not in new_files)} | retro: {sum(1 for k in mints if k in new_files)}")

# 1. organic-only dip_reversal grid
print("\n== organic-only dip_reversal grid (no costs) ==")
best_org = None
for dip in (0.20, 0.30, 0.40):
    for cf in (0.85, 0.90, 0.95):
        s = [x for k, r in mints.items() if k not in new_files for x in sim_mint(r, dip, cf, 1.30, 120)]
        m = expectancy.evaluate([x["pnl"] for x in s])
        if best_org is None or m["expectancy"] > best_org["expectancy"]:
            best_org = {"dip": dip, "cf": cf, **m}
        print(f"  dip={dip:.2f} cf={cf:.2f}: n={m['n']} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f}")
print(f"BEST organic: {best_org['dip']}/{best_org['cf']} exp={best_org['expectancy']:+.4f} "
      f"pf={best_org['profit_factor']:.3f} n={best_org['n']}")

# 2. with costs
pnls_net = [x["pnl"] - cost for k, r in mints.items() if k not in new_files
            for x in sim_mint(r, best_org["dip"], best_org["cf"], 1.30, 120)]
m2 = expectancy.evaluate(pnls_net)
print(f"\norganic + costs: exp={m2['expectancy']:+.4f} pf={m2['profit_factor']:.3f} n={m2['n']}")

# 3. split-half + outlier on organic best config
trades = [x for k, r in mints.items() if k not in new_files
          for x in sim_mint(r, best_org["dip"], best_org["cf"], 1.30, 120)]
sp = sorted([t["pnl"] for t in trades], reverse=True)
for k in (0, 1, 5, 10, 50):
    mm = expectancy.evaluate(sp[k:])
    print(f"drop top-{k}: exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f}")
half = len(trades) // 2
first_half = [t["pnl"] for t in trades[:half]]
second_half = [t["pnl"] for t in trades[half:]]
for nm, lst in (("first_half", first_half), ("second_half", second_half)):
    mm = expectancy.evaluate(lst)
    print(f"{nm}: n={mm['n']} exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f}")

# 4. volume_lowbuy organic-only
print("\n== organic-only volume_lowbuy grid (no costs) ==")
best_vb = None
for dip in (0.30, 0.40, 0.50):
    for vm in (2.0, 3.0):
        s = [x for k, r in mints.items() if k not in new_files
             for x in sim_mint(r, dip, vm, 2.0, 120, require_vol=True)]
        m = expectancy.evaluate([x["pnl"] for x in s])
        if best_vb is None or m["expectancy"] > best_vb["expectancy"]:
            best_vb = {"dip": dip, "volx": vm, **m}
        print(f"  dip={dip:.2f} volx={vm}: n={m['n']} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f}")
print(f"BEST organic vol: {best_vb['dip']}/{best_vb['volx']} exp={best_vb['expectancy']:+.4f} "
      f"pf={best_vb['profit_factor']:.3f} n={best_vb['n']}")
pnls_vb = [x["pnl"] - cost for k, r in mints.items() if k not in new_files
           for x in sim_mint(r, best_vb["dip"], best_vb["volx"], 2.0, 120, require_vol=True)]
m3 = expectancy.evaluate(pnls_vb)
print(f"organic vol + costs: exp={m3['expectancy']:+.4f} pf={m3['profit_factor']:.3f} n={m3['n']}")
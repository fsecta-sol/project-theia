#!/usr/bin/env python3
"""Deep-dive the promising volume-confirmed configs (exit>=1.5, volx>=3)."""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy
from compute.volume_lowbuy_backtest import load_mints, sim_mint

mints = load_mints(min_candles=120)
print("mints:", len(mints))

print("\n=== A) exit sweep for strong vol configs (dip=0.40) ===")
for vm in (2.0, 3.0, 4.0):
    for em in (1.5, 2.0, 2.5, 3.0):
        sims = [s for r in mints.values() for s in sim_mint(r, 0.40, vm, em, 120, require_vol=True)]
        m = expectancy.evaluate([s["pnl"] for s in sims])
        print(f"  volx={vm} exit={em}: n={len(sims):4d} exp={m['expectancy']:+.5f} "
              f"pf={m['profit_factor']:.3f} win={m['win_rate']:.3f} wilson_low={m['wilson_low']:.3f}")

print("\n=== B) distinct mints per strong config ===")
for vm, em in [(3.0, 2.0), (4.0, 2.0), (3.0, 2.5), (4.0, 2.5)]:
    seen = set()
    sims = []
    for key, r in mints.items():
        ss = sim_mint(r, 0.40, vm, em, 120, require_vol=True)
        if ss:
            seen.add(key)
        sims += ss
    m = expectancy.evaluate([s["pnl"] for s in sims])
    print(f"  volx={vm} exit={em}: n={len(sims):4d} mints={len(seen):3d} exp={m['expectancy']:+.5f} "
          f"pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

print("\n=== C) per-mint attribution volx=3.0 exit=2.0 ===")
agg = defaultdict(list)
for key, r in mints.items():
    for s in sim_mint(r, 0.40, 3.0, 2.0, 120, require_vol=True):
        agg[key].append(s["pnl"])
for key, pnls in sorted(agg.items(), key=lambda kv: -sum(kv[1])):
    m = expectancy.evaluate(pnls)
    print(f"  {key[:26]:28s} n={len(pnls):4d} exp={m['expectancy']:+.5f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

print("\n=== D) split-half volx=3.0 exit=2.0 ===")
h1, h2 = [], []
for key, r in mints.items():
    mid = len(r) // 2
    h1 += [s for s in sim_mint(r[:mid + 1], 0.40, 3.0, 2.0, 120, require_vol=True)]
    h2 += [s for s in sim_mint(r, 0.40, 3.0, 2.0, 120, require_vol=True) if s["entry_ts"] >= r[mid][0]]
for name, sims in (("first", h1), ("second", h2)):
    m = expectancy.evaluate([s["pnl"] for s in sims])
    print(f"  {name}: n={len(sims)} exp={m['expectancy']:+.5f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

print("\n=== E) outlier volx=3.0 exit=2.0 ===")
sims = [s for r in mints.values() for s in sim_mint(r, 0.40, 3.0, 2.0, 120, require_vol=True)]
pnls = sorted([s["pnl"] for s in sims], reverse=True)
for k in (1, 2, 3, 5, 10):
    m = expectancy.evaluate(pnls[k:])
    print(f"  drop top-{k}: n={len(pnls)-k} exp={m['expectancy']:+.5f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")
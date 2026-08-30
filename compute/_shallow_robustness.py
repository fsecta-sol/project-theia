#!/usr/bin/env python3
"""Full robustness battery for the shallow-dip + momentum edge."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy
from compute.volume_lowbuy_backtest import load_mints
from compute.shallow_dip_entry_backtest import sim_mint

mints = load_mints(min_candles=120)
print(f"mints: {len(mints)}")

# best config from sweep
DLO, DHI, MF = 0.25, 0.45, 1.00

# per-mint trades
per_mint = {}
for key, r in mints.items():
    ts = sim_mint(r, DLO, DHI, MF, mint_label=key)
    if ts:
        per_mint[key] = ts
all_trades = [t for ts in per_mint.values() for t in ts]
pnls = [t["pnl_net"] for t in all_trades]
m = expectancy.evaluate(pnls)
print(f"\nBEST config dip={DLO}-{DHI} mom>={MF}: n={len(pnls)} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")
print(f"  mints with trades: {len(per_mint)}")

# 1. per-mint concentration
cnt = Counter(t["mint"] for t in all_trades)
top5 = cnt.most_common(5)
print(f"\n== per-mint concentration (top 5 of {len(cnt)}) ==")
for k, v in top5:
    print(f"  {k[:16]}: {v} trades ({100*v/len(all_trades):.1f}%)")
# mint-level expectancy
mint_exp = []
for key, ts in per_mint.items():
    mm = expectancy.evaluate([t["pnl_net"] for t in ts])
    mint_exp.append((mm["expectancy"], key, len(ts)))
mint_exp.sort(reverse=True)
print(f"  mints with exp>0: {sum(1 for e,_,_ in mint_exp if e>0)}/{len(mint_exp)}")
print(f"  top3 by exp: {[(k[:14], round(e,3), n) for e,k,n in mint_exp[:3]]}")
print(f"  bottom3: {[(k[:14], round(e,3), n) for e,k,n in mint_exp[-3:]]}")

# 2. split-half by time (per mint half)
h1, h2 = [], []
for key, r in mints.items():
    mid = len(r) // 2
    h1 += sim_mint(r[:mid + 1], DLO, DHI, MF, mint_label=key)
    h2 += [t for t in sim_mint(r, DLO, DHI, MF, mint_label=key) if t["entry_ts"] >= r[mid][0]]
for name, sims in (("first_half", h1), ("second_half", h2)):
    mm = expectancy.evaluate([t["pnl_net"] for t in sims])
    print(f"\n== split {name}: n={len(sims)} exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f} win={mm['win_rate']:.3f}")

# 3. outlier (done in sweep, reconfirm)
sp = sorted(pnls, reverse=True)
for k in (1, 5, 10, 50):
    mm = expectancy.evaluate(sp[k:])
    print(f"\n== drop top-{k}: exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f}")

# 4. exit reason distribution
reasons = Counter(t["reason"] for t in all_trades)
print(f"\n== exit reasons: {dict(reasons)}")

# 5. venue: derive from mint prefix (pump vs not)
pump = [t for t in all_trades if "pump" in t["mint"]]
nonpump = [t for t in all_trades if "pump" not in t["mint"]]
for name, sims in (("pump*", pump), ("non-pump", nonpump)):
    if not sims:
        continue
    mm = expectancy.evaluate([t["pnl_net"] for t in sims])
    print(f"\n== venue {name}: n={len(sims)} exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f} win={mm['win_rate']:.3f}")

# 6. time-stop / tp dominance — is the edge one exit?
for r in ("tp", "trail", "hard_stop", "time_stop", "data_end"):
    sub = [t for t in all_trades if t["reason"] == r]
    if sub:
        mm = expectancy.evaluate([t["pnl_net"] for t in sub])
        print(f"\n== reason {r}: n={len(sub)} exp={mm['expectancy']:+.4f} pf={mm['profit_factor']:.3f} win={mm['win_rate']:.3f}")
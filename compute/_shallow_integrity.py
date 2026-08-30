#!/usr/bin/env python3
"""Check point-in-time integrity of the shallow-dip edge + out-of-sample split.

Questions:
  A. Is the edge concentrated in mints fetched TODAY (background fetch) vs
     pre-existing cache? If yes -> the fetch introduced selection bias.
  B. Does the rule only fire near the END of a mint's series (lookback window
     needs i>=30, so early candles can't fire — but if it ONLY fires in the last
     few candles of young series, the signal is 'newly listed' not 'shallow dip').
  C. Does 'momentum>=1.0' mean close[i]>=close[i-30] (alive) — verify sign.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy
from compute.volume_lowbuy_backtest import load_mints
from compute.shallow_dip_entry_backtest import sim_mint

mints = load_mints(min_candles=120)
print(f"mints total: {len(mints)}")

# A: which mints are NEW (created today by our fetch)? those files have _now.json
# and were written by _fetch_missing_ohlcv (single file, 'now' suffix).
OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
new_files = set()
for f in OHLCV.iterdir():
    if f.is_file() and f.stem.endswith("_now"):
        new_files.add(f.stem[:-len("_now")])
print(f"files with '_now' suffix (fetched today): {len(new_files)}")

DLO, DHI, MF = 0.25, 0.45, 1.00

# per-mint trades with source tag
old_trades, new_trades = [], []
new_mint_trades = 0
for key, r in mints.items():
    ts = sim_mint(r, DLO, DHI, MF, mint_label=key)
    if not ts:
        continue
    if key in new_files:
        new_trades += ts
    else:
        old_trades += ts

for name, sims in (("PRE-EXISTING cache", old_trades), ("FETCHED today", new_trades)):
    if not sims:
        print(f"\n== {name}: 0 trades")
        continue
    m = expectancy.evaluate([t["pnl_net"] for t in sims])
    print(f"\n== {name}: n={len(sims)} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

# B: entry position within series (fraction of way through the mint's candles)
print("\n== entry position within series (all trades) ==")
pos_hist = Counter()
samples = []
for key, r in mints.items():
    ts = sim_mint(r, DLO, DHI, MF, mint_label=key)
    n = len(r)
    for t in ts:
        idx = min(range(n), key=lambda j: abs(r[j][0] - t["entry_ts"]))
        frac = idx / n
        pos_hist[min(int(frac * 10), 9)] += 1
        if len(samples) < 5:
            samples.append((key[:12], n, idx, round(frac, 2)))
for b in sorted(pos_hist):
    print(f"  decile {b*10}-{b*10+10}%: {pos_hist[b]} trades")
print("  samples (mint, n_rows, entry_idx, frac):", samples)

# C: momentum sign check
print("\n== momentum sign (dip candles that fire, mom = close[i]/close[i-30]) ==")
moms = []
for key, r in mints.items():
    n = len(r)
    closes = [x[4] for x in r]
    highs = [x[2] for x in r]
    ath = [0.0] * n
    for i in range(n):
        ath[i] = max(highs[max(0, i - 180):i + 1])
    for i in range(30, n):
        if ath[i] > 0:
            dd = 1 - closes[i] / ath[i]
            if 0.25 <= dd <= 0.45 and closes[i - 30] > 0:
                moms.append(closes[i] / closes[i - 30])
import statistics
moms.sort()
print(f"  n={len(moms)} median={statistics.median(moms):.3f} q25={moms[len(moms)//4]:.3f} q75={moms[3*len(moms)//4]:.3f}")
print(f"  share with mom>=1.0: {sum(1 for x in moms if x>=1.0)/len(moms):.3f}")
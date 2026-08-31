#!/usr/bin/env python3
"""Stage 2b — OOS split: features from scan days 1-3, outcome from days 4-6.

In-sample discovery (stage 2) found txs7/volume/rPnl-momentum/hold monotonic
positive, wr7 inverted. To check it's not window-artifact: define features at
the FIRST scan in days 1-3 (25-27 Aug), measure forward drift from scans in
days 4-6 (28-30 Aug) only. Monotonic separation persisting = real signal.
"""
import json
import sqlite3
import statistics
import time
from collections import defaultdict

DB = "/home/hermes/.hermes/theia/theia.db"
NOW = int(time.time())
D0 = NOW - 6 * 86400          # ~25 Aug
FEAT_HI = NOW - 3 * 86400     # feature window ends ~28 Aug
OUT_LO = NOW - 3 * 86400      # outcome window starts ~28 Aug

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT wallet, scan_ts, realized_profit_7d, winrate_7d, txs_7d, "
    "avg_holding_period_7d, volume_7d, tags FROM wallet_scan_history "
    "WHERE scan_ts BETWEEN ? AND ? ORDER BY wallet, scan_ts", (D0, NOW - 1)).fetchall()
con.close()

feat = {}   # wallet -> features at latest scan in days1-3
outc = {}   # wallet -> max r7 in days4-6 (and drift vs last feature-scan r7)
for r in rows:
    if r["realized_profit_7d"] is None:
        continue
    w = r["wallet"]
    if r["scan_ts"] < FEAT_HI:
        feat[w] = {
            "r7": r["realized_profit_7d"], "wr": r["winrate_7d"], "txs": r["txs_7d"],
            "hold_h": (r["avg_holding_period_7d"] or 0) / 3600.0,
            "vol": r["volume_7d"] or 0, "ts": r["scan_ts"],
            "tags": set(json.loads(r["tags"] or "[]") if r["tags"] else []),
        }
    else:
        if w not in outc or r["realized_profit_7d"] > outc[w]:
            outc[w] = r["realized_profit_7d"]

cohort = {}
for w, f in feat.items():
    if w in outc:
        cohort[w] = {**f, "fwd_drift": outc[w] - f["r7"]}

print(f"OOS cohort (feature in days1-3, outcome in days4-6): {len(cohort)}")
ds = [c["fwd_drift"] for c in cohort.values()]
print(f"overall: median={statistics.median(ds):+.0f} share+ve={sum(1 for d in ds if d>0)/len(ds):.0%}\n")


def bucketize(name, keyfn, buckets):
    groups = defaultdict(list)
    for c in cohort.values():
        v = keyfn(c)
        if v is None:
            continue
        for label, lo, hi in buckets:
            if lo <= v < hi:
                groups[label].append(c["fwd_drift"])
                break
    print(f"== {name} (feature@days1-3 → outcome@days4-6) ==")
    for label, lo, hi in buckets:
        d = groups.get(label, [])
        if d:
            print(f"  {label:<16} n={len(d):>4} median={statistics.median(d):>+9.0f} "
                  f"share+ve={sum(1 for x in d if x>0)/len(d):.0%}")
        else:
            print(f"  {label:<16} n=0")
    print()


bucketize("winrate_7d", lambda c: c["wr"],
          [("<0.30", -1, 0.30), ("0.30-0.45", 0.30, 0.45), ("0.45-0.60", 0.45, 0.60),
           ("0.60-0.80", 0.60, 0.80), (">=0.80", 0.80, 99)])
bucketize("txs_7d", lambda c: c["txs"],
          [("<50", -1, 50), ("50-150", 50, 150), ("150-500", 150, 500),
           ("500-2000", 500, 2000), (">=2000", 2000, 10**9)])
bucketize("hold_hours", lambda c: c["hold_h"] if c["hold_h"] > 0 else None,
          [("<1h", -1, 1), ("1-6h", 1, 6), ("6-24h", 6, 24), ("24-48h", 24, 48), (">48h", 48, 1e9)])
vol_vals = sorted(c["vol"] for c in cohort.values() if c["vol"] > 0)
qs = [vol_vals[int(len(vol_vals) * q)] for q in (0.25, 0.5, 0.75)] if vol_vals else [1, 2, 3]
bucketize("volume_7d (quartiles)", lambda c: c["vol"] if c["vol"] > 0 else None,
          [("q1", -1, qs[0]), ("q2", qs[0], qs[1]), ("q3", qs[1], qs[2]), ("q4", qs[2], 1e18)])
bucketize("rPnl7d level", lambda c: c["r7"],
          [("<0", -1e9, 0), ("0-1k", 0, 1000), ("1k-10k", 1000, 10000),
           ("10k-50k", 10000, 50000), (">=50k", 50000, 1e12)])

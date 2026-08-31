#!/usr/bin/env python3
"""Gate-persistence stage 2 — which stored feature actually predicts forward drift?

From stage 1c: the wr7>=0.6 threshold doesn't discriminate (near-miss outperformed
2:1). This stage sweeps EVERY labeled feature in wallet_scan_history and measures,
per feature bucket (at the wallet's FIRST scan in the window), the forward drift
of realized_profit_7d (max later r7 - first r7). A real discriminator shows
monotonic bucket separation. If nothing separates → wallets are a candidate-token
source only (option c), not an edge.

Features tested (at first scan):
  wr7 (winrate_7d), txs7, hold_h (avg_holding_period_7d /3600), vol7 (volume_7d),
  r7 level (realized_profit_7d at scan), tags (fresh_wallet / bluechip_owner).
API-free; wallet_scan_history only.
"""
import json
import sqlite3
import statistics
import time
from collections import defaultdict

DB = "/home/hermes/.hermes/theia/theia.db"
NOW = int(time.time())
WIN_LO = NOW - 6 * 86400
WIN_HI = NOW - 1 * 86400

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT wallet, scan_ts, gate_pass, realized_profit_7d, winrate_7d, txs_7d, "
    "avg_holding_period_7d, volume_7d, tags FROM wallet_scan_history "
    "WHERE scan_ts BETWEEN ? AND ? ORDER BY wallet, scan_ts", (WIN_LO, WIN_HI)).fetchall()
con.close()

series = defaultdict(list)
for r in rows:
    if r["realized_profit_7d"] is None:
        continue
    try:
        tags = set(json.loads(r["tags"] or "[]"))
    except Exception:
        tags = set()
    series[r["wallet"]].append({
        "ts": r["scan_ts"], "gp": r["gate_pass"], "r7": r["realized_profit_7d"],
        "wr": r["winrate_7d"], "txs": r["txs_7d"],
        "hold_h": (r["avg_holding_period_7d"] or 0) / 3600.0,
        "vol": r["volume_7d"] or 0, "tags": tags,
    })

# keep wallets with >=2 scans (need a forward window) and >=3 days span
cohort = {}
for w, seq in series.items():
    if len(seq) < 2 or (seq[-1]["ts"] - seq[0]["ts"]) < 2 * 86400:
        continue
    f, l = seq[0], seq[-1]
    later = [s["r7"] for s in seq[1:]]
    cohort[w] = {
        "fwd_drift": max(later) - f["r7"],
        "wr": f["wr"], "txs": f["txs"], "hold_h": f["hold_h"],
        "vol": f["vol"], "r7": f["r7"], "tags": f["tags"],
        "gp": f["gp"], "n_scans": len(seq),
    }

print(f"cohort wallets (>=2 scans, >=2d span): {len(cohort)}")
all_drifts = [c["fwd_drift"] for c in cohort.values()]
print(f"overall: median={statistics.median(all_drifts):+.0f} "
      f"mean={statistics.mean(all_drifts):+.0f} "
      f"share+ve={sum(1 for d in all_drifts if d>0)/len(all_drifts):.0%}\n")


def bucketize(name, keyfn, buckets):
    print(f"== {name} ==")
    groups = defaultdict(list)
    for c in cohort.values():
        v = keyfn(c)
        if v is None:
            continue
        for label, lo, hi in buckets:
            if lo <= v < hi:
                groups[label].append(c["fwd_drift"])
                break
    for label, lo, hi in buckets:
        ds = groups.get(label, [])
        if not ds:
            print(f"  {label:<22} n=0")
            continue
        print(f"  {label:<22} n={len(ds):>4} median={statistics.median(ds):>+9.0f} "
              f"share+ve={sum(1 for d in ds if d>0)/len(ds):.0%}")
    print()


bucketize("winrate_7d (at scan)",
          lambda c: c["wr"],
          [("<0.30", -1, 0.30), ("0.30-0.45", 0.30, 0.45), ("0.45-0.60", 0.45, 0.60),
           ("0.60-0.80", 0.60, 0.80), (">=0.80", 0.80, 99)])

bucketize("txs_7d (at scan)",
          lambda c: c["txs"],
          [("<50", -1, 50), ("50-150", 50, 150), ("150-500", 150, 500),
           ("500-2000", 500, 2000), (">=2000", 2000, 10**9)])

bucketize("hold (hours, at scan)",
          lambda c: c["hold_h"] if c["hold_h"] > 0 else None,
          [("<1h", -1, 1), ("1-6h", 1, 6), ("6-24h", 6, 24),
           ("24-48h", 24, 48), (">48h", 48, 10**9)])

vol_vals = sorted(c["vol"] for c in cohort.values() if c["vol"] > 0)
qs = [vol_vals[int(len(vol_vals) * q)] for q in (0.25, 0.5, 0.75)] if vol_vals else [1, 2, 3]
bucketize("volume_7d (at scan, quartiles)",
          lambda c: c["vol"] if c["vol"] > 0 else None,
          [("q1", -1, qs[0]), ("q2", qs[0], qs[1]), ("q3", qs[1], qs[2]), ("q4", qs[2], 10**18)])

bucketize("rPnl7d level (at scan)",
          lambda c: c["r7"],
          [("<0", -10**9, 0), ("0-1k", 0, 1000), ("1k-10k", 1000, 10000),
           ("10k-50k", 10000, 50000), (">=50k", 50000, 10**12)])

for tag in ("fresh_wallet", "bluechip_owner", "trojan", "axiom"):
    have = [c["fwd_drift"] for c in cohort.values() if tag in c["tags"]]
    rest = [c["fwd_drift"] for c in cohort.values() if tag not in c["tags"]]
    if have:
        print(f"== tag {tag}: n={len(have)} median={statistics.median(have):+.0f} "
              f"share+ve={sum(1 for d in have if d>0)/len(have):.0%} "
              f"(rest n={len(rest)} median={statistics.median(rest):+.0f})")
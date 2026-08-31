#!/usr/bin/env python3
"""Audit the wash_trader tag: provenance, stability, and behavioral evidence.

Q1 provenance: we never compute it — it comes from GMGN's walletNew `tags` array.
Q2 stability: does the tag persist across scans for the tagged whales?
Q3 behavior: do tagged wallets show wash-trading signatures in OUR stored data?
   - classic wash signature: same mint bought AND sold repeatedly in short
     round trips (self-dealing / volume inflation)
   - vs high-frequency scalping: many distinct mints, genuine round trips
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DB = "/home/hermes/.hermes/theia/theia.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

WHALES = ["2fg5QD1eD7rz", "suqh5sHtr8Hy", "ardinRsN1mNYVe", "6G8Cu53PRgm5aP"]

# Q2: tag stability across scans
print("== Q2: tag stability across scans (all scans since 25-Aug) ==")
for s in WHALES:
    rows = con.execute(
        "SELECT scan_ts, tags FROM wallet_scan_history WHERE wallet LIKE ? "
        "ORDER BY scan_ts", (s + "%",)).fetchall()
    if not rows:
        print(f"  {s}: no scans")
        continue
    tag_sets = []
    wash_count = 0
    for r in rows:
        try:
            tags = set(json.loads(r["tags"] or "[]"))
        except Exception:
            tags = set()
        tag_sets.append(tags)
        if "wash_trader" in tags:
            wash_count += 1
    n = len(rows)
    full = tag_sets[0] if tag_sets else set()
    stable = all(t == full for t in tag_sets)
    print(f"  {s:<15} scans={n} wash_trader in {wash_count}/{n} "
          f"({wash_count/n:.0%}) tags_stable={stable}")
    print(f"     tags: {sorted(full)[:8]}")

# Q3a: population stats — tagged vs untagged wallets (latest scan today)
print("\n== Q3a: population stats, latest scan per wallet today ==")
rows = con.execute(
    "SELECT wallet, scan_ts, tags, txs_7d, volume_7d, realized_profit_7d, "
    "winrate_7d, avg_holding_period_7d FROM wallet_scan_history "
    "WHERE scan_ts >= strftime('%s','2026-08-31') ORDER BY wallet, scan_ts").fetchall()
latest = {}
for r in rows:
    latest[r["wallet"]] = r
tagged, untagged = [], []
for w, r in latest.items():
    try:
        tags = set(json.loads(r["tags"] or "[]"))
    except Exception:
        tags = set()
    grp = tagged if "wash_trader" in tags else untagged
    grp.append(r)

for name, grp in (("wash_trader-tagged", tagged), ("NOT tagged", untagged)):
    if not grp:
        print(f"  {name}: none")
        continue
    txs = [r["txs_7d"] or 0 for r in grp]
    vol = [r["volume_7d"] or 0 for r in grp]
    r7 = [r["realized_profit_7d"] or 0 for r in grp]
    wr = [r["winrate_7d"] for r in grp if r["winrate_7d"] is not None]
    hold = [(r["avg_holding_period_7d"] or 0) / 3600 for r in grp]
    txs.sort(); vol.sort(); r7.sort()
    import statistics
    print(f"  {name:<20} n={len(grp):>3} | median txs={statistics.median(txs):>6.0f} "
          f"vol=${statistics.median(vol):>10,.0f} rPnl7d={statistics.median(r7):>+8,.0f} "
          f"hold={statistics.median(hold):>5.1f}h wr={statistics.median(wr):.2f}" if wr else
          f"  {name:<20} n={len(grp):>3} | median txs={statistics.median(txs):>6.0f} "
          f"vol=${statistics.median(vol):>10,.0f} rPnl7d={statistics.median(r7):>+8,.0f} "
          f"hold={statistics.median(hold):>5.1f}h wr=n/a")

# how many tagged have huge rPnl (profitable DESPITE the tag)
big = sum(1 for r in tagged if (r["realized_profit_7d"] or 0) > 10000)
print(f"  tagged wallets with rPnl7d>10k: {big}/{len(tagged)}")
con.close()
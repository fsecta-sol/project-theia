#!/usr/bin/env python3
"""Check mcap data availability for whale-traced mints (price_snapshots v1.1
has a mcap column; OHLCV cache rows have 6+ fields only when volume recorded)."""
import json
import sqlite3
from collections import defaultdict

suqh = json.load(open('compute/_suqh_lots.json'))
v2 = json.load(open('compute/_whale_lots_v2.json'))
mints = set()
for l in suqh:
    mints.add(l['mint'])
for w, dd in v2.items():
    for l in dd.get('lots', []):
        mints.add(l['mint'])
print('whale mints total:', len(mints))

c = sqlite3.connect('/home/hermes/.hermes/theia/theia.db')
sample = list(mints)[:8]
rows = c.execute(
    "SELECT p.mint, SUM(CASE WHEN ps.mcap>0 THEN 1 ELSE 0 END), MAX(ps.mcap), COUNT(*) "
    "FROM pools p JOIN price_snapshots ps ON ps.pool_addr=p.pool_addr "
    "WHERE p.mint IN (%s) GROUP BY p.mint" % ','.join('?' * len(sample)),
    sample).fetchall()
print('mcap coverage in price_snapshots (sample 8):')
for r in rows:
    print(' ', r[0][:10], 'rows_with_mcap:', r[1], 'max_mcap:', r[2], 'rows:', r[3])

# OHLCV cache row width for whale mints
import sys
sys.path.insert(0, '/home/hermes/project-theia')
from compute.volume_lowbuy_backtest import load_mints
mm = load_mints(min_candles=20)
hit = 0
for key, rows2 in mm.items():
    if any(key.startswith(m[:20]) for m in mints):
        if rows2 and len(rows2[0]) > 6:
            hit += 1
print('whale mints with wide candles (>6 fields) in cache:', hit)

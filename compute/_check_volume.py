#!/usr/bin/env python3
"""Check volume data field depth across the OHLCV cache (how many rows have real v>0)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"

total_files = 0
files_with_v = 0
rows_total = 0
rows_with_v = 0
rows_with_v_gt0 = 0
sample_with_v = []

for f in OHLCV.iterdir():
    if not f.is_file():
        continue
    total_files += 1
    try:
        data = json.loads(f.read_text())
    except Exception:
        continue
    rows = data.get("rows", data) if isinstance(data, dict) else data
    if not rows:
        continue
    # field depth of first row
    if isinstance(rows[0], (list, tuple)) and len(rows[0]) >= 6:
        files_with_v += 1
    for r in rows:
        if not isinstance(r, (list, tuple)):
            continue
        rows_total += 1
        if len(r) >= 6:
            rows_with_v += 1
            try:
                if float(r[5]) > 0:
                    rows_with_v_gt0 += 1
            except (TypeError, ValueError):
                pass
    if isinstance(rows[0], (list, tuple)) and len(rows[0]) >= 6 and len(sample_with_v) < 3:
        sample_with_v.append((f.stem[:20], len(rows), rows[0][:7]))

print(f"files total: {total_files}")
print(f"files with >=6 fields: {files_with_v}")
print(f"rows total: {rows_total}")
print(f"rows with >=6 fields: {rows_with_v}")
print(f"rows with v>0 anywhere: {rows_with_v_gt0}")
print("sample rows (mint, nrows, first row):")
for s in sample_with_v:
    print("  ", s)
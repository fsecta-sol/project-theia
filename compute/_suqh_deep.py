#!/usr/bin/env python3
"""Deep-fetch suqh enhanced history until 2026-08-28 (bounded 30 pages)."""
import datetime
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

W = "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK"
CUTOFF = 1787971200  # 2026-08-28 00:00 WIB-ish
PATH = Path("/home/hermes/project-theia/compute/_suqh_enhanced.json")

all_txs = json.load(open(PATH))
oldest = min((t.get("timestamp") or 0) for t in all_txs)
print("current oldest:",
      datetime.datetime.fromtimestamp(oldest, datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M"))

before = all_txs[-1].get("signature")
added = 0
for page in range(30):
    url = (m.ENHANCED + f"/addresses/{W}/transactions?api-key={m._key()}&limit=100"
           + (f"&before={before}" if before else ""))
    txs = m.request_json(url, throttle=("helius-enh", 0.6)) or []
    if not txs:
        break
    all_txs += txs
    added += len(txs)
    before = txs[-1].get("signature")
    last_ts = txs[-1].get("timestamp") or 0
    if last_ts < CUTOFF:
        print(f"page {page}: reached cutoff, oldest now",
              datetime.datetime.fromtimestamp(last_ts, datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M"))
        break

oldest = min((t.get("timestamp") or 0) for t in all_txs)
print(f"added {added} txs; total {len(all_txs)}; oldest",
      datetime.datetime.fromtimestamp(oldest, datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M"))
PATH.write_text(json.dumps(all_txs))
print("saved")
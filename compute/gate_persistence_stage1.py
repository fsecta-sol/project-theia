#!/usr/bin/env python3
"""Gate-persistence test — stage 1: build the cohort from wallet_scan_history.

Question: does a wallet that passed the discovery gate N days ago remain
profitable today (forward rPnl)? If not, the gate has no predictive validity
and the whole follow-strategy stack is downstream-dead.

Cohort: wallets whose LATEST scan in the window (today-N .. today-1) has a
gate_pass verdict. Split pass / fail. Fresh refetch files (gmgn_refetch_*.json)
already exist for the 18 currently-tracked wallets; other cohort wallets need a
bounded refetch (stage 2).
"""
import glob
import json
import sqlite3
from pathlib import Path

DB = Path.home() / ".hermes/theia/theia.db"
OUT = Path("/home/hermes/project-theia/compute/_gate_persistence_cohort.json")

import time
NOW = int(time.time())
WIN_LO = NOW - 6 * 86400   # ~6 hari lalu (25 Aug)
WIN_HI = NOW - 1 * 86400   # kemarin

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT wallet, scan_ts, gate_pass, gate_reason FROM wallet_scan_history "
    "WHERE scan_ts BETWEEN ? AND ? ORDER BY scan_ts ASC", (WIN_LO, WIN_HI)).fetchall()
con.close()

latest = {}
for r in rows:
    latest[r["wallet"]] = {"gp": r["gate_pass"], "gr": r["gate_reason"], "ts": r["scan_ts"]}

cohort_pass = {w: v for w, v in latest.items() if v["gp"] == 1}
cohort_fail = {w: v for w, v in latest.items() if v["gp"] == 0}

# who already has fresh refetch data
fresh = {}
for f in sorted(glob.glob("/home/hermes/theia-gate/data/gmgn_refetch_*.json")):
    key = Path(f).stem.split("_")[-1]
    try:
        d = json.load(open(f))
        i7 = ((d.get("7d") or {}).get("data") or {}).get("data") or {}
        i30 = ((d.get("30d") or {}).get("data") or {}).get("data") or {}
        fresh[key] = {"rPnl7d": i7.get("realized_profit_7d"),
                      "rPnl30d": i30.get("realized_profit_30d")}
    except Exception:
        pass

pass_have = [w for w in cohort_pass if w[:12] in fresh]
pass_need = [w for w in cohort_pass if w[:12] not in fresh]
fail_have = [w for w in cohort_fail if w[:12] in fresh]
fail_need = [w for w in cohort_fail if w[:12] not in fresh]

print(f"cohort window: {WIN_LO}..{WIN_HI} (6d-1d ago)")
print(f"distinct wallets: {len(latest)} | pass={len(cohort_pass)} fail={len(cohort_fail)}")
print(f"fresh-data already available: pass {len(pass_have)} | fail {len(fail_have)}")
print(f"need refetch: pass {len(pass_need)} | fail {len(fail_need)}")
print(f"\ntotal refetch needed: {len(pass_need) + len(fail_need)} (each = 2 calls, 7d+30d)")

# inspect scan_ts distribution (how many scans per wallet in window)
from collections import Counter
per_wallet = Counter(r["wallet"] for r in rows)
dist = Counter(per_wallet.values())
print("scans-per-wallet distribution:", dict(sorted(dist.items())))

json.dump({
    "window": {"lo": WIN_LO, "hi": WIN_HI},
    "pass": cohort_pass, "fail": cohort_fail,
    "pass_have_fresh": pass_have, "pass_need": pass_need,
    "fail_have_fresh": fail_have, "fail_need": fail_need,
    "fresh_data": fresh,
}, open(OUT, "w"))
print(f"\ncohort saved -> {OUT}")
#!/usr/bin/env python3
"""Decode suqh's 41 owner-delta txs into buy/sell lots (sign from SOL leg)."""
import datetime
import json
from collections import Counter
from pathlib import Path

WSOL = "So11111111111111111111111111111111111111112"
W = "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK"

txs = json.load(open("/home/hermes/project-theia/compute/_suqh_enhanced.json"))
lots = []
for t in txs:
    hit = None
    for x in (t.get("accountData") or []):
        for ch in (x.get("tokenBalanceChanges") or []):
            if ch.get("userAccount") == W:
                raw = ch.get("rawTokenAmount") or {}
                amt = int(raw.get("tokenAmount") or 0)
                dec = raw.get("decimals") or 0
                mint = ch.get("mint")
                if mint and mint != WSOL:
                    hit = (mint, amt / (10 ** dec))
                break
        if hit:
            break
    if not hit:
        continue
    mint, qty = hit
    sol_out = sol_in = 0
    for nt in (t.get("nativeTransfers") or []):
        if (nt.get("fromUserAccount") or "") == W:
            sol_out += (nt.get("amount") or 0)
        if (nt.get("toUserAccount") or "") == W:
            sol_in += (nt.get("amount") or 0)
    side = "buy" if sol_out > sol_in else "sell"
    lots.append({"sig": (t.get("signature") or "")[:16], "ts": t.get("timestamp"),
                 "side": side, "mint": mint, "qty": qty,
                 "sol_out": sol_out / 1e9, "sol_in": sol_in / 1e9})

print(f"owner-delta lots: {len(lots)}")
print("sides:", dict(Counter(l["side"] for l in lots)))
for l in lots[:10]:
    ts = datetime.datetime.fromtimestamp(
        l["ts"] or 0, datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M")
    print(f"  {ts} {l['side']:<5} {l['mint'][:8]:<10} qty={l['qty']:>14,.0f} "
          f"sol_out={l['sol_out']:.3f} sol_in={l['sol_in']:.3f}")

Path("/home/hermes/project-theia/compute/_suqh_lots.json").write_text(json.dumps(lots))
print("saved _suqh_lots.json")
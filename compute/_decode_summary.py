#!/usr/bin/env python3
"""Decode focus summary: the four whales' trade-visibility via the v2 method.

Method: Helius ENHANCED api, accountData.tokenBalanceChanges where
userAccount == wallet (owner), signed by the SOL leg (nativeTransfers in/out).
v1 (tokenTransfers) missed all of these. Now quantify per whale what we can see.
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=7))
data = json.load(open("/home/hermes/project-theia/compute/_whale_lots_v2.json"))

print(f"{'wallet':<22} {'txs':>5} {'lots':>5} {'buys':>4} {'sells':>5} {'real':>5} {'mints':>5} {'net SOL':>9}")
for w, d in data.items():
    lots = d["lots"]
    buys = [l for l in lots if l["side"] == "buy"]
    sells = [l for l in lots if l["side"] == "sell"]
    real = [l for l in lots if l["sol_out"] > 0.01 or l["sol_in"] > 0.01]
    net = sum(l["sol_in"] - l["sol_out"] for l in lots)
    mints = set(l["mint"] for l in lots)
    tag = {"2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5[wash+105k]",
           "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin[wash+96k]",
           "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8[wash+20k]"}.get(w, w[:10])
    print(f"{tag:<22} {d['txs_scanned']:>5} {len(lots):>5} {len(buys):>4} {len(sells):>5} "
          f"{len(real):>5} {len(mints):>5} {net:>+9.2f}")

# 6G8 deep dive: PnL by mint from SOL legs (its own flows — the only fully-decoded whale)
print("\n== 6G8 net SOL per mint (own SOL in-out) ==")
per_mint = defaultdict(float)
lots = data["6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk"]["lots"]
for l in lots:
    per_mint[l["mint"]] += l["sol_in"] - l["sol_out"]
pos = sorted(per_mint.items(), key=lambda kv: -kv[1])
print(f"mints net+ : {sum(1 for _, v in pos if v > 0)} | mints net- : {sum(1 for _, v in pos if v < 0)}")
total = sum(v for _, v in pos)
print(f"total net SOL across {len(pos)} mints: {total:+.2f}")
for mint, v in pos[:8]:
    print(f"  {mint[:10]:<12} net={v:+.3f} SOL")
print(f"  ... bottom: {[(m[:8], round(v,2)) for m, v in pos[-3:]]}")
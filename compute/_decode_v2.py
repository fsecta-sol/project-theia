#!/usr/bin/env python3
"""Decode 2fg5 + ardin + 6G8 via enhanced-API accountData.tokenBalanceChanges
(the method that worked for suqh). Bounded: 15 pages x 100 txs per wallet."""
import datetime
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

WSOL = "So11111111111111111111111111111111111111112"
OUT = Path("/home/hermes/project-theia/compute/_whale_lots_v2.json")
TARGETS = [
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
    ("6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk", "6G8"),
]
PAGES = 15

out = {}
for w, tag in TARGETS:
    txs, before = [], None
    for page in range(PAGES):
        url = (m.ENHANCED + f"/addresses/{w}/transactions?api-key={m._key()}&limit=100"
               + (f"&before={before}" if before else ""))
        batch = None
        for attempt in range(3):
            try:
                batch = m.request_json(url, throttle=("helius-enh", 0.6)) or []
                break
            except Exception as e:
                print(f"  {tag} page{page} attempt{attempt}: {type(e).__name__} — retrying")
                time.sleep(4 * (attempt + 1))
        if batch is None:
            break
        txs += batch
        before = batch[-1].get("signature")
        if len(batch) < 100:
            break
    lots = []
    for t in txs:
        hit = None
        for x in (t.get("accountData") or []):
            for ch in (x.get("tokenBalanceChanges") or []):
                if ch.get("userAccount") == w:
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
            if (nt.get("fromUserAccount") or "") == w:
                sol_out += (nt.get("amount") or 0)
            if (nt.get("toUserAccount") or "") == w:
                sol_in += (nt.get("amount") or 0)
        side = "buy" if sol_out > sol_in else "sell"
        lots.append({"sig": (t.get("signature") or "")[:16], "ts": t.get("timestamp"),
                     "side": side, "mint": mint, "qty": qty,
                     "sol_out": sol_out / 1e9, "sol_in": sol_in / 1e9})
    real = [l for l in lots if l["sol_out"] > 0.01 or l["sol_in"] > 0.01]
    sides = Counter(l["side"] for l in lots)
    mints = set(l["mint"] for l in lots)
    oldest = min((t.get("timestamp") or 0) for t in txs) if txs else 0
    print(f"{tag:<6} txs={len(txs)} lots={len(lots)} ({dict(sides)}) "
          f"real_SOL_leg={len(real)} mints={len(mints)} oldest="
          f"{datetime.datetime.fromtimestamp(oldest, datetime.timezone(datetime.timedelta(hours=7))).strftime('%m-%d %H:%M') if oldest else '-'}")
    out[w] = {"txs_scanned": len(txs), "lots": lots}

OUT.write_text(json.dumps(out))
print("\nsaved _whale_lots_v2.json")
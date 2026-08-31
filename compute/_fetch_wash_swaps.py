#!/usr/bin/env python3
"""Fetch deeper swap history for the 4 whale wallets (bounded, cached)."""
import importlib.util
import json
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

WHALES = {
    "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5",
    "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh",
    "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin",
    "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8",
}
PATH = Path("/home/hermes/project-theia/compute/_wash_follow_swaps.json")
out = json.loads(PATH.read_text()) if PATH.exists() else {}

for w, tag in WHALES.items():
    got = None
    for attempt in range(3):
        try:
            swaps = m.wallet_swaps(w, pages=6, max_age_s=30 * 86400)
            if isinstance(swaps, list):
                got = swaps
                break
        except Exception as e:
            print(f"{tag} attempt{attempt}: {type(e).__name__} {str(e)[:60]}")
            time.sleep(4)
    if got is not None and len(got) > len(out.get(w) or []):
        out[w] = got
    cur = out.get(w) or []
    buys = [s for s in cur if s.get("side") == "buy" and s.get("base_mint")]
    mints = set(s.get("base_mint") for s in buys)
    print(f"{tag:<6} total={len(cur):>5} buys={len(buys):>4} mints={len(mints)}")
    PATH.write_text(json.dumps(out))
    time.sleep(2)

print("saved")
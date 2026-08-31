#!/usr/bin/env python3
"""Retry fetch for 2fg5/suqh/ardin without max_age_s (avoid cached empty windows)."""
import importlib.util
import json
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TARGETS = [
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
    ("suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK", "suqh"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
]
PATH = Path("/home/hermes/project-theia/compute/_wash_follow_swaps.json")
out = json.loads(PATH.read_text()) if PATH.exists() else {}

for w, tag in TARGETS:
    best = out.get(w) or []
    for kw in ({"pages": 8}, {"pages": 8, "max_age_s": 60 * 86400}):
        try:
            swaps = m.wallet_swaps(w, **kw)
            n = len(swaps) if isinstance(swaps, list) else 0
            if n > len(best):
                best = swaps
            buys = [s for s in (swaps or []) if s.get("side") == "buy" and s.get("base_mint")]
            mints = set(s.get("base_mint") for s in buys)
            print(f"{tag:<6} kw={kw}: total={n} buys={len(buys)} mints={len(mints)}")
        except Exception as e:
            print(f"{tag:<6} kw={kw}: ERR {type(e).__name__} {str(e)[:50]}")
        time.sleep(3)
    out[w] = best
    PATH.write_text(json.dumps(out))

print("saved")
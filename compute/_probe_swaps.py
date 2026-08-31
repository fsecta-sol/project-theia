#!/usr/bin/env python3
"""Probe: do 2fg5/suqh/ardin return swaps without max_age_s window?"""
import importlib.util

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TARGETS = [
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
    ("suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK", "suqh"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
]
for w, tag in TARGETS:
    try:
        s = m.wallet_swaps(w, pages=1, max_pages=100)
        n = len(s) if isinstance(s, list) else -1
        sides = {}
        for x in (s or []):
            sides[x.get("side")] = sides.get(x.get("side"), 0) + 1
        print(f"{tag}: pages=1 no-window -> {n} rows, sides={sides}")
    except Exception as e:
        print(f"{tag}: ERR {type(e).__name__} {str(e)[:60]}")
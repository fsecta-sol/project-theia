#!/usr/bin/env python3
"""Probe composition: what tx types/sources dominate suqh & 2fg5 activity?"""
import importlib.util
from collections import Counter

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

for w, tag in [
    ("suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK", "suqh"),
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
]:
    url = m.ENHANCED + f"/addresses/{w}/transactions?api-key={m._key()}&limit=100"
    txs = m.request_json(url, throttle=("helius-enh", 0.6)) or []
    types = Counter(t.get("type") for t in txs)
    srcs = Counter(t.get("source") for t in txs)
    n_tt = sum(1 for t in txs if (t.get("tokenTransfers") or []))
    n_swap_ev = sum(1 for t in txs if (t.get("events") or {}).get("swap"))
    print(f"{tag:<6} raw={len(txs)} types={dict(types)}")
    print(f"       sources={dict(srcs)}")
    print(f"       txs_with_tokenTransfers={n_tt} txs_with_events.swap={n_swap_ev}")
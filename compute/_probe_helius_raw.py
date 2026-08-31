#!/usr/bin/env python3
"""Probe raw Helius transactions for suqh/ardin — why does wallet_swaps return 0?"""
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path("/home/hermes/.hermes/theia/mcp/common")))

# get a Helius key the same way the MCP does — from the repo .secret file
env_file = Path("/home/hermes/project-theia/.secret")
KEYS = []
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip().startswith("HELIUS_API_KEY"):
            KEYS = [k.strip() for k in line.split("=", 1)[1].split(",") if k.strip()]
            break
if not KEYS:
    print("no helius key found in .secret")
    sys.exit(1)

TARGETS = [
    ("suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK", "suqh"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
]
for w, tag in TARGETS:
    url = (f"https://api.helius.xyz/v0/addresses/{w}/transactions"
           f"?api-key={KEYS[0]}&limit=25")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            txs = json.loads(resp.read())
    except Exception as e:
        print(f"{tag}: HTTP ERR {e}")
        continue
    print(f"{tag}: raw txs={len(txs)}")
    if txs:
        types = Counter(t.get("type") for t in txs)
        print(f"   types: {dict(types)}")
        # check description of a swap-looking one
        for t in txs[:3]:
            print(f"   [{t.get('type')}] {(t.get('description') or '')[:90]}")

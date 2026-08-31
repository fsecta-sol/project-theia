#!/usr/bin/env python3
"""What IS suqh's account on-chain? (wallet vs token-mint vs program)"""
import json
import urllib.request

W = "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK"
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                   "params": [W, {"encoding": "jsonParsed"}]}).encode()
req = urllib.request.Request(
    "https://api.mainnet-beta.solana.com", data=body,
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=20) as resp:
    r = json.loads(resp.read())
val = (r.get("result") or {}).get("value") or {}
if not val:
    print("account does not exist on-chain (never initialized as SOL account?)")
else:
    owner = val.get("owner")
    data = val.get("data")
    # jsonParsed may return data as [type, dict] or {"type":..,"parsed":..}
    dtype = data[0] if isinstance(data, list) else (data.get("type") if isinstance(data, dict) else None)
    parsed = data[1] if isinstance(data, list) else (data.get("parsed") if isinstance(data, dict) else {})
    print("owner program:", owner, "| data type:", dtype)
    print("parsed:", json.dumps(parsed)[:500])

# same for ardin and 2fg5
for w, tag in [("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
               ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5")]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                       "params": [w, {"encoding": "jsonParsed"}]}).encode()
    req = urllib.request.Request("https://api.mainnet-beta.solana.com", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        r = json.loads(resp.read())
    val = (r.get("result") or {}).get("value") or {}
    print(f"\n{tag}: exists={bool(val)}", end=" ")
    if val:
        data = val.get("data")
        dtype = data[0] if isinstance(data, list) else (data.get("type") if isinstance(data, dict) else None)
        print("owner:", val.get("owner"), "data.type:", dtype)
    else:
        print("(no on-chain account)")

"""creator_resolve.py — robust pump.fun creator resolution for M-05 POC C.

WORKAROUND variant (mission tool-building privilege, 2026-08-22):
The live theia-chainrpc token_creator (server.py) cannot resolve creators on
this Helius setup:
  - getParsedTransaction -> {"code": -32601, "message": "Method not found"}
  - pump.fun frontend API fallback -> Cloudflare HTTP 530 (blocked)
So we implement an equivalent resolver with the SAME semantics (oldest
transaction for the mint -> find pump.fun create -> extract creator) but on
endpoints that WORK on this key:
  - getSignaturesForAddress (works, max 1000/page, paginate to oldest)
  - getTransaction with encoding=jsonParsed (works; jsonParsed exposes
    parsed instructions incl. Token-2022 initializeMint)
  - parsed instruction 'initializeMint' contains info.authority — the
    authority that initialized the mint is the creator for pump.fun tokens
    (create path: user == authority).
  - fallback: first account of the oldest tx / sole signer.

Rate-limited with the same theia_net throttle + DiskCache (cache key
'creator:{mint}' collides with the server's own cache — same semantics,
24h TTL, creator never changes). Deterministic: oldest-first ordering.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/hermes/.hermes/theia/mcp/theia-chainrpc")
sys.path.insert(0, "/home/hermes/.hermes/theia/mcp/common")

import server  # noqa: E402
from theia_net import request_json  # noqa: E402

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPFUN_API = "https://frontend-api.pump.fun/coins"

MAX_PAGES = 20  # 20k sigs — plenty for any mint; stops at first page <1000


def _fetch_oldest_sig(mint: str) -> dict | None:
    """Oldest signature for the mint (create tx is the mint's first tx)."""
    last = None
    for _ in range(MAX_PAGES):
        params = [mint, {"limit": 1000, "before": last}] if last else [mint, {"limit": 1000}]
        r = request_json(f"{server.RPC}/?api-key={server._key()}", method="POST",
                         body={"jsonrpc": "2.0", "id": 1,
                               "method": "getSignaturesForAddress", "params": params},
                         throttle=("helius-rpc", 0.6))
        res = (r or {}).get("result", [])
        if not res:
            return None
        if len(res) < 1000:
            return res[-1]
        last = res[-1].get("signature")
    return None


def _get_tx_jsonparsed(sig: str) -> dict | None:
    r = request_json(f"{server.RPC}/?api-key={server._key()}", method="POST",
                     body={"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                           "params": [sig, {"maxSupportedTransactionVersion": 0,
                                             "encoding": "jsonParsed"}]},
                     throttle=("helius-rpc", 0.6))
    return (r or {}).get("result")


def _creator_from_create_tx(tx: dict) -> str | None:
    """Creator from the mint's create tx: initializeMint authority (Token/Token-2022)."""
    if not tx:
        return None
    msg = tx.get("transaction", {}).get("message", {})
    if not isinstance(msg, dict):
        return None
    account_keys = msg.get("accountKeys", [])
    if isinstance(account_keys, list) and account_keys and isinstance(account_keys[0], dict):
        account_keys = [k.get("pubkey", "") for k in account_keys]

    def _auth_of(ins) -> str | None:
        parsed = ins.get("parsed") or {}
        if parsed.get("type") in ("initializeMint", "initializeMint2"):
            info = parsed.get("info") or {}
            auth = info.get("mintAuthority") or info.get("authority")
            if auth and auth in account_keys:
                return auth
            return auth or None
        return None

    for ins in msg.get("instructions", []):
        a = _auth_of(ins)
        if a:
            return a
    # inner instructions
    for group in tx.get("meta", {}).get("innerInstructions", []):
        for ins in group.get("instructions", []):
            a = _auth_of(ins)
            if a:
                return a
    # fallback: pump.fun program present -> account[0] is the user
    for ins in msg.get("instructions", []):
        if PUMPFUN_PROGRAM in ins.get("programId", ""):
            accts = ins.get("accounts") or []
            if accts and isinstance(accts[0], int) and 0 <= accts[0] < len(account_keys):
                return account_keys[accts[0]]
    return None


def token_creator_robust(mint: str, use_fallback_pumpfun: bool = True) -> dict:
    """Resolve creator wallet for a mint. Mirrors server.token_creator semantics.

    Returns {mint, creator_wallet, creation_slot, creation_ts, source}.
    """
    ckey = f"creator:{mint}"
    hit = server.cache.get(ckey, ttl=86400)
    if hit is not None and hit.get("source") != "creator-resolve-null":
        return hit
    if hit is not None:  # previously resolved NULL with this exact variant
        return hit

    result = {"mint": mint, "creator_wallet": None, "creation_slot": 0,
              "creation_ts": 0, "source": None}

    try:
        oldest = _fetch_oldest_sig(mint)
        if oldest and oldest.get("signature"):
            tx = _get_tx_jsonparsed(oldest["signature"])
            creator = _creator_from_create_tx(tx) if tx else None
            if creator:
                result.update({"creator_wallet": creator,
                               "creation_slot": oldest.get("slot", 0),
                               "creation_ts": oldest.get("blockTime", 0),
                               "source": "helius_robust"})
                server.cache.set(ckey, result)
                return result
            result["creation_slot"] = oldest.get("slot", 0)
            result["creation_ts"] = oldest.get("blockTime", 0)
    except Exception:
        pass

    # Fallback: pump.fun API (likely Cloudflare-blocked but keep for parity)
    if use_fallback_pumpfun:
        try:
            pu = request_json(f"{PUMPFUN_API}/{mint}", throttle=("pumpfun", 1.0)) or {}
            creator = pu.get("creator")
            if creator:
                result["creator_wallet"] = creator
                result["source"] = "pumpfun_api"
                server.cache.set(ckey, result)
                return result
        except Exception:
            pass

    result["source"] = "creator-resolve-null"
    server.cache.set(ckey, result)
    return result


if __name__ == "__main__":
    mints = sys.argv[1:]
    for m in mints:
        t0 = time.time()
        r = token_creator_robust(m)
        print(m, "->", r.get("creator_wallet"), r.get("source"),
              f"({round(time.time()-t0,1)}s)", flush=True)

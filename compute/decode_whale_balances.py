#!/usr/bin/env python3
"""Decode-focused: rebuild whale swap history from Helius meta pre/postTokenBalances.

Uses getTransaction JSON with base64 encoding (public RPC getAccountInfo says
the wallets are plain System accounts; the ENHANCED API's enriched view hides
their trading). meta.preTokenBalances/postTokenBalances diffs, filtered to the
wallet as OWNER, are the ground truth — works for bonding-curve txs that
tokenTransfers misses.

Rate: public RPC getTransaction = 1 req, bounded to N txs per wallet.
Output: normalized lots like wallet_swaps (ts, side, mint, qty, price if SOL leg known).
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

WSOL = "So11111111111111111111111111111111111111112"
RPC = "https://api.mainnet-beta.solana.com"
# If a Helius key is present, prefer it (higher rate limits + enriched txs).
KEY = ""
secret = Path("/home/hermes/project-theia/.secret")
if secret.exists():
    for line in secret.read_text().splitlines():
        if line.strip().startswith("HELIUS_API_KEY"):
            KEY = line.split("=", 1)[1].split(",")[0].strip()
RPCS = ([f"https://mainnet.helius-rpc.com/?api-key={KEY}"] if KEY else []) + [RPC]

TARGETS = [
    ("suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK", "suqh"),
    ("ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT", "ardin"),
    ("2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f", "2fg5"),
    ("6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk", "6G8"),
]


def rpc_call(method, params):
    for url in RPCS:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                r = json.loads(resp.read())
        except Exception as e:
            print(f"  rpc {url.split('?')[0]} err: {str(e)[:80]}")
            continue
        if "error" in r:
            continue
        return r.get("result")
    return None


def sig_list(wallet, limit=100):
    res = rpc_call("getSignaturesForAddress", [wallet, {"limit": limit}])
    return [(s.get("signature"), s.get("blockTime"), s.get("err")) for s in (res or [])]


def decode_tx(sig, wallet):
    """Decode buy/sell lots for `wallet` from a raw getTransaction."""
    res = rpc_call("getTransaction", [sig, {"encoding": "jsonParsed",
                                            "maxSupportedTransactionVersion": 0}])
    if not res:
        return []
    meta = res.get("meta") or {}
    if meta.get("err"):
        return []
    pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or [])}
    post = {b["accountIndex"]: b for b in (meta.get("postTokenBalances") or [])}
    # map accountIndex -> owner
    acct_keys = (res.get("transaction") or {}).get("message") or {}
    keys = acct_keys.get("accountKeys") or []
    # jsonParsed gives dicts with pubKey
    if keys and isinstance(keys[0], dict):
        pubkeys = [k.get("pubkey") for k in keys]
    else:
        pubkeys = keys

    deltas = {}  # mint -> raw delta for the wallet
    sol_delta = 0.0
    for idx in range(len(pubkeys)):
        owner = ((pre.get(idx) or {}).get("owner") or (post.get(idx) or {}).get("owner"))
        pk = pubkeys[idx]
        p = pre.get(idx)
        q = post.get(idx)
        if owner == wallet or pk == wallet:
            if p and q and p.get("mint") == q.get("mint"):
                amt_p = (p.get("uiTokenAmount") or {}).get("amount") or "0"
                amt_q = (q.get("uiTokenAmount") or {}).get("amount") or "0"
                d = int(amt_q) - int(amt_p)
                if d != 0:
                    deltas[p["mint"]] = deltas.get(p["mint"], 0) + d
            nb = (meta.get("preBalances") or [])[idx] if idx < len(meta.get("preBalances") or []) else 0
            na = (meta.get("postBalances") or [])[idx] if idx < len(meta.get("postBalances") or []) else 0
            if pk == wallet:
                sol_delta = na - nb
    lots = []
    ts = res.get("blockTime")
    for mint, d in deltas.items():
        if mint == WSOL:
            continue
        info = post.get(0) or {}
        # decimals from post balances
        dec = None
        for b in (meta.get("postTokenBalances") or []):
            if b.get("mint") == mint:
                dec = (b.get("uiTokenAmount") or {}).get("decimals")
                break
        qty = d / (10 ** dec) if dec is not None else d
        lots.append({"sig": sig, "ts": ts, "side": "buy" if d > 0 else "sell",
                     "mint": mint, "qty": qty, "sol_delta_lamports": sol_delta})
    return lots


def main():
    per_wallet = {}
    for w, tag in TARGETS:
        sigs = sig_list(w, limit=60)
        lots_all = []
        tried = 0
        for sig, ts, err in sigs:
            if err:
                continue
            if tried >= 40:
                break
            tried += 1
            lots_all += decode_tx(sig, w)
        buys = [l for l in lots_all if l["side"] == "buy"]
        sells = [l for l in lots_all if l["side"] == "sell"]
        mints = set(l["mint"] for l in buys)
        per_wallet[w] = lots_all
        print(f"{tag:<6} sigs={len(sigs)} tried={tried} lots={len(lots_all)} "
              f"buys={len(buys)} sells={len(sells)} mints={len(mints)}")
        if buys:
            b = buys[0]
            print(f"   sample buy: mint={b['mint'][:8]} qty={b['qty']:.2f} ts={b['ts']}")

    Path("/home/hermes/project-theia/compute/_whale_lots_decoded.json").write_text(
        json.dumps(per_wallet))
    print("\nsaved _whale_lots_decoded.json")


if __name__ == "__main__":
    main()
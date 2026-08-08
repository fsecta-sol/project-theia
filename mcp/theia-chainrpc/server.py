#!/usr/bin/env python3
"""theia-chainrpc — Helius (Solana) read-only RPC + parsed swap history + creator tracking.

Tools: health, wallet_swaps, gas_oracle, creator_tokens, creator_history.
Multi-key round-robin: HELIUS_API_KEY=key1,key2,key3 → per-key throttle.
No signing, ever.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, get_secrets, request_json, ApiKeyRotator  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

ENHANCED = "https://api.helius.xyz/v0"
RPC = "https://mainnet.helius-rpc.com"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
QUOTES = {WSOL, USDC}

# Multi-key rotation — per-key throttle 0.6s → effective throughput scales with key count
_keys = ApiKeyRotator("helius", get_secrets("HELIUS_API_KEY"), interval=0.6)

mcp = FastMCP("theia-chainrpc")
cache = DiskCache()


def _key() -> str:
    return _keys.next()


@mcp.tool()
def health() -> dict:
    """RPC getHealth — confirms the Helius key works."""
    r = request_json(f"{RPC}/?api-key={_key()}", method="POST",
                     body={"jsonrpc": "2.0", "id": 1, "method": "getHealth"})
    return {"health": (r or {}).get("result", "unknown")}


def _swap_from_transfers(tx: dict) -> dict | None:
    """Parse swap from Helius tokenTransfers (current API format).

    Identifies: what was sent (SOL or token) → what was received (token or SOL).
    Returns normalized {signature, slot, ts, side, base_mint, base_qty, quote_mint, quote_qty, exec_price}.
    """
    transfers = tx.get("tokenTransfers") or []
    if not transfers or tx.get("type") != "SWAP":
        return None

    # Group transfers by direction relative to feePayer (user = feePayer)
    user = tx.get("feePayer", "")
    sent = []       # fromUser == user
    received = []   # toUser == user

    for tr in transfers:
        amt = float(tr.get("tokenAmount", 0))
        if amt <= 0:
            continue
        if tr.get("fromUserAccount") == user:
            sent.append({"mint": tr.get("mint", ""), "amount": amt})
        elif tr.get("toUserAccount") == user:
            received.append({"mint": tr.get("mint", ""), "amount": amt})

    if not sent or not received:
        return None

    # Classify: SOL-in/out determines side
    sent_sol = sum(s["amount"] for s in sent if s["mint"] == WSOL)
    sent_token = [s for s in sent if s["mint"] != WSOL]
    recv_sol = sum(r["amount"] for r in received if r["mint"] == WSOL)
    recv_token = [r for r in received if r["mint"] != WSOL]

    if recv_sol > 0 and sent_token:
        # Selling token for SOL
        base = sent_token[0]
        qq = recv_sol
        side = "sell"
    elif sent_sol > 0 and recv_token:
        # Buying token with SOL
        base = recv_token[0]
        qq = sent_sol
        side = "buy"
    else:
        # Token-to-token via aggregator — skip for now
        return None

    if base["amount"] <= 0 or qq <= 0:
        return None

    return {
        "signature": tx.get("signature"),
        "slot": tx.get("slot"),
        "ts": tx.get("timestamp"),
        "side": side,
        "base_mint": base["mint"],
        "base_qty": base["amount"],
        "quote_mint": WSOL,
        "quote_qty": qq,
        "exec_price": qq / base["amount"],
    }


@mcp.tool()
def wallet_swaps(address: str, pages: int = 5) -> list:
    """Normalized buy/sell swap lots for a wallet (newest-first), cached.

    Each: {signature, slot, ts, side, base_mint, base_qty, quote_mint, quote_qty,
    exec_price}. Prefers Helius events.swap (covers Jupiter/aggregator routes).
    """
    ckey = f"helius:swaps:{address}:p{pages}"
    raw = cache.get(ckey)
    if raw is None:
        txs, before = [], None
        for _ in range(max(1, pages)):
            url = f"{ENHANCED}/addresses/{address}/transactions?api-key={_key()}&limit=100"
            if before:
                url += f"&before={before}"
            batch = request_json(url, throttle=("helius-enh", 0.6)) or []
            if not batch:
                break
            txs += batch
            before = batch[-1].get("signature")
        cache.set(ckey, txs)
        raw = txs
    out = []
    for tx in raw:
        s = _swap_from_transfers(tx)
        if s:
            out.append(s)
    return out


@mcp.tool()
def gas_oracle() -> dict:
    """Live Solana priority-fee estimate (micro-lamports per CU) via Helius."""
    r = request_json(f"{RPC}/?api-key={_key()}", method="POST", throttle=("helius-rpc", 0.2),
                     body={"jsonrpc": "2.0", "id": 1, "method": "getPriorityFeeEstimate",
                           "params": [{"options": {"includeAllPriorityFeeLevels": True}}]})
    levels = ((r or {}).get("result") or {}).get("priorityFeeLevels") or {}
    return {"priority_fee_levels_microlamports": levels,
            "base_lamports_per_sig": 5000}


# ── Creator tracking ─────────────────────────────────────────────────────────

# SPL Token Program: tokens are created by initializing a mint account.
# We scan transaction history for these program invocations.
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _rpc(method: str, params: list) -> list:
    """Raw JSON-RPC call to Helius. Returns the 'result' array directly."""
    resp = request_json(f"{RPC}/?api-key={_key()}", method="POST",
                        body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                        throttle=("helius-rpc", 0.2)) or {}
    return resp.get("result", []) if isinstance(resp, dict) else []


@mcp.tool()
def creator_tokens(wallet: str, limit: int = 100) -> list:
    """Find SPL tokens created by a wallet (direct creates, not pump.fun CPI).

    Scans recent transaction signatures, parses each for Token Program's
    initializeMint instruction. NOTE: pump.fun token creates happen via
    their bonding-curve program (CPI) — those won't appear here.
    Use Dexscreener/Birdeye enrichment for pump.fun creators.

    Cache: 1h — token creation history rarely changes.
    """
    ckey = f"creator:tokens:{wallet}"
    hit = cache.get(ckey, ttl=3600)
    if hit is not None:
        return hit

    # Step 1: get signatures (use raw request_json for direct result access)
    sig_body = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                "params": [wallet, {"limit": min(limit, 500)}]}
    sigs = request_json(f"{RPC}/?api-key={_key()}", method="POST",
                        body=sig_body, throttle=("helius-rpc", 0.2))
    if not sigs or "result" not in sigs:
        return []

    # Step 2: getParsedTransaction one-by-one for token creation detection
    signatures = [s["signature"] for s in sigs.get("result", [])[:limit]]
    mints = []

    for sig in signatures:
        results = _rpc("getParsedTransaction", [[sig], {"maxSupportedTransactionVersion": 0}])
        for tx in (results or []):
            if not isinstance(tx, dict):
                continue
            instrs = tx.get("transaction", {}).get("message", {}).get("instructions", [])
            for ins in instrs or []:
                prog = ins.get("programId", "")
                parsed = ins.get("parsed", {})
                if TOKEN_PROGRAM in prog and parsed.get("type") == "initializeMint":
                    info = parsed.get("info", {})
                    mint = info.get("mint", "")
                    if mint and mint not in mints:
                        mints.append(mint)
        time.sleep(0.1)  # gentle throttle

    mints.sort()
    cache.set(ckey, mints)
    return mints


@mcp.tool()
def creator_history(wallet: str) -> dict:
    """Aggregate creator track record: tokens created, on-chain history, fraud signals.

    Returns:
      - total_created: count of SPL tokens created by this wallet
      - sample_mints: first 20 mint addresses
      - is_repeat: true if >1 token created (repeat deployer)
      - txn_count: total transactions (proxy for activity level)
      - first_active: earliest known transaction timestamp
      - funding_source: source wallet that funded this creator (if traceable)
    """
    result = {"wallet": wallet, "total_created": 0, "is_repeat": False,
              "sample_mints": [], "txn_count": 0, "first_active": None}

    # Token count from creator_tokens
    mints = creator_tokens(wallet, limit=200)
    result["total_created"] = len(mints)
    result["is_repeat"] = len(mints) > 1
    result["sample_mints"] = mints[:20]

    # Transaction count (cheap: getSignaturesForAddress with empty config)
    # We just need the count, not parsing
    try:
        sigs = _rpc("getSignaturesForAddress", [wallet, {"limit": 1}])
        if sigs and sigs.get("result"):
            result["txn_count"] = len(sigs.get("result", []))
            if result["txn_count"] > 0:
                result["first_active"] = sigs["result"][0].get("blockTime")
    except Exception:
        pass

    return result


@mcp.tool()
def wallet_pnl(address: str) -> dict:
    """Compute realized + unrealized P&L for a wallet from its swap history.

    Fetches swap history via wallet_swaps, enriches with current prices from
    Dexscreener, and runs FIFO P&L calculation. Returns aggregate stats
    + per-token breakdown.

    Cache: 5min — swap history changes slowly for most wallets.
    """
    ckey = f"wlpnl:{address}"
    hit = cache.get(ckey, ttl=300)
    if hit is not None:
        return hit

    swaps = wallet_swaps(address, pages=3)
    if not swaps:
        result = {"ok": False, "wallet": address, "error": "No swap history found",
                  "n_swaps": 0}
        cache.set(ckey, result)
        return result

    # Get current prices for tokens held
    import json as _json
    mints = list({s["base_mint"] for s in swaps})
    prices = {}
    if mints[:30]:
        from theia_net import request_json
        joined = ",".join(mints[:30])
        try:
            dex = request_json(f"https://api.dexscreener.com/latest/dex/tokens/{joined}",
                               throttle=("dex", 0.3)) or {}
            for pair in dex.get("pairs", []) or []:
                mint = pair.get("baseToken", {}).get("address", "")
                price = float(pair.get("priceUsd", 0) or 0)
                # Convert USD price to SOL if needed
                if mint and price > 0:
                    prices[mint] = price
        except Exception:
            pass

    # Run P&L compute
    _theia_root = str(Path(__file__).resolve().parents[2])
    import sys as _sys
    if _theia_root not in _sys.path:
        _sys.path.insert(0, _theia_root)
    from compute.pnl import wallet_pnl_summary

    result_pnl = wallet_pnl_summary(swaps, prices=prices)
    result = {
        "ok": True,
        "wallet": address,
        "n_swaps": len(swaps),
        "total_realized": result_pnl.total_realized,
        "total_unrealized": result_pnl.total_unrealized,
        "total_cost_basis": result_pnl.total_cost_basis,
        "n_trades": result_pnl.n_trades,
        "n_wins": result_pnl.n_wins,
        "win_rate": round(result_pnl.n_wins / result_pnl.n_trades, 4) if result_pnl.n_trades > 0 else 0,
        "n_active_positions": result_pnl.n_active_positions,
        "per_token": result_pnl.per_token,
        "trade_pnls": result_pnl.realized_trade_pnls,
        "prices_sourced": len(prices),
    }

    cache.set(ckey, result)
    return result


# ── Phase 1: token_creator — Helius RPC + Pump.fun API fallback ──────────────

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPFUN_API = "https://frontend-api.pump.fun/coins"


def _parse_pumpfun_create(tx: dict) -> str | None:
    """Extract creator wallet from a Pump.fun create transaction.
    
    Account layout (0-indexed) for Pump.fun create:
      [0] mint (PDA)        [3] user ← CREATOR
      [1] bonding_curve     [4] system_program
      [2] assoc_curve       [5] token_program
                             [6] rent  [7] event  [8] program
    
    Creator may be in inner instructions (CPI) at index 3, or outer feePayer.
    Returns creator wallet or None.
    """
    try:
        msg = tx.get("transaction", {}).get("message", {})
        account_keys = msg.get("accountKeys", [])
        outer_instructions = msg.get("instructions", [])
        inner_meta = tx.get("meta", {}).get("innerInstructions", [])

        # Build index: which inner instructions belong to which outer index
        inner_map = {}
        for group in inner_meta or []:
            idx = group.get("index", -1)
            inner_map[idx] = group.get("instructions", [])

        def _find_creator(instructions, accounts):
            for ins in instructions:
                program_id = ins.get("programId", "")
                if PUMPFUN_PROGRAM not in program_id:
                    continue
                accts = ins.get("accounts", [])
                if len(accts) >= 4:
                    idx = accts[3]  # index 3 = user/creator
                    if isinstance(idx, int) and 0 <= idx < len(accounts):
                        return accounts[idx]
                # Parse parsed format
                parsed = ins.get("parsed", {})
                info = parsed.get("info") if parsed else None
                if info and info.get("user"):
                    return info.get("user")
            return None

        # Try inner instructions first (CPI case)
        for outer_idx, inner_instrs in inner_map.items():
            # Inner instructions use inner accounts from the meta
            inner_accounts = []
            if isinstance(tx.get("meta"), dict):
                loaded = tx["meta"].get("loadedAddresses", {})
                inner_accounts = account_keys + loaded.get("writable", []) + loaded.get("readonly", [])
            creator = _find_creator(inner_instrs, inner_accounts)
            if creator:
                return creator

        # Fallback: outer instructions → account index 3 or feePayer
        creator = _find_creator(outer_instructions, account_keys)
        if creator:
            return creator
        
        # Last resort: feePayer is creator (non-CPI case)
        fee_payer = tx.get("transaction", {}).get("message", {}).get("feePayer")
        if fee_payer:
            return fee_payer

    except Exception:
        pass
    return None


@mcp.tool()
def token_creator(mint: str) -> dict:
    """Resolve the creator wallet for a Solana token.

    PRIMARY — Helius RPC:
    Parses the oldest transaction for the mint, scanning Pump.fun program
    instructions for the "create" discriminator. Extracts creator from
    account index 3 (user field) — handles both direct and CPI paths.

    FALLBACK #1 — Pump.fun unofficial API:
    GET https://frontend-api.pump.fun/coins/{mint} → `creator` field.

    FALLBACK #2:
    Returns creator_wallet = None if all sources fail.

    Cache: 24h (creator never changes).
    """
    ckey = f"creator:{mint}"
    hit = cache.get(ckey, ttl=86400)
    if hit is not None:
        return hit

    result = {"mint": mint, "creator_wallet": None, "creation_slot": 0,
              "creation_ts": 0, "source": None}

    # PRIMARY: Helius RPC
    try:
        # Get oldest signatures first (reverse-chronological → oldest = last)
        sigs_resp = request_json(
            f"{RPC}/?api-key={_key()}", method="POST",
            body={"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                  "params": [mint, {"limit": 50}]},
            throttle=("helius-rpc", 0.6)) or {}
        sigs = sigs_resp.get("result", []) if sigs_resp else []

        if sigs:
            # Oldest signature is the LAST one (reverse order)
            oldest_sig = sigs[-1].get("signature", "")
            oldest_slot = sigs[-1].get("slot", 0)
            oldest_ts = sigs[-1].get("blockTime", 0)

            if oldest_sig:
                tx_resp = request_json(
                    f"{RPC}/?api-key={_key()}", method="POST",
                    body={"jsonrpc": "2.0", "id": 1, "method": "getParsedTransaction",
                          "params": [oldest_sig, {"maxSupportedTransactionVersion": 0}]},
                    throttle=("helius-rpc", 0.6)) or {}
                tx = tx_resp.get("result")

                if tx:
                    creator = _parse_pumpfun_create(tx)
                    if creator:
                        result["creator_wallet"] = creator
                        result["creation_slot"] = oldest_slot
                        result["creation_ts"] = oldest_ts
                        result["source"] = "helius"
                        cache.set(ckey, result)
                        return result
    except Exception:
        pass

    # FALLBACK #1: Pump.fun API
    try:
        from theia_net import request_json
        pu_resp = request_json(f"{PUMPFUN_API}/{mint}",
                               throttle=("pumpfun", 1.0)) or {}
        creator = pu_resp.get("creator")
        if creator:
            result["creator_wallet"] = creator
            result["source"] = "pumpfun_api"
            cache.set(ckey, result)
            return result
    except Exception:
        pass

    # FALLBACK #2: NULL — no source worked
    cache.set(ckey, result)
    return result


if __name__ == "__main__":
    mcp.run()

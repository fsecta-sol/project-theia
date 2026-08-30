#!/usr/bin/env python3
"""Source-2 concept-test runner (grounded thresholds).

Runs the Dexscreener-trending → Birdeye-top_traders discovery filter once over
live data and reports, per h24/h6 threshold, how many tokens/wallets pass — so
the thresholds are chosen from data, not guessed.

Usage:
    python cron/test_source2.py [--pages N] [--max-tokens N] [--dry]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path.home() / ".hermes/theia/theia.db"
BAD_TAGS = {"bundler", "dev", "sniper", "chef", "fresh", "smart_trader", "bot", "wash_trader"}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def token_passes(pool, h24_min, h6_min, liq_min=30000, mcap_max=50e6):
    attrs = pool.get("attributes") or {}
    pct = attrs.get("price_change_percentage") or {}
    h24 = _f(pct.get("h24"))
    h6 = _f(pct.get("h6"))
    if h24 < h24_min and h6 < h6_min:
        return False, f"h24={h24:.0f} h6={h6:.0f}"
    liq = _f(attrs.get("reserve_in_usd"))
    if liq < liq_min:
        return False, f"liq=${liq:.0f}"
    mcap = attrs.get("market_cap_usd")
    if mcap is not None and _f(mcap) > mcap_max:
        return False, f"mcap=${_f(mcap)/1e6:.0f}M"
    # quote must be SOL or USDC
    rel = pool.get("relationships") or {}
    quote_id = ((rel.get("quote_token") or {}).get("data") or {}).get("id", "")
    if "So11111111111111111111111111111111111111112" not in quote_id and "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" not in quote_id:
        return False, "quote_not_sol_usdc"
    return True, "ok"


def wallet_passes(t, min_trade=5):
    tags = {str(tg).lower() for tg in (t.get("tags") or [])}
    if tags & BAD_TAGS:
        return False, f"tag:{sorted(tags & BAD_TAGS)}"
    rpnl = _f(t.get("realizedPnl"))
    if rpnl <= 0:
        return False, f"rpnl={rpnl:.1f}"
    tr = int(t.get("trade") or 0)
    if tr < min_trade:
        return False, f"trade={tr}"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=30)
    ap.add_argument("--dry", action="store_true", help="skip top_traders (only token filter)")
    args = ap.parse_args()

    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")

    # ── 1. trending pools (paginate) ────────────────────────────────────────
    pools = []
    for page in range(1, args.pages + 1):
        try:
            batch = dexdata.trending_pools(network="solana", page=page) or []
            pools.extend(batch)
            print(f"[trending] page {page}: {len(batch)} pools", flush=True)
            if len(batch) < 20:
                break
        except Exception as e:
            print(f"[trending] page {page} err: {e}", flush=True)
    print(f"[trending] total {len(pools)} pools", flush=True)

    # ── 2. token filter sweep ───────────────────────────────────────────────
    thresholds = [(0, 0), (50, 50), (100, 100), (200, 100), (300, 0)]
    print("\n=== Token filter sweep (liq>=30k, mcap<50M, SOL/USDC) ===")
    for h24_min, h6_min in thresholds:
        passed = [p for p in pools if token_passes(p, h24_min, h6_min)[0]]
        print(f"  h24>={h24_min} & h6>={h6_min}: {len(passed)}/{len(pools)} tokens")
    # pick the working threshold for the next stage
    H24, H6 = 50, 50
    toks = [p for p in pools if token_passes(p, H24, H6)[0]][: args.max_tokens]
    print(f"\n[stage2] using h24>={H24} & h6>={H6}: {len(toks)} tokens selected", flush=True)

    if args.dry:
        return

    # ── 3. top_traders per token + wallet filter ────────────────────────────
    all_wallets = {}
    per_token = {}
    n_tok_err = 0
    for i, p in enumerate(toks):
        mint = ((p.get("relationships") or {}).get("base_token") or {}).get("data", {}).get("id", "")
        mint = mint.replace("solana_", "")
        name = (p.get("attributes") or {}).get("name", "?")
        if not mint:
            continue
        try:
            traders = birdeye.top_traders(token_addr=mint, time_frame="24h", limit=10)
        except Exception as e:
            n_tok_err += 1
            print(f"  [{i+1}/{len(toks)}] {name[:12]} top_traders err: {type(e).__name__}", flush=True)
            continue
        clean = []
        for t in traders or []:
            ok, why = wallet_passes(t)
            if ok:
                clean.append(t.get("owner"))
                all_wallets[t.get("owner")] = all_wallets.get(t.get("owner"), 0) + 1
        per_token[mint] = {"name": name, "clean": clean}
        print(f"  [{i+1}/{len(toks)}] {name[:14]:<14} clean={len(clean)}/{len(traders or [])}", flush=True)
        time.sleep(0.5)

    # ── 4. summary ──────────────────────────────────────────────────────────
    multi = {w: c for w, c in all_wallets.items() if c >= 2}
    print(f"\n=== RESULT ===")
    print(f"tokens processed: {len(toks)} (err {n_tok_err})")
    print(f"unique clean wallets: {len(all_wallets)}")
    print(f"  appearing in >=2 tokens: {len(multi)}")
    for w, c in sorted(multi.items(), key=lambda kv: -kv[1]):
        print(f"    {w} x{c}")

    # overlap with existing
    con = sqlite3.connect(DB)
    sm = {r[0] for r in con.execute("SELECT wallet FROM wallet_profiles WHERE is_smart_money=1")}
    con.close()
    new = set(all_wallets) - sm
    print(f"overlap with existing smart wallets: {len(set(all_wallets) & sm)}")
    print(f"NEW wallets (not yet tracked): {len(new)}")

    out = {"ts": int(time.time()), "h24_min": H24, "h6_min": H6,
           "tokens": {m: v["name"] for m, v in per_token.items()},
           "clean_wallets": all_wallets}
    Path("/home/hermes/project-theia/artifacts").mkdir(exist_ok=True)
    Path("/home/hermes/project-theia/artifacts/source2_test_run.json").write_text(
        json.dumps(out, indent=1, default=str))
    print("saved artifacts/source2_test_run.json", flush=True)


if __name__ == "__main__":
    main()

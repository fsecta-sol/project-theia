#!/usr/bin/env python3
"""Progressive OHLCV+pool backfill for the AFK re-backtest (Track A batch-2).

Goal: build a representative cached dataset for the wallet-follow backtest by
fetching OHLCV + pool info for the 604 mints bought by smart-tracked wallets.
Fully respects the free-tier rate budget: GeckoTerminal ~30 req/min shared
through the pipeline's RateLimiter; pool resolve is cached; DexScreener bars as
fallback for live windows.

This script is designed to be RESUMABLE: every mint's OHLCV+pool is cached to
disk, so re-running skips anything already fetched. Run it in the background,
poll progress, then re-run the backtest on the grown cache.

Usage:
    python cron/backfill_ohlcv.py [--max-mints N] [--only-tracked]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from concurrent import futures
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path.home() / ".hermes/theia/theia.db"
WSOL = "So11111111111111111111111111111111111111112"


def _load_wallet_common():
    for p in (Path(__file__).resolve().parent / "wallet_common.py",
              Path("/home/hermes/project-theia/cron/wallet_common.py"),
              Path("/home/hermes/theia-gate/wallet_common.py")):
        if p.exists():
            spec = importlib.util.spec_from_file_location("wallet_common", p)
            if spec is None or spec.loader is None:
                continue
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("wallet_common.py not found")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mints", type=int, default=0)
    ap.add_argument("--only-tracked", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wc = _load_wallet_common()
    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

    # mints bought by (tracked) wallets
    con = sqlite3.connect(DB)
    tracked = {r[0] for r in con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1")}
    con.close()
    swaps = json.loads((DATA / "discovery_swaps.json").read_text())
    mints = set()
    for w, txs in swaps.items():
        if args.only_tracked and w not in tracked:
            continue
        if not isinstance(txs, list):
            continue
        for t in txs:
            if t.get("side") == "buy" and t.get("quote_mint") == WSOL and t.get("base_mint"):
                mints.add(t["base_mint"])
    mints = sorted(mints)
    if args.max_mints:
        mints = mints[: args.max_mints]
    print(f"[backfill] {len(mints)} mints to ensure-cached", flush=True)

    OHLCV_DIR = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
    POOLS_DIR = Path.home() / ".hermes/theia/wallet_cache/pools"

    def _has_ohlcv(mint):
        return any(mint in f.name for f in OHLCV_DIR.iterdir())

    def _has_pool(mint):
        return (POOLS_DIR / f"{mint}.json").exists()

    todo = [m for m in mints if not _has_ohlcv(m)]
    print(f"[backfill] {len(todo)} missing OHLCV, {len(mints)-len(todo)} already cached",
          flush=True)
    if args.dry_run:
        return
    if not todo:
        print("[backfill] nothing to do", flush=True)
        return

    done = 0
    failed = 0
    t0 = time.time()

    # oldest buy ts per mint (to anchor the deep window)
    oldest_buy = {}
    for w, txs in swaps.items():
        if args.only_tracked and w not in tracked:
            continue
        if not isinstance(txs, list):
            continue
        for t in txs:
            if t.get("side") == "buy" and t.get("quote_mint") == WSOL and t.get("base_mint"):
                ts = int(t.get("ts") or 0)
                if ts:
                    oldest_buy[t["base_mint"]] = min(oldest_buy.get(t["base_mint"], ts), ts)

    def _fetch(mint):
        # pool first (cached by resolve_pool), then OHLCV deep window anchored
        # at the oldest buy so the pre-entry peak window is covered.
        try:
            info = wc.resolve_pool(dexdata, mint)
            if not info:
                return mint, "no_pool"
            ob = oldest_buy.get(mint, 0)
            # before_ts = oldest buy + 4h: covers the buy..entry..exit span.
            # Gecko caps at 1000 rows (~16.7h of 1m candles) — one call is enough.
            wc.gecko_ohlcv_for(dexdata, mint,
                               before_ts=(ob + 4 * 3600) if ob else 0, ttl=86400)
            return mint, "ok"
        except Exception as e:
            return mint, f"err:{type(e).__name__}"

    with futures.ThreadPoolExecutor(max_workers=3) as ex:
        for mint, status in ex.map(_fetch, todo):
            done += 1
            if status != "ok":
                failed += 1
            if done % 25 == 0:
                el = time.time() - t0
                print(f"[backfill] {done}/{len(todo)} ({status}) "
                      f"{el/60:.1f}min elapsed", flush=True)

    el = time.time() - t0
    print(f"[backfill] done {done}/{len(todo)} ok={done-failed} failed={failed} "
          f"{el/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()

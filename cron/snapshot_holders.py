#!/usr/bin/env python3
"""Snapshot top-holder concentration into early_holders (Track B).

GoPlus token_security returns a `holders` array with per-holder `percent` (of
total supply) — the exact "top-10 holders pegang berapa % supply" signal. This
script extracts it for a set of mints and stores into `early_holders`, including
a computed `top10_pct` so downstream rules (screen_score / backtests) can use it.

Rate/cache: GoPlus is keyless, ~30/min, cached 24h by the MCP server. We fetch
the full 604 mint set once; every write is idempotent (INSERT OR REPLACE on
(mint, wallet)).

Usage:
    python cron/snapshot_holders.py [--max-mints N] [--mints M1,M2] [--dry-run]
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
WSOL = "So11111111111111111111111111111111111111112"


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
    ap.add_argument("--mints", type=str, default="", help="comma-separated mint list")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    security = load("security", DEPLOY / "theia-security" / "server.py")

    # resolve target mints
    if args.mints:
        mints = [m.strip() for m in args.mints.split(",") if m.strip()]
    else:
        con = sqlite3.connect(DB)
        tracked = {r[0] for r in con.execute(
            "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1")}
        con.close()
        swaps = json.loads((Path.home() / "theia-gate/data/discovery_swaps.json").read_text())
        mints = set()
        for w, txs in swaps.items():
            if w not in tracked:
                continue
            if not isinstance(txs, list):
                continue
            for t in txs:
                if t.get("side") == "buy" and t.get("quote_mint") == WSOL and t.get("base_mint"):
                    mints.add(t["base_mint"])
        mints = sorted(mints)
    if args.max_mints:
        mints = mints[: args.max_mints]
    print(f"[holders] {len(mints)} mints to snapshot", flush=True)

    con = sqlite3.connect(DB)
    now = int(time.time())
    done = found = no_data = 0
    failures = []

    for mint in mints:
        try:
            res = security.token_security(mint)
        except Exception as e:
            failures.append((mint, f"{type(e).__name__}:{e}"))
            continue
        done += 1
        if not res or not res.get("found"):
            no_data += 1
            continue
        raw = res.get("raw") or {}
        holders = raw.get("holders") or []
        total_supply = float(raw.get("total_supply") or 0)
        top10 = 0.0
        for h in holders:
            pct = float(h.get("percent") or 0)
            top10 += pct
            if args.dry_run:
                continue
            amt = float(h.get("balance") or 0)
            con.execute(
                """INSERT OR REPLACE INTO early_holders
                   (mint, wallet, amount_usd, pct_of_supply, first_seen_ts, source)
                   VALUES (?,?,?,?,?,?)""",
                (mint, h.get("account"), amt, pct, now, "goplus_holders"))
        # store a top10 summary row (wallet='__TOP10__') for fast downstream lookup
        if not args.dry_run and holders:
            con.execute(
                """INSERT OR REPLACE INTO early_holders
                   (mint, wallet, amount_usd, pct_of_supply, first_seen_ts, source)
                   VALUES (?,?,?,?,?,?)""",
                (mint, "__TOP10__", None, round(top10, 6), now, "goplus_top10"))
            con.commit()
        found += 1
        if done % 20 == 0:
            print(f"[holders] {done}/{len(mints)} found={found} nodata={no_data}", flush=True)

    con.close()
    print(f"[holders] done={done}/{len(mints)} found={found} nodata={no_data} "
          f"failures={len(failures)}", flush=True)
    if failures:
        print("  sample failures:", failures[:3], flush=True)


if __name__ == "__main__":
    main()

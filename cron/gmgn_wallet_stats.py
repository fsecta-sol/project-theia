#!/usr/bin/env python3
"""Scrape GMGN wallet analytics page data (standalone, CF-bypass).

The wallet page https://gmgn.ai/sol/address/{addr} is client-rendered; the real
data comes from the CF-protected API:
    https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period={p}

CF bypass requires the browser tier. The MCP server's StealthyFetcher fails with
"Playwright Sync API inside asyncio loop" (async context), so this script runs
StealthyFetcher in a STANDALONE process (proven working 2026-08-29).

Usage:
    # single
    python cron/gmgn_wallet_stats.py --addr <wallet> [--period 7d]
    # backfill a list
    python cron/gmgn_wallet_stats.py --addrs-file /tmp/addrs.txt [--period 7d] [--cache]
    # list what's cached
    python cron/gmgn_wallet_stats.py --cache --list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Pull in the webscraper venv's scrapling (this script should be run with it)
try:
    from scrapling.fetchers import StealthyFetcher
except ImportError:
    print("ERROR: run with the theia-webscraper venv python:\n"
          "  /home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python",
          file=sys.stderr)
    sys.exit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period={period}"


def fetch_wallet(addr: str, period: str = "7d", timeout_ms: int = 45000) -> dict:
    """Fetch GMGN wallet analytics. Returns the parsed JSON (full response)."""
    url = API.format(addr=addr, period=period)
    sf = StealthyFetcher()
    resp = sf.fetch(url, solve_cloudflare=True, timeout=timeout_ms,
                    headless=True, network_idle=False, load_dom=False)
    if resp.status != 200:
        return {"ok": False, "status": resp.status, "addr": addr, "period": period}
    body = resp.body if hasattr(resp, "body") else b""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return {"ok": False, "status": resp.status, "addr": addr, "period": period,
                "raw": body[:500].decode("utf-8", errors="replace")}
    return {"ok": True, "status": resp.status, "addr": addr, "period": period, "data": data}


def cache_path(addr: str, period: str) -> Path:
    return CACHE_DIR / f"{addr}_{period}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", type=str, default="")
    ap.add_argument("--period", type=str, default="7d")
    ap.add_argument("--addrs-file", type=str, default="")
    ap.add_argument("--cache", action="store_true", help="use/save cache")
    ap.add_argument("--list", action="store_true", help="list cached addrs")
    args = ap.parse_args()

    if args.list:
        for f in sorted(CACHE_DIR.glob("*.json")):
            print(f.name)
        return

    if args.addr:
        addrs = [args.addr]
    elif args.addrs_file:
        addrs = [a.strip() for a in Path(args.addrs_file).read_text().splitlines() if a.strip()]
    else:
        print("need --addr or --addrs-file")
        sys.exit(1)

    results = []
    for i, addr in enumerate(addrs):
        cp = cache_path(addr, args.period)
        if args.cache and cp.exists():
            r = json.loads(cp.read_text())
            print(f"[{i+1}/{len(addrs)}] {addr[:16]}... (cached)")
            results.append(r)
            continue
        try:
            r = fetch_wallet(addr, args.period)
        except Exception as e:
            r = {"ok": False, "addr": addr, "period": args.period, "err": str(e)}
        results.append(r)
        if r.get("ok"):
            print(f"[{i+1}/{len(addrs)}] {addr[:16]}... "
                  f"rPnl7d={r['data'].get('data', {}).get('realized_profit_7d')}")
            if args.cache:
                cp.write_text(json.dumps(r))
        else:
            print(f"[{i+1}/{len(addrs)}] {addr[:16]}... FAIL {r.get('status') or r.get('err')}")
        time.sleep(1.5)  # be gentle; browser launches are heavy

    out = Path.home() / "theia-gate/data/gmgn_wallet_stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    print(f"\nsaved {len(results)} results → {out}")


if __name__ == "__main__":
    main()

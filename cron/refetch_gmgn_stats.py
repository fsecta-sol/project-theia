#!/usr/bin/env python3
"""Refetch FULL GMGN wallet stats (30d + 7d) for all smart wallets, no cache.

walletNew 7d cache from source2-era is incomplete (winrate missing for
non-GMGN-tracked). Fetch fresh 30d AND 7d so we have the authoritative
numbers (realized_profit, winrate if provided, buy/sell counts) to filter on.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:
    from scrapling.fetchers import StealthyFetcher
except ImportError:
    print("ERROR: run with theia-webscraper venv", file=sys.stderr)
    sys.exit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period={period}"
DB = Path.home() / ".hermes/theia/theia.db"


def fetch_wallet(addr: str, period: str, timeout_ms: int = 45000) -> dict:
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
                "raw": body[:400].decode("utf-8", errors="replace")}
    return {"ok": True, "addr": addr, "period": period, "data": data}


def main():
    con = sqlite3.connect(DB)
    wallets = [r[0] for r in con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1")]
    con.close()
    print(f"smart wallets to refetch: {len(wallets)}")

    ok = 0
    for i, w in enumerate(wallets):
        got = {}
        for period in ("7d", "30d"):
            try:
                r = fetch_wallet(w, period)
            except Exception as e:
                r = {"ok": False, "addr": w, "period": period, "err": str(e)}
            if r.get("ok"):
                got[period] = r
                ok += 1
            time.sleep(1.5)
        if got:
            out = Path.home() / f"theia-gate/data/gmgn_refetch_{w[:12]}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(got))
            inner7 = ((got.get("7d") or {}).get("data") or {}).get("data") or {}
            inner30 = ((got.get("30d") or {}).get("data") or {}).get("data") or {}
            print(f"[{i+1}/{len(wallets)}] {w[:14]} "
                  f"rPnl7d={inner7.get('realized_profit_7d')} rPnl30d={inner30.get('realized_profit_30d')} "
                  f"win7d={inner7.get('winrate')} buy30={inner7.get('buy_30d')} sell30={inner7.get('sell_30d')}")
        else:
            print(f"[{i+1}/{len(wallets)}] {w[:14]} ALL FAIL")
    print(f"\ndone ok={ok}/{len(wallets)*2}")


if __name__ == "__main__":
    main()
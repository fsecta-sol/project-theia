#!/usr/bin/env python3
"""Reprocess dex_trending wallets' GMGN stats: fetch fresh stats, update wallet_profiles.

Fixes: dex_trending wallets were upserted by discover_source2 WITHOUT win_rate /
profit_factor / distribution columns (they're 0.00 in the DB), because source2
only fills those from GMGN leaderboard rows, not from walletNew stats.

Uses the same GMGN walletNew API as gmgn_wallet_stats.py (standalone, CF-bypass),
then UPDATEs wallet_profiles with the real numbers.
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
    print("ERROR: run with theia-webscraper venv:\n"
          "  /home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python", file=sys.stderr)
    sys.exit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period={period}"
DB = Path.home() / ".hermes/theia/theia.db"


def fetch_wallet(addr: str, period: str = "7d", timeout_ms: int = 45000) -> dict:
    url = API.format(addr=addr, period=period)
    sf = StealthyFetcher()
    resp = sf.fetch(url, solve_cloudflare=True, timeout=timeout_ms,
                    headless=True, network_idle=False, load_dom=False)
    if resp.status != 200:
        return {"ok": False, "status": resp.status, "addr": addr}
    body = resp.body if hasattr(resp, "body") else b""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return {"ok": False, "status": resp.status, "addr": addr,
                "raw": body[:400].decode("utf-8", errors="replace")}
    return {"ok": True, "addr": addr, "data": data}


def main():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1 AND source='dex_trending'"
    ).fetchall()
    wallets = [r[0] for r in rows]
    print(f"dex_trending smart wallets to reprocess: {len(wallets)}")

    updated = 0
    failed = 0
    for i, w in enumerate(wallets):
        cp = CACHE_DIR / f"{w}_7d.json"
        if cp.exists():
            r = json.loads(cp.read_text())
            print(f"[{i+1}/{len(wallets)}] {w[:16]} (cached)")
        else:
            try:
                r = fetch_wallet(w, "7d")
            except Exception as e:
                r = {"ok": False, "addr": w, "err": str(e)}
            if r.get("ok"):
                cp.write_text(json.dumps(r))
            time.sleep(1.5)
        if not r.get("ok"):
            failed += 1
            print(f"  FAIL {r.get('status') or r.get('err')}")
            continue

        d = r.get("data") or {}
        # response shape: {code,msg,data:{...wallet stats...}}
        data = d.get("data") or {} if isinstance(d, dict) else {}
        if not isinstance(data, dict):
            data = {}
        # fields we can map (verify against actual payload keys)
        wr = data.get("winrate")
        pf = data.get("profit_factor")
        rp7 = data.get("realized_profit_7d")
        buys = data.get("buy_30d")
        sells = data.get("sell_30d")
        # distribution buckets if present (winrate can be derived from them)
        dist = {k: data.get(k) for k in ("pnl_gt_5x_num", "pnl_2x_5x_num", "pnl_lt_2x_num",
                                          "pnl_minus_dot5_0x_num", "pnl_lt_minus_dot5_num")}
        if wr is None and any(dist.values()):
            wins = (dist.get("pnl_gt_5x_num") or 0) + (dist.get("pnl_2x_5x_num") or 0) + (dist.get("pnl_lt_2x_num") or 0)
            losses = (dist.get("pnl_minus_dot5_0x_num") or 0) + (dist.get("pnl_lt_minus_dot5_num") or 0)
            if wins + losses > 0:
                wr = wins / (wins + losses)

        con.execute(
            "UPDATE wallet_profiles SET win_rate=?, profit_factor=?, total_trades=?, "
            "total_buys=?, total_sells=?, updated_ts=? WHERE wallet=?",
            (wr if wr is not None else 0, pf if pf is not None else 0,
             (buys or 0) + (sells or 0) if buys is not None or sells is not None else None,
             buys, sells, int(time.time()), w))
        con.commit()
        updated += 1
        print(f"  -> winrate={wr} pf={pf} rPnl7d={rp7} buy30={buys} sell30={sells}")

    con.close()
    print(f"\ndone: updated={updated} failed={failed}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""theia-birdeye — DISCOVERY source only (never a source of P&L truth).

Free Standard tier: token lists, per-coin top traders, global gainers/losers, wallet
PnL. Use to FIND candidate wallets/coins; every number touching a verdict is re-derived
by our own compute libs. Filter candidates by realized_pnl>0 & real trade counts.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, get_secret, request_json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

BASE = "https://public-api.birdeye.so"
BT = ("birdeye", 1.1)  # wallet APIs beta: 5/s,75/min — stay well under

mcp = FastMCP("theia-birdeye")
cache = DiskCache()


def _get(path: str):
    return request_json(f"{BASE}{path}",
                        headers={"X-API-KEY": get_secret("BIRDEYE_API_KEY"), "x-chain": "solana"},
                        throttle=BT)


@mcp.tool()
def token_list(sort_by: str = "v24hUSD", limit: int = 50, offset: int = 0,
               min_liquidity: int = 100000) -> list:
    """Top tokens by volume/mcap. Fields incl. mc, v24hUSD, price, symbol, address."""
    p = (f"/defi/tokenlist?sort_by={sort_by}&sort_type=desc&offset={offset}"
         f"&limit={limit}&min_liquidity={min_liquidity}")
    return ((_get(p) or {}).get("data") or {}).get("tokens") or []


@mcp.tool()
def top_traders(token_addr: str, time_frame: str = "24h", limit: int = 10, offset: int = 0) -> list:
    """Top traders of a coin. Each has owner, realizedPnl, trade/tradeBuy/tradeSell, volume."""
    p = (f"/defi/v2/tokens/top_traders?address={token_addr}&time_frame={time_frame}"
         f"&sort_type=desc&sort_by=volume&offset={offset}&limit={limit}")
    d = (_get(p) or {}).get("data") or {}
    return d.get("items") or d.get("tokens") or []


@mcp.tool()
def gainers_losers(want: str = "gainers", time_frame: str = "1W", limit: int = 10,
                   offset: int = 0) -> list:
    """Global top-PnL wallets. Fields: address, pnl, realized_pnl, trade_count, volume.
    NOTE: dominated by single-trade unrealized holders — filter realized_pnl>0 & trade_count>=N."""
    st = "desc" if want == "gainers" else "asc"
    p = f"/trader/gainers-losers?type={time_frame}&sort_by=PnL&sort_type={st}&offset={offset}&limit={limit}"
    return ((_get(p) or {}).get("data") or {}).get("items") or []


@mcp.tool()
def token_ohlcv(token_addr: str, type: str = "1m", time_from: int = 0,
                time_to: int = 0, limit: int = 1000, offset: int = 0,
                currency: str = "usd") -> list:
    """Birdeye OHLCV candles for a TOKEN (not pool). [ts,o,h,l,c,v,quote] rows.

    Price quote: USD only (Birdeye ignores currency=token → 0 rows). 'v' is
    token qty, 'vUsd' is USD volume. Up to 1000 candles per request — use
    time_from/time_to windows, paginate with offset only if beyond 1000.

    NOTE: Birdeye candles start at the token's first indexed trade
    (lastTradeUnixTime), not at launch. New micro-caps may return 0 candles
    until they have indexed volume — GeckoTerminal is the fallback there.
    """
    if not time_from:
        time_from = int(time.time()) - 24 * 3600
    if not time_to:
        time_to = int(time.time())
    p = (f"/defi/ohlcv?address={token_addr}&type={type}"
         f"&time_from={time_from}&time_to={time_to}"
         f"&currency={currency}&limit={limit}&offset={offset}")
    items = ((_get(p) or {}).get("data") or {}).get("items") or []
    out = []
    for it in items:
        try:
            out.append([int(it.get("unixTime", 0)),
                        float(it.get("o", 0)), float(it.get("h", 0)),
                        float(it.get("l", 0)), float(it.get("c", 0)),
                        float(it.get("v", 0)), it.get("vUsd", 0)])
        except (TypeError, ValueError):
            continue
    return sorted(out, key=lambda r: r[0])


@mcp.tool()
def wallet_pnl(wallet: str) -> dict:
    """Birdeye's own wallet PnL — CROSS-CHECK ONLY, never the source of truth."""
    return (_get(f"/wallet/v2/pnl?wallet={wallet}") or {}).get("data") or {}


if __name__ == "__main__":
    mcp.run()

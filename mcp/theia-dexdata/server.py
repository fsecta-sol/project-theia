#!/usr/bin/env python3
"""theia-dexdata — GeckoTerminal (discovery + OHLCV) + Dexscreener (enrichment).

Keyless. Gecko is throttled ~6s (keyless ~10/min) with jittered backoff; OHLCV in
currency=token so prices match swap quote/base. Cache at this boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, request_json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

GECKO = "https://api.geckoterminal.com/api/v2"
DEX = "https://api.dexscreener.com/latest/dex"
GT = ("gecko", 6.0)

mcp = FastMCP("theia-dexdata")
cache = DiskCache()


def _g(url: str):
    return request_json(url, throttle=GT)


@mcp.tool()
def new_pools(network: str = "solana", page: int = 1) -> list:
    """Newly created pools on a network (discovery)."""
    return (_g(f"{GECKO}/networks/{network}/new_pools?page={page}") or {}).get("data", [])


@mcp.tool()
def trending_pools(network: str = "solana", page: int = 1) -> list:
    """Trending pools on a network (discovery — treat volume as gameable, wash-filter)."""
    return (_g(f"{GECKO}/networks/{network}/trending_pools?page={page}") or {}).get("data", [])


@mcp.tool()
def token_pools(mint: str, network: str = "solana") -> list:
    """Pools for a token, highest-liquidity first."""
    return (_g(f"{GECKO}/networks/{network}/tokens/{mint}/pools") or {}).get("data", [])


@mcp.tool()
def pool_trades(pool_addr: str, network: str = "solana") -> list:
    """Recent individual trades for a pool (last ~300)."""
    addr = _strip_net(pool_addr, network)
    return (_g(f"{GECKO}/networks/{network}/pools/{addr}/trades") or {}).get("data", [])


def _strip_net(pool_addr: str, network: str = "solana") -> str:
    return pool_addr.removeprefix(f"{network}_")


@mcp.tool()
def pool_ohlcv(pool_addr: str, network: str = "solana", timeframe: str = "minute",
               aggregate: int = 1, limit: int = 1000, before_timestamp: int = 0,
               currency: str = "token") -> list:
    """OHLCV [[ts,o,h,l,c,v],...] ascending. currency=token → base priced in quote (SOL).
    Accepts pool addr with or without the gecko network prefix (solana_xxx → xxx)."""
    addr = _strip_net(pool_addr, network)
    url = (f"{GECKO}/networks/{network}/pools/{addr}/ohlcv/{timeframe}"
           f"?aggregate={aggregate}&limit={limit}&currency={currency}&token=base")
    if before_timestamp:
        url += f"&before_timestamp={before_timestamp}"
    data = _g(url) or {}
    rows = (((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
    return sorted(rows, key=lambda r: r[0])


@mcp.tool()
def pairs_by_token(mints: list) -> list:
    """Dexscreener enrichment (price/liq/vol/mcap) for up to 30 token mints."""
    joined = ",".join(mints[:30])
    return (request_json(f"{DEX}/tokens/{joined}", throttle=("dex", 0.3)) or {}).get("pairs", [])


if __name__ == "__main__":
    mcp.run()

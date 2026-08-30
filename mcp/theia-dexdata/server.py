#!/usr/bin/env python3
"""theia-dexdata — GeckoTerminal (discovery + OHLCV) + Dexscreener (enrichment + bars).

Keyless. Gecko is throttled ~6s (keyless ~10/min) with jittered backoff; OHLCV in
currency=token so prices match swap quote/base. Cache at this boundary.

dex_bars: dexscreener's frontend bars endpoint (binary format, CF-gated) — use
curl_cffi to bypass; no browser needed. See module docstring for format.
"""
from __future__ import annotations

import struct
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, request_json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

GECKO = "https://api.geckoterminal.com/api/v2"
DEX = "https://api.dexscreener.com/latest/dex"
IO_DEX = "https://io.dexscreener.com/dex/chart/amm/v3"
GT = ("gecko", 6.0)
DEX_BAR_SCALE = 1_000_000_000  # cs param — prices returned multiplied by this

mcp = FastMCP("theia-dexdata")
cache = DiskCache()


def _g(url: str):
    return request_json(url, throttle=GT)


def _dex_bars_raw(pair: str, dex: str = "pumpfundex", res: int = 15,
                  count: int = 500,
                  quote: str = "So11111111111111111111111111111111111111112",
                  scale: int = DEX_BAR_SCALE) -> bytes:
    """Fetch raw binary bars — urllib first (works from any runtime, CF not
    blocking here), curl_cffi fallback (impersonate chrome) if blocked."""
    u = (f"{IO_DEX}/{dex}/bars/solana/{pair}"
         f"?mc=1&cs={scale}&res={res}&cb={count}&q={quote}&uo=0")
    try:
        req = urllib.request.Request(
            u, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read()
    except Exception:
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(u, impersonate="chrome", timeout=30)
        r.raise_for_status()
        return r.content


def _parse_dex_bars(b: bytes, res_min: int) -> list:
    """Decode dexscreener bars binary format.

    Header '1.0.0'; per bar: 6-byte ts (2 zero pad + LE double epoch-ms) +
    9 length-prefixed ASCII numbers [o, v1, h, v2, l, v3, c, v4, v5] where
    marker byte = 2*len(ascii), separated by optional 0x02. o/h/l/c are
    quote-token price * cs (divide by 1e9); v = base-token volume.
    """
    idx = b.find(b"1.0.0")
    if idx < 0:
        return []
    d = b[idx + 5:]
    step = res_min * 60000
    ts_offsets = []
    for k in range(4, len(d) - 6):
        try:
            v = struct.unpack("<d", b"\x00\x00" + d[k:k + 6])[0]
        except Exception:
            continue
        if 1.0e12 < v < 9.0e12 and (v % step) == 0:
            if not ts_offsets or k - ts_offsets[-1][1] > 20:
                ts_offsets.append((v, k))
    bars = []
    for i, (ts_ms, off) in enumerate(ts_offsets):
        end = ts_offsets[i + 1][1] if i + 1 < len(ts_offsets) else len(d)
        j = off + 6
        nums = []
        while j < end - 2:
            while j < end and d[j] == 0x02:
                j += 1
            if j >= end - 2:
                break
            m = d[j]
            L = m // 2
            if L <= 0 or L > 30 or j + 1 + L > end:
                break
            try:
                f = float(d[j + 1:j + 1 + L])
            except ValueError:
                break
            nums.append(f)
            j += 1 + L
        if len(nums) < 8:
            continue
        o, h, l, c = nums[0], nums[2], nums[4], nums[6]
        v_tok = max(nums[1], nums[3], nums[5], nums[7])
        v_extra = nums[8] if len(nums) >= 9 else 0
        bars.append([round(ts_ms / 1000, 0), o / DEX_BAR_SCALE, h / DEX_BAR_SCALE,
                     l / DEX_BAR_SCALE, c / DEX_BAR_SCALE, v_tok, v_extra])
    return bars


@mcp.tool()
def dex_bars(pair: str, dex: str = "pumpfundex", res: int = 15, count: int = 500,
             quote: str = "So11111111111111111111111111111111111111112") -> list:
    """Dexscreener frontend OHLCV bars (binary, CF-gated). [[ts,o,h,l,c,v_tok,v_extra],...].

    res = bar size in minutes (1/5/15/60/240/1440). cb(=count) = max bars asked.
    res>=15 returns FULL history from pool creation (up to ~150 bars); res=1 only
    last ~30-40 min. o/h/l/c in quote-token (SOL) price; v_tok = base token qty.
    Cloudflare bypassed via curl_cffi — no browser required.
    """
    key = f"dexbars_{pair}_{dex}_{res}_{count}"
    cached = cache.get(key, ttl=120)
    if cached is not None and cached:
        return cached
    try:
        raw = _dex_bars_raw(pair, dex=dex, res=res, count=count, quote=quote)
        bars = _parse_dex_bars(raw, res)
    except Exception:
        bars = []
    if bars:
        cache.set(key, bars)
    return bars


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

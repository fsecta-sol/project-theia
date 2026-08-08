#!/usr/bin/env python3
"""theia-security — GoPlus token safety (Solana). Static screening signals only.

Keyless works (free 30/min). Returns the raw per-mint security dict (mint/freeze
authority, honeypot-ish flags, holder/LP concentration) for the screen-token skill to
turn into wash/rug/screen scores via compute libs. Static ≠ proof — pair with a sim.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, request_json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

GOPLUS = "https://api.gopluslabs.io/api/v1/solana/token_security"
GT = ("goplus", 2.2)  # free 30/min

mcp = FastMCP("theia-security")
cache = DiskCache()


@mcp.tool()
def token_security(mint: str) -> dict:
    """GoPlus Solana token-security for a mint (cached 24h). Raw provider fields.

    Caller derives a verdict; this tool only fetches. Solana coverage is partial —
    treat mint/freeze-authority-revoked + a live sell simulation as the real check.
    """
    ck = f"goplus:{mint}"
    hit = cache.get(ck, ttl=86400)
    if hit is not None:
        return hit
    r = request_json(f"{GOPLUS}?contract_addresses={mint}", throttle=GT) or {}
    result = (r.get("result") or {})
    data = result.get(mint) or result.get(mint.lower()) or {}
    out = {"mint": mint, "found": bool(data), "raw": data}
    cache.set(ck, out)
    return out


if __name__ == "__main__":
    mcp.run()

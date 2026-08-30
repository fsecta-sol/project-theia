#!/usr/bin/env python3
"""Fetch missing trigger-mint OHLCV into the cache so source2 backtest gets coverage."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")
sys.path.insert(0, "/home/hermes/.hermes/profiles/theia/scripts")

from compute.volume_lowbuy_backtest import load_mints  # noqa: E402
from wallet_common import ohlcv_for, _call_with_timeout  # noqa: E402

SWAPS = Path("/home/hermes/project-theia/compute/_dex_trending_swaps.json")

data = json.loads(SWAPS.read_text())
trig_mints = set()
for w, ss in data.items():
    if isinstance(ss, list):
        for s in ss:
            if s.get("side") == "buy" and s.get("base_mint"):
                trig_mints.add(s["base_mint"])

cached = set(load_mints(min_candles=30).keys())
missing = sorted(trig_mints - cached)
print(f"missing mints to fetch: {len(missing)}")


def load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")

fetched = 0
failed = 0
for mint in missing:
    try:
        rows, src = _call_with_timeout(ohlcv_for, dexdata, birdeye, mint, before_ts=0, ttl=300)
        if rows:
            # save into cache dir as a gecko-style file so load_mints picks it up
            cache_dir = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
            f = cache_dir / f"{mint}_{'now'}.json"
            f.write_text(json.dumps({"rows": rows}))
            fetched += 1
            print(f"  + {mint[:14]} rows={len(rows)} src={src}")
        else:
            failed += 1
            print(f"  - {mint[:14]} no rows (src={src})")
    except Exception as e:
        failed += 1
        print(f"  ! {mint[:14]} {type(e).__name__}")
print(f"fetched={fetched} failed={failed}")
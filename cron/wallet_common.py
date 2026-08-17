"""wallet_common — shared helpers for the wallet pipeline (canonical: project-theia/cron).

Fixes addressed here:
  #1  GeckoTerminal sequential + hard sleep(6)  → parallel worker pool + token-bucket rate limit
  #2  HTTP without timeout → hung process      → request_json already retries; we add a hard
                                                 wall-clock tick wrapper + flock single-instance
  #3  Redundant re-fetch of OHLCV/pool         → disk cache (JSON, TTL per use-case)
  #7  DexScreener-missed pool               → token_pools → pairs_by_token fallback
  #8  Tracker pages=1 misses buys              → pages handled in pipeline; here just IO helpers

All scripts that touch Gecko/Helius should use these helpers instead of calling
dexdata/chainrpc directly.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

# ── environment / cache dir ─────────────────────────────────────────────────────
# Deployment scripts live in the profile scripts dir; the dev copies live in
# project-theia/cron. CACHE_DIR is per-user and stable across both.
CACHE_DIR = Path(os.environ.get("THEIA_CACHE", str(Path.home() / ".hermes/theia/wallet_cache")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
for sub in ("ohlcv", "pools", "sol_usd"):
    (CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)

# GeckoTerminal free tier: ~20-30 req/min. We budget 30/min → 2s between requests,
# shared across worker threads.
RATE_PER_SEC = 30.0 / 60.0  # ~1 request per 2 seconds
REQUEST_TIMEOUT = 10.0       # hard ceiling per API call (fixes #2 hang)


class RateLimiter:
    """Token-bucket: one worker at a time, min interval between requests."""

    def __init__(self, per_sec: float = RATE_PER_SEC):
        self._min_interval = 1.0 / per_sec if per_sec > 0 else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            wait = self._last + self._min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()


LIMITER = RateLimiter()


def _cache_path(sub: str, key: str) -> Path:
    safe = key.replace("/", "_")
    return CACHE_DIR / sub / f"{safe}.json"


def _load_cache(sub: str, key: str, ttl: float) -> dict | None:
    p = _cache_path(sub, key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except Exception:
        return None
    if time.time() - data.get("ts", 0) > ttl:
        return None
    return data


def _save_cache(sub: str, key: str, payload) -> None:
    try:
        _cache_path(sub, key).write_text(json.dumps({"ts": time.time(), **payload}))
    except Exception:
        pass


def gecko_ohlcv(dexdata, mint: str, before_ts: int = 0, ttl: float = 60.0):
    """pool_ohlcv with disk cache + rate limit + hard timeout.

    before_ts: end of the historical window (epoch). ttl: 60s for live feeds
    (monitor/screen), >3600 for immutable historical backtests.
    """
    key = f"{mint}_{before_ts // 86400 if before_ts else 'now'}"
    cached = _load_cache("ohlcv", key, ttl)
    if cached:
        return cached["rows"]

    LIMITER.wait()
    # resolve pool first (it's cached too)
    pool_info = _resolve_pool(dexdata, mint, ttl=ttl)
    if not pool_info or not pool_info.get("pool"):
        return []
    pool_addr = pool_info["pool"].replace("solana_", "")
    rows = _call_with_timeout(dexdata.pool_ohlcv, pool_addr, timeframe="minute",
                              aggregate=1, limit=1000,
                              before_timestamp=before_ts, currency="token")
    rows = rows or []
    _save_cache("ohlcv", key, {"rows": rows})
    return rows


def _resolve_pool(dexdata, mint: str, ttl: float = 300.0) -> dict | None:
    key = mint
    cached = _load_cache("pools", key, ttl)
    if cached:
        return cached  # cached already IS the info dict (ts + pool/liq/price/dex)
    LIMITER.wait()
    try:
        pools = _call_with_timeout(dexdata.token_pools, mint)
    except Exception:
        pools = []  # Gecko 404/error → fall through to DexScreener (fix #7)
    info = None
    if pools:
        # highest reserve pool first
        def _liq(p):
            try:
                return float(p.get("attributes", {}).get("reserve_in_usd") or 0)
            except (TypeError, ValueError):
                return 0.0
        pools.sort(key=_liq, reverse=True)
        attr = pools[0].get("attributes", {})
        info = {
            "pool": pools[0].get("id", "").replace("solana_", ""),
            "liq_usd": _liq(pools[0]),
            "price_usd": float(attr.get("base_token_price_usd") or 0),
            "dex_id": attr.get("dex_id") or (pools[0].get("relationships", {})
                                             .get("dex", {}).get("data", {}).get("id", "")),
        }
    if not info:
        # fall 7: DexScreener pairs_by_token
        try:
            dex_res = _call_with_timeout(dexdata.pairs_by_token, [mint]) or []
            for p in dex_res:
                if p.get("baseToken", {}).get("address") == mint:
                    info = {
                        "pool": p.get("pairAddress"),
                        "mint": mint,
                        "liq_usd": (p.get("liquidity") or {}).get("usd", 0),
                        "price_usd": float(p.get("priceUsd") or 0),
                        "dex_id": p.get("dexId") or "",
                    }
                    break
        except Exception:
            pass
    if info:
        _save_cache("pools", key, info)
    return info


def resolve_pool(dexdata, mint):
    return _resolve_pool(dexdata, mint)


def sol_usd(dexdata, ttl: float = 900.0) -> float:
    cached = _load_cache("sol_usd", "sol", ttl)
    if cached:
        return cached["price"]
    LIMITER.wait()
    rows = _call_with_timeout(dexdata.pairs_by_token,
                              ["So11111111111111111111111111111111111111112"]) or []
    price = None
    for p in rows:
        if (p.get("baseToken", {}).get("address") == "So11111111111111111111111111111111111111112"
                and (p.get("quoteToken", {}).get("symbol") or "").upper().startswith("USDC")):
            try:
                price = float(p.get("priceUsd"))
                break
            except (TypeError, ValueError):
                continue
    if not price:
        price = 150.0
    _save_cache("sol_usd", "sol", {"price": price})
    return price


def _call_with_timeout(fn, *args, **kwargs):
    """Wrap a blocking call with a hard timeout via a worker thread."""
    result, error = [], []

    def _run():
        try:
            result.append(fn(*args, **kwargs))
        except Exception as e:  # noqa: BLE001
            error.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(REQUEST_TIMEOUT)
    if t.is_alive():
        raise TimeoutError(f"{getattr(fn, '__name__', fn)} timed out after {REQUEST_TIMEOUT}s")
    if error:
        raise error[0]
    return result[0] if result else None


# ── script single-instance lock (fixes cron overlap, #2) ────────────────────
def script_lock(name: str, timeout_wait: float = 0.0):
    """Context manager: `with script_lock("pipeline"):` — exits if already running."""
    lock_path = CACHE_DIR / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    got = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except BlockingIOError:
            if timeout_wait <= 0:
                raise RuntimeError(f"another {name} instance is running")
            fcntl.flock(fd, fcntl.LOCK_EX)  # wait
            got = True
    except Exception:
        fd.close()
        raise

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                fd.close()
            return False

    return _Ctx() if got else None


def parallel_map(fn, items, workers: int = 3, show_progress=None):
    """Run fn over items with the shared rate-limiter; returns list of (item, result)."""
    from concurrent import futures
    res = []
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, i): i for i in items}
        for fut in futures.as_completed(futs):
            item = futs[fut]
            try:
                res.append((item, fut.result()))
            except Exception as e:  # noqa: BLE001
                res.append((item, None))
            if show_progress and len(res) % 5 == 0:
                show_progress(len(res), len(items))
    return res
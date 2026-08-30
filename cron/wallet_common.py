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
# Hard ceiling per API call (fixes #2 hang). 60s: GeckoTerminal is slow on deep
# OHLCV windows (limit=1000); 10s used to cut off requests that would have
# succeeded, producing mass sim failures (train=0/test=0) in discovery profiling.
REQUEST_TIMEOUT = 60.0


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
    key = f"gecko_{mint}_{before_ts // 86400 if before_ts else 'now'}"
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


def birdeye_ohlcv(birdeye, mint: str, before_ts: int = 0, ttl: float = 60.0,
                  hours: int = 24) -> list:
    """Birdeye token_ohlcv with disk cache + hard timeout.

    Returns the SAME [[ts,o,h,l,c,v],...] row shape as gecko_ohlcv (drops the
    7th 'vUsd' field). before_ts = end of window; window = [before_ts-hours*3600,
    before_ts]. Birdeye indexes candles from a token's first trade (not launch);
    a fresh micro-cap may return [] — gecko fallback handles that.

    NOTE: Birdeye's 1m candles for tokens WITHOUT current volume come back FLAT
    (o=h=l=c constant, v=0) once the token is past its active window — the
    histogram data expires. ohlcv_for() filters those out and falls back to
    Gecko; only active tokens keep birdeye as source.
    """
    key = f"bird_{mint}_{before_ts // 3600 if before_ts else 'now'}_{hours}h"
    cached = _load_cache("ohlcv", key, ttl)
    if cached:
        return cached["rows"]
    LIMITER.wait()
    t_to = before_ts or int(time.time())
    t_from = t_to - hours * 3600
    items = _call_with_timeout(birdeye.token_ohlcv, mint, type="1m",
                               time_from=t_from, time_to=t_to)
    rows = []
    for it in items or []:
        try:
            rows.append([int(it[0]), float(it[1]), float(it[2]),
                         float(it[3]), float(it[4]), float(it[5])])
        except (TypeError, ValueError, IndexError):
            continue
    _save_cache("ohlcv", key, {"rows": rows})
    return rows


def ohlcv_for(dexdata, birdeye, mint: str, before_ts: int = 0, ttl: float = 60.0,
              hours: int = 24, dex_paths: tuple = ("pumpfundex", "raydium", "orca",
                                                    "meteora", "pump")) -> tuple[list, str | None]:
    """OHLCV for one mint: Birdeye first (active coverage), Gecko fallback,
    Dexscreener bars last (res=15 full-history from launch; live window only).

    Birdeye USD-quote candles are fine for chart-condition checks (price caps,
    dip detection) where the pipeline compares ratios/levels, not absolute
    USD amounts. Gecko token-quote is used when Birdeye has no index yet.
    Dexscreener bars (res=15) as a last resort — its endpoint always returns
    history from pool creation and cannot honor before_ts, so it only runs for
    live windows (before_ts=0). dex_paths = dexscreener AMM path variants to
    try (pumpfundex/raydium/orca/meteora/pump), first non-empty wins.
    """
    if birdeye is not None:
        try:
            rows = birdeye_ohlcv(birdeye, mint, before_ts=before_ts, ttl=ttl,
                                 hours=hours)
            # birdeye returns flat/no-trade candles for micro-caps that have
            # index coverage but no real volume — prefer gecko's token-quote
            # candles when the birdeye rows are all zeros/flat (fake coverage)
            if rows:
                active = sum(1 for r in rows
                             if (r[5] or 0) > 0 and r[4] != r[1])
                if active >= max(3, len(rows) // 5):
                    return rows, "birdeye"
        except Exception:
            pass
    try:
        rows = gecko_ohlcv(dexdata, mint, before_ts=before_ts, ttl=ttl)
        if rows:
            return rows, "gecko"
    except Exception:
        pass
    # Dexscreener bars fallback — live only (endpoint returns full history from
    # launch, cannot select a window, so skip historical requests)
    if before_ts == 0 and dexdata is not None:
        try:
            pool_info = _resolve_pool(dexdata, mint, ttl=ttl)
            pool_addr = (pool_info or {}).get("pool")
            if pool_addr:
                for path in dex_paths:
                    try:
                        rows = _call_with_timeout(dexdata.dex_bars, pool_addr,
                                                  dex=path, res=15, count=500)
                        if rows:
                            return rows, f"dex_{path}"
                    except Exception:
                        continue
        except Exception:
            pass
    return [], None


def gecko_ohlcv_for(dexdata, mint: str, before_ts: int = 0, ttl: float = 86400.0,
                    retries: int = 2, retry_delay: float = 5.0) -> list:
    """OHLCV for one mint with bounded retries — the discovery profiler's hot path.

    Discovery profiling fetches the same mint's OHLCV once per buy in the wallet's
    history; with the 60s timeout a single slow Gecko response no longer kills the
    sim, but retrying transient failures here is what turns train=0/test=0 (mass
    sim-dropped) runs into real evaluations. Results are cached under the same key
    as gecko_ohlcv (ttl=86400 = immutable historical window).
    """
    for attempt in range(retries + 1):
        try:
            rows = gecko_ohlcv(dexdata, mint, before_ts=before_ts, ttl=ttl)
            if rows:
                return rows
            # empty result (pool miss / no data yet) — not worth retrying
            return rows
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(retry_delay * (attempt + 1))
    return []


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
        # Gecko exposes reserve_in_usd (total USD) but not per-side reserves;
        # back out base/quote qty from USD value + prices when both available.
        liq_usd = _liq(pools[0])
        price_usd = float(attr.get("base_token_price_usd") or 0)
        quote_px_usd = float(attr.get("quote_token_price_usd") or 0)
        reserves_base = reserves_quote = None
        if price_usd > 0 and quote_px_usd > 0 and liq_usd > 0:
            # quote qty = liq_usd / 2 / quote_px_usd (constant-product: 50/50 value)
            reserves_quote = (liq_usd / 2.0) / quote_px_usd
            reserves_base = (liq_usd / 2.0) / price_usd
        info = {
            "pool": pools[0].get("id", "").replace("solana_", ""),
            "liq_usd": liq_usd,
            "price_usd": price_usd,
            "dex_id": attr.get("dex_id") or (pools[0].get("relationships", {})
                                             .get("dex", {}).get("data", {}).get("id", "")),
            "reserves_base": reserves_base,
            "reserves_quote": reserves_quote,
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
                        # DexScreener liquidity.base/quote = AMM reserves
                        # (base token qty / quote SOL qty) — enables
                        # reconstructable paper fills (fix missing_reserve_snapshot)
                        "reserves_base": (p.get("liquidity") or {}).get("base"),
                        "reserves_quote": (p.get("liquidity") or {}).get("quote"),
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
    # Sanity-check: SOL/USD must be in a realistic range. A value outside
    # 10–10000 means we matched a wrong pair (e.g. inverted or non-USDC quote)
    # — fall back to the last cached value or the hardcoded default.
    if not price or not (10.0 < price < 10_000.0):
        last = _load_cache("sol_usd", "sol", ttl=86400)  # accept stale up to 24h
        price = last["price"] if (last and 10.0 < last.get("price", 0) < 10_000.0) else 150.0
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
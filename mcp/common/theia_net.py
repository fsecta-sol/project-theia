"""Shared net / cache / secrets for Theia data MCP servers. Pure stdlib.

Deployed alongside the servers under ~/.hermes/theia/mcp/common/; each server adds
../common to sys.path. Rate-limit + cache live HERE (the MCP boundary), never in skills.
Secrets read from the process env (Hermes passes them), then ~/.hermes/.env, then a
local .secret for offline testing — never logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

_LAST: dict[str, float] = {}


def _throttle(key: str, interval: float) -> None:
    wait = interval - (time.monotonic() - _LAST.get(key, 0.0))
    if wait > 0:
        time.sleep(wait)
    _LAST[key] = time.monotonic()


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} {url}: {body[:150]}")
        self.status = status


def _scrub(u: str) -> str:
    return u.split("api-key=")[0] + "api-key=<redacted>" if "api-key=" in u else u


def request_json(url, method="GET", headers=None, body=None, throttle=None,
                 retries=5, timeout=25):
    """JSON over HTTP with jittered backoff on 429/5xx and optional per-host throttle."""
    if throttle:
        _throttle(*throttle)
    hdrs = {"Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) theia/0.1",
            **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            btext = e.read().decode(errors="replace") if e.fp else ""
            last = HttpError(e.code, _scrub(url), btext)
            if e.code not in (429, 500, 502, 503, 504):
                raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        if i < retries:
            time.sleep(1.0 * (2 ** i) + random.uniform(0, 1))
    raise last


CACHE_DIR = Path(os.environ.get("THEIA_CACHE", str(Path.home() / ".hermes" / "theia" / "cache")))


class DiskCache:
    def __init__(self, root=None):
        self.root = Path(root or CACHE_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, k: str) -> Path:
        return self.root / f"{hashlib.sha1(k.encode()).hexdigest()}.json"

    def get(self, k, ttl=None):
        p = self._p(k)
        if p.is_file():
            if ttl and (time.time() - p.stat().st_mtime) > ttl:
                return None
            return json.loads(p.read_text())
        return None

    def set(self, k, v):
        self._p(k).write_text(json.dumps(v))

    def cached(self, k, fn, ttl=None):
        hit = self.get(k, ttl)
        if hit is not None:
            return hit
        v = fn()
        self.set(k, v)
        return v


def _load_env_file(p) -> dict:
    d = {}
    try:
        for line in Path(p).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return d


_SECRETS = None


def get_secret(name: str, required: bool = True) -> str:
    """Single key (backward compat). For multi-key rotation use ApiKeyRotator."""
    global _SECRETS
    if os.environ.get(name):
        return os.environ[name]
    if _SECRETS is None:
        _load_all_secrets()
    v = _SECRETS.get(name, "")
    if not v and required:
        raise RuntimeError(f"missing secret {name}")
    return v


def get_secrets(name: str, required: bool = True) -> list[str]:
    """Multi-key: splits by comma, strips whitespace. Returns all configured keys."""
    raw = os.environ.get(name, "")
    if not raw:
        if _SECRETS is None:
            _load_all_secrets()
        raw = _SECRETS.get(name, "")
    if not raw and required:
        raise RuntimeError(f"missing secret {name}")
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _load_all_secrets():
    global _SECRETS
    _SECRETS = {}
    for p in (Path.home() / ".hermes" / ".env",
              Path(__file__).resolve().parents[2] / ".secret"):
        _SECRETS.update(_load_env_file(p))


class ApiKeyRotator:
    """Round-robin across multiple API keys with per-key throttle tracking.

    Usage:
        keys = get_secrets("HELIUS_API_KEY")
        rotator = ApiKeyRotator("helius", keys, interval=0.6)

        # Each call returns the next key
        key = rotator.next()        # → key0
        key = rotator.next()        # → key1
    """

    def __init__(self, name: str, keys: list[str], interval: float = 0.6):
        if not keys:
            raise RuntimeError(f"ApiKeyRotator({name}): no keys provided")
        self.name = name
        self.keys = keys
        self.interval = interval
        self._idx = 0
        self._last_used: dict[str, float] = {}

    def next(self) -> str:
        """Return the next key, throttled per-key."""
        key = self.keys[self._idx]
        self._idx = (self._idx + 1) % len(self.keys)

        # Throttle this specific key
        wait = self.interval - (time.monotonic() - self._last_used.get(key, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_used[key] = time.monotonic()
        return key

    def all_keys(self) -> list[str]:
        return list(self.keys)

    def count(self) -> int:
        return len(self.keys)

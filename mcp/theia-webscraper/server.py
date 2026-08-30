#!/usr/bin/env python3
"""theia-webscraper — tiered web fetch MCP for Theia.

Tier 1: curl_cffi (impersonate Chrome) — fast, ~70% success
Tier 2: StealthyFetcher (Chromium headless) — slow, ~100% success, bypasses CF

All web fetch in Theia goes through this single gate.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from mcp.server.fastmcp import FastMCP
from scrapling.fetchers import StealthyFetcher

mcp = FastMCP("theia-webscraper")

# ── Tier 1: curl_cffi (fast HTTP with Chrome fingerprint) ─────────────────────

def _cf_detected(text: str, status: int) -> bool:
    """Heuristic: is this a Cloudflare challenge/block page?"""
    if status in (403, 429, 503):
        return True
    t = text.lower()
    markers = [
        "cf-turnstile",
        "challenges.cloudflare",
        "cf.challenge",
        "cf-browser-verification",
        "turnstile",
        "just a moment",
        "checking your browser",
        "cf-im-under-attack",
        "cf_captcha",
    ]
    return any(m in t for m in markers)


def _tier1_fetch(url: str, timeout: int = 20) -> tuple[int, str, float]:
    """curl_cffi fetch. Returns (status, text, latency_ms)."""
    t0 = time.time()
    try:
        resp = curl_requests.get(url, impersonate="chrome110", timeout=timeout)
        latency = (time.time() - t0) * 1000
        return resp.status_code, resp.text, latency
    except Exception as e:
        return 0, str(e), (time.time() - t0) * 1000


# ── Tier 2: StealthyFetcher (Chromium headless, CF bypass) ──────────────────

def _tier2_fetch(url: str, timeout: int = 30) -> tuple[int, str, float]:
    """StealthyFetcher fetch. Returns (status, text, latency_ms)."""
    t0 = time.time()
    try:
        sf = StealthyFetcher()
        # solve_cloudflare=True triggers CF challenge solving if present
        resp = sf.fetch(url, solve_cloudflare=True, timeout=timeout * 1000)
        latency = (time.time() - t0) * 1000
        # StealthyFetcher Response: use body (bytes) or text
        text = ""
        if hasattr(resp, "text") and resp.text:
            text = resp.text
        elif hasattr(resp, "body") and resp.body:
            text = resp.body.decode("utf-8", errors="replace")
        elif hasattr(resp, "html_content") and resp.html_content:
            text = resp.html_content
        return resp.status, text, latency
    except Exception as e:
        return 0, str(e), (time.time() - t0) * 1000


# ── Public tools ────────────────────────────────────────────────────────────


@mcp.tool()
def fetch_page(url: str, timeout: int = 30, tier: str = "auto", max_chars: int = 1_000_000) -> dict:
    """Fetch a single URL. Tier: auto | http | browser.

    auto   → try curl_cffi first, fallback to StealthyFetcher on CF/block
    http   → curl_cffi only (fast, no browser)
    browser→ StealthyFetcher only (slow, guaranteed)
    max_chars: response cap (default 1MB; GMGN leaderboards ~100KB so the old
    100KB cap truncated valid JSON mid-token).
    """
    t0 = time.time()

    if tier == "browser":
        status, text, lat1 = _tier2_fetch(url, timeout)
        return {
            "ok": status == 200,
            "status": status,
            "url": url,
            "content": text[:max_chars],  # cap (default 1MB)
            "method": "stealthyfetcher",
            "latency_ms": round(lat1, 1),
            "cf_bypassed": True,
        }

    if tier == "http":
        status, text, lat1 = _tier1_fetch(url, timeout)
        cf = _cf_detected(text, status)
        return {
            "ok": status == 200 and not cf,
            "status": status,
            "url": url,
            "content": text[:max_chars],
            "method": "curl_cffi",
            "latency_ms": round(lat1, 1),
            "cf_detected": cf,
        }

    # auto tier
    status1, text1, lat1 = _tier1_fetch(url, timeout)
    cf1 = _cf_detected(text1, status1)

    if status1 == 200 and not cf1:
        return {
            "ok": True,
            "status": 200,
            "url": url,
            "content": text1[:max_chars],
            "method": "curl_cffi",
            "latency_ms": round(lat1, 1),
            "cf_detected": False,
        }

    # Fallback to tier 2
    status2, text2, lat2 = _tier2_fetch(url, timeout)
    total_latency = lat1 + lat2
    return {
        "ok": status2 == 200,
        "status": status2,
        "url": url,
        "content": text2[:max_chars],
        "method": "stealthyfetcher",
        "latency_ms": round(total_latency, 1),
        "cf_bypassed": status2 == 200,
        "tier1_failed": {"status": status1, "latency_ms": round(lat1, 1)},
    }


@mcp.tool()
def fetch_pages(urls: list[str], max_concurrent: int = 3, timeout: int = 30, tier: str = "auto") -> dict:
    """Batch fetch up to 10 URLs in parallel."""
    urls = urls[:10]
    results = []
    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {pool.submit(fetch_page, u, timeout, tier): u for u in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"ok": False, "url": url, "error": str(e)})
    return {"ok": True, "results": results, "n": len(results)}


@mcp.tool()
def extract_text(html_content: str) -> dict:
    """Strip HTML tags and return clean text."""
    # Remove script/style tags first
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html_content, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Unescape HTML entities
    text = html.unescape(text)
    return {"ok": True, "text": text, "chars": len(text)}


@mcp.tool()
def detect_protection(url: str, timeout: int = 10) -> dict:
    """Quick probe: does this URL serve CF challenge?"""
    status, text, latency = _tier1_fetch(url, timeout)
    cf = _cf_detected(text, status)
    return {
        "ok": True,
        "url": url,
        "cf_detected": cf,
        "status": status,
        "latency_ms": round(latency, 1),
        "needs_browser": cf or status != 200,
    }


if __name__ == "__main__":
    mcp.run()

#!/usr/bin/env python3
"""theia-xscraper — X.com scraping: keyless HTTP (scrapling.Fetcher) for profiles +
twscrape GraphQL (cookie-auth) for full tweet search & timelines.

Phase 1: profile_lookup via Fetcher (no auth, no browser)
Phase 2: search_tweets, user_tweets, user_by_login via twscrape (cookie auth, real API)

Cookie setup: set X_AUTH_TOKEN and X_CT0 env vars, or let the server read from
~/.hermes/.env. Export them from a logged-in browser session (DevTools → Cookies → x.com).
The twscrape account pool is lazy-initialized on first GraphQL call.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from theia_net import DiskCache, get_secret  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("theia-xscraper")
cache = DiskCache()

# Internal rate limiter — stays well under X.com tolerance
_LAST: dict[str, float] = {}

# Lazy twscrape API singleton
_tw_api = None
_tw_ready: bool | None = None  # None = unprobed, True/False = known state


def _throttle(key: str, interval: float):
    wait = interval - (time.monotonic() - _LAST.get(key, 0.0))
    if wait > 0:
        time.sleep(wait)
    _LAST[key] = time.monotonic()


def _get_tw_api():
    """Lazy-init twscrape API with cookie auth. Returns API or None if not configured."""
    global _tw_api, _tw_ready
    if _tw_api is not None:
        return _tw_api
    try:
        auth_token = get_secret("X_AUTH_TOKEN", required=False)
        ct0 = get_secret("X_CT0", required=False)
        if not auth_token or not ct0:
            _tw_ready = False
            return None

        from twscrape import API
        api = API()

        async def _add():
            await api.pool.add_account_cookies(
                "theia",
                f"auth_token={auth_token}; ct0={ct0}"
            )

        asyncio.run(_add())
        _tw_api = api
        _tw_ready = True
        return api
    except Exception:
        _tw_ready = False
        return None


def _run_tw(fn, *args, **kwargs):
    """Run a twscrape async call synchronously, return list or dict."""
    api = _get_tw_api()
    if api is None:
        return None
    try:
        return asyncio.run(fn(api, *args, **kwargs))
    except Exception:
        return None


def _fetch(url: str, ttl: int = 300) -> tuple[str, int]:
    """Fetch with caching + curl-cffi impersonation. Returns (html, status_code)."""
    ck = f"x:{url}"
    hit = cache.get(ck, ttl=ttl)
    if hit is not None:
        return hit["html"], hit["status"]

    _throttle("x", 1.5)  # ~40 req/min max
    from scrapling.fetchers import Fetcher

    try:
        resp = Fetcher.get(url, impersonate="chrome", timeout=20)
        text = resp.body.decode() if resp.body else ""
        status = getattr(resp, "status_code", 200)
    except Exception as e:
        text = ""
        status = -1

    cache.set(ck, {"html": text, "status": status})
    return text, status


def _verify_not_blocked(html: str) -> bool:
    """Check if response is readable X.com, not Cloudflare/block page."""
    if not html:
        return False
    cf = ["Just a moment", "Attention Required", "cf-error-details",
          "challenges.cloudflare.com", "Checking your browser"]
    if any(s.lower() in html.lower() for s in cf):
        return False
    return "x.com" in html[:50000].lower() or "twitter" in html[:1000].lower()


def _extract_profiles(html: str) -> list[dict]:
    """Basic profile extraction from HTML. Returns list of {username, display_name, bio}."""
    from scrapling.parser import Selector
    page = Selector(content=html)
    profiles = []

    # Try structured data first
    scripts = page.css('script[type="application/ld+json"]')
    for s in scripts:
        import json
        try:
            raw = s.get() if hasattr(s, 'get') else str(s)
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("@type") == "Person":
                profiles.append({
                    "username": data.get("additionalName", ""),
                    "display_name": data.get("name", ""),
                    "bio": data.get("description", ""),
                    "followers": data.get("interactionStatistic", [{}])[0].get("userInteractionCount", 0) if data.get("interactionStatistic") else 0,
                })
        except (json.JSONDecodeError, AttributeError):
            pass

    if not profiles:
        # Fallback: extract from HTML
        title = page.css("title::text").get() or ""
        desc = page.css('meta[name="description"]::attr(content)').get() or ""
        profiles.append({"display_name": title.replace(" / X", "").strip(), "bio": desc})

    return profiles


def _extract_tweets(html: str) -> list[dict]:
    """Extract tweet text + author from search/timeline HTML."""
    from scrapling.parser import Selector
    page = Selector(content=html)
    tweets = []

    for article in page.css("article"):
        text_el = article.css('[data-testid="tweetText"]::text') or article.css('[lang] *::text')
        text = text_el.getall() if text_el else []
        user_el = article.css('[data-testid="User-Name"] *::text')
        user = user_el.getall() if user_el else []

        if text:
            tweets.append({
                "text": "".join(text).strip()[:500],
                "user": "".join(user).strip()[:50] if user else "",
            })
    return tweets[:20]


# ── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool()
def profile_lookup(username: str) -> dict:
    """Look up an X.com profile by username. Returns display_name, bio, followers (when available).

    Keyless HTTP — works without cookies. Cached 5min.
    Use for wallet discovery / whale identification.
    """
    url = f"https://x.com/{username}"
    html, status = _fetch(url, ttl=300)
    ok = status == 200 and _verify_not_blocked(html)

    profiles = _extract_profiles(html) if ok else []
    result = {
        "username": username,
        "url": url,
        "http_status": status,
        "ok": ok,
    }
    if profiles:
        result.update(profiles[0])
    else:
        result["title"] = ""
        result["display_name"] = ""

    return result


@mcp.tool()
def search_tweets(query: str, limit: int = 10) -> dict:
    """Search X.com tweets by keyword — FULL via twscrape GraphQL (requires cookie auth).

    Returns parsed tweets with id, user, text, created_at, likes, retweets.
    Rate limit: ~1 req/3s via twscrape's built-in pool rotation. Cache 2min.
    Falls back to keyless HTTP scrape if cookies not configured.
    """
    ckey = f"tw:search:{query}:{limit}"
    hit = cache.get(ckey, ttl=120)
    if hit is not None:
        return hit

    _throttle("tw", 3.0)

    async def _do(api, q, lim):
        from twscrape import gather
        tweets = await gather(api.search(q, limit=lim))
        return [{"id": t.id, "user": t.user.username, "text": t.rawContent,
                 "created_at": str(t.date), "likes": t.likeCount, "retweets": t.retweetCount,
                 "views": getattr(t, "viewCount", 0)}
                for t in (tweets or [])]

    result = _run_tw(_do, query, limit)

    if result is None:
        # Fallback to keyless HTTP
        result = _search_keyless(query, limit)

    cache.set(ckey, result)
    return result


def _search_keyless(query: str, limit: int) -> dict:
    """Keyless fallback — limited, JS-rendered results may be empty."""
    url = f"https://x.com/search?q={query.replace(' ', '+')}&f=live"
    html, status = _fetch(url, ttl=120)
    ok = status == 200 and _verify_not_blocked(html)
    tweets = _extract_tweets(html) if ok else []
    return {
        "query": query, "url": url, "http_status": status,
        "ok": ok, "found": len(tweets), "tweets": tweets[:limit],
        "backend": "keyless-http",
    }


@mcp.tool()
def user_tweets(username: str, limit: int = 10) -> dict:
    """Fetch recent tweets from a user's timeline via twscrape GraphQL (requires cookie auth).

    Returns parsed tweets with id, text, created_at, likes, retweets.
    Rate limit: ~1 req/3s. Cache 5min.
    """
    ckey = f"tw:user_tweets:{username}:{limit}"
    hit = cache.get(ckey, ttl=300)
    if hit is not None:
        return hit

    _throttle("tw", 3.0)

    # Resolve user_id first
    async def _do(api, uname, lim):
        user = await api.user_by_login(uname)
        if not user:
            return {"error": f"User '{uname}' not found"}
        tweets_result = await api.user_tweets(user.id, limit=lim)
        return {
            "username": uname,
            "user_id": str(user.id),
            "found": len(tweets_result),
            "tweets": [{"id": t.id, "text": t.rawContent, "created_at": str(t.date),
                        "likes": t.likeCount, "retweets": t.retweetCount}
                       for t in (tweets_result or [])],
        }

    result = _run_tw(_do, username, limit)

    if result is None:
        result = {
            "username": username, "ok": False,
            "error": "Cookie auth not configured. Set X_AUTH_TOKEN + X_CT0 env vars.",
            "backend": "twscrape-unavailable",
        }

    cache.set(ckey, result)
    return result


@mcp.tool()
def user_by_login(username: str) -> dict:
    """Resolve X.com username to user_id + profile stats via twscrape GraphQL (requires cookie auth).

    Returns id, username, displayname, followers/following count, description, created.
    Rate limit: ~1 req/3s. Cache 10min.
    """
    ckey = f"tw:user:{username}"
    hit = cache.get(ckey, ttl=600)
    if hit is not None:
        return hit

    _throttle("tw", 3.0)

    async def _do(api, uname):
        user = await api.user_by_login(uname)
        if not user:
            return {"error": f"User '{uname}' not found"}
        return {
            "id": str(user.id), "username": user.username,
            "displayname": getattr(user, "displayname", "") or getattr(user, "name", ""),
            "followers": user.followersCount, "following": user.friendsCount,
            "description": getattr(user, "description", "") or getattr(user, "rawDescription", ""),
            "created": str(getattr(user, "created", "")),
        }

    result = _run_tw(_do, username)

    if result is None:
        # Fallback to keyless profile_lookup
        result = profile_lookup(username)

    cache.set(ckey, result)
    return result


@mcp.tool()
def health() -> dict:
    """Probe x.com reachability + cookie auth status. Returns health summary."""
    from scrapling.fetchers import Fetcher
    t0 = time.monotonic()
    keyless_ok = False
    try:
        resp = Fetcher.get("https://x.com", impersonate="chrome", timeout=10)
        text = resp.body.decode() if resp.body else ""
        keyless_ok = _verify_not_blocked(text)
    except Exception:
        pass

    # Probe twscrape
    tw_ok = False
    try:
        api = _get_tw_api()
        if api:
            stats = asyncio.run(api.pool.stats())
            accts = stats.get("accounts", []) if isinstance(stats, dict) else []
            tw_ok = any(a.get("active") for a in accts if isinstance(a, dict))
    except Exception:
        pass

    global _tw_ready
    return {
        "reachable": keyless_ok,
        "cookie_auth": tw_ok or (_tw_ready or False),
        "latency_ms": (time.monotonic() - t0) * 1000,
        "tools_available": ["profile_lookup"]
        + (["search_tweets", "user_tweets", "user_by_login"] if (tw_ok or _tw_ready) else []),
        "budget_remaining": "~20 req/min keyless + twscrape auto pool rotation",
    }


if __name__ == "__main__":
    mcp.run()

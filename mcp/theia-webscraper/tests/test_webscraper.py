"""theia-webscraper golden tests — mock tier fetchers."""
import importlib.util
import sys
from pathlib import Path

# ── Mock mcp modules ───────────────────────────────────────────────────────

class _MockFastMCP:
    def __init__(self, name): self.name = name
    def tool(self):
        def decorator(fn): return fn
        return decorator

sys.modules["mcp"] = type(sys)("mcp")
sys.modules["mcp.server"] = type(sys)("mcp.server")
sys.modules["mcp.server.fastmcp"] = type(sys)("mcp.server.fastmcp")
sys.modules["mcp.server.fastmcp"].FastMCP = _MockFastMCP

# Mock curl_cffi
class _MockResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text

class _MockRequests:
    @staticmethod
    def get(url, **kw):
        if "medium" in url:
            return _MockResp(403, "just a moment... challenges.cloudflare.com")
        return _MockResp(200, f"<html><title>OK</title><body>{url}</body></html>")

sys.modules["curl_cffi"] = type(sys)("curl_cffi")
sys.modules["curl_cffi.requests"] = _MockRequests

# Mock scrapling
class _MockStealthResp:
    def __init__(self, url):
        self.status = 200
        self.text = f"<html><title>Bypassed</title><body>{url}</body></html>"
        self.body = self.text.encode()

class _MockSF:
    def fetch(self, url, **kw):
        return _MockStealthResp(url)

sys.modules["scrapling"] = type(sys)("scrapling")
sys.modules["scrapling.fetchers"] = type(sys)("scrapling.fetchers")
sys.modules["scrapling.fetchers"].StealthyFetcher = _MockSF

# ── Load server module ─────────────────────────────────────────────────────

spec = importlib.util.spec_from_file_location("webscraper_server", Path(__file__).resolve().parents[1] / "server.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["webscraper_server"] = mod
spec.loader.exec_module(mod)


# ── Tests ───────────────────────────────────────────────────────────────────

def test_fetch_page_http_success():
    res = mod.fetch_page("https://solana.com/docs", tier="http")
    assert res["ok"] is True
    assert res["method"] == "curl_cffi"
    assert res["status"] == 200


def test_fetch_page_http_cf_fallback():
    res = mod.fetch_page("https://medium.com/@aeyakovenko", tier="auto")
    # tier1 fails (mock 403), tier2 bypasses
    assert res["ok"] is True
    assert res["method"] == "stealthyfetcher"
    assert res["cf_bypassed"] is True
    assert "tier1_failed" in res


def test_fetch_page_browser_only():
    res = mod.fetch_page("https://medium.com/@aeyakovenko", tier="browser")
    assert res["ok"] is True
    assert res["method"] == "stealthyfetcher"
    assert res["cf_bypassed"] is True


def test_extract_text():
    html = "<html><script>alert(1)</script><body><h1>Hello</h1><p>World</p></body></html>"
    res = mod.extract_text(html)
    assert res["ok"] is True
    assert "Hello" in res["text"]
    assert "World" in res["text"]
    assert "alert" not in res["text"]


def test_detect_protection_cf():
    res = mod.detect_protection("https://medium.com/@aeyakovenko")
    assert res["cf_detected"] is True
    assert res["needs_browser"] is True


def test_detect_protection_clean():
    res = mod.detect_protection("https://solana.com/docs")
    assert res["cf_detected"] is False
    assert res["needs_browser"] is False


def test_fetch_pages_batch():
    urls = [
        "https://solana.com/docs",
        "https://medium.com/@aeyakovenko",
        "https://pump.fun",
    ]
    res = mod.fetch_pages(urls, max_concurrent=2, tier="auto")
    assert res["ok"] is True
    assert len(res["results"]) == 3
    ok_count = sum(1 for r in res["results"] if r["ok"])
    assert ok_count == 3

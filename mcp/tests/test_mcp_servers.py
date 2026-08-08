"""MCP server golden tests — mock HTTP / DB, no real network calls."""
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

# ── Mock mcp modules so server imports work without the package installed ──

class _MockFastMCP:
    def __init__(self, name): self.name = name
    def tool(self):
        def decorator(fn): return fn
        return decorator

sys.modules["mcp"] = type(sys)("mcp")
sys.modules["mcp.server"] = type(sys)("mcp.server")
sys.modules["mcp.server.fastmcp"] = type(sys)("mcp.server.fastmcp")
sys.modules["mcp.server.fastmcp"].FastMCP = _MockFastMCP

# Add paths
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp" / "common"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp"))

from theia_net import DiskCache, ApiKeyRotator  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load server modules
_chainrpc = _load_module("chainrpc_server", ROOT / "mcp" / "theia-chainrpc" / "server.py")
_dexdata = _load_module("dexdata_server", ROOT / "mcp" / "theia-dexdata" / "server.py")
_security = _load_module("security_server", ROOT / "mcp" / "theia-security" / "server.py")
_birdeye = _load_module("birdeye_server", ROOT / "mcp" / "theia-birdeye" / "server.py")
_store = _load_module("store_server", ROOT / "mcp" / "theia-store" / "server.py")

# ── Helpers ─────────────────────────────────────────────────────────────────


def _init_test_db(schema_path: Path) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tmp.name)
    conn.executescript(schema_path.read_text())
    conn.commit()
    conn.close()
    return tmp.name


def _patch_db_path(mod, db_path: str):
    original = mod.DB_PATH
    mod.DB_PATH = db_path
    return original


# ── theia-chainrpc tests ───────────────────────────────────────────────────


def test_chainrpc_swap_parsing_buy():
    """Parse a buy swap from Helius tokenTransfers."""
    tx = {
        "signature": "sig1",
        "slot": 123,
        "timestamp": 1000,
        "type": "SWAP",
        "feePayer": "user_wallet",
        "tokenTransfers": [
            {"fromUserAccount": "user_wallet", "toUserAccount": "pool",
             "mint": "So11111111111111111111111111111111111111112",
             "tokenAmount": 10.0},
            {"fromUserAccount": "pool", "toUserAccount": "user_wallet",
             "mint": "TOKEN_MINT",
             "tokenAmount": 1000.0},
        ],
    }
    s = _chainrpc._swap_from_transfers(tx)
    assert s is not None
    assert s["side"] == "buy"
    assert s["base_mint"] == "TOKEN_MINT"
    assert s["base_qty"] == 1000.0
    assert s["quote_qty"] == 10.0
    assert s["exec_price"] == 10.0 / 1000.0


def test_chainrpc_swap_parsing_sell():
    """Parse a sell swap (token out, SOL in)."""
    tx = {
        "signature": "sig2",
        "slot": 124,
        "timestamp": 1001,
        "type": "SWAP",
        "feePayer": "user_wallet",
        "tokenTransfers": [
            {"fromUserAccount": "user_wallet", "toUserAccount": "pool",
             "mint": "TOKEN_MINT", "tokenAmount": 500.0},
            {"fromUserAccount": "pool", "toUserAccount": "user_wallet",
             "mint": "So11111111111111111111111111111111111111112",
             "tokenAmount": 5.0},
        ],
    }
    s = _chainrpc._swap_from_transfers(tx)
    assert s is not None
    assert s["side"] == "sell"
    assert s["base_mint"] == "TOKEN_MINT"
    assert s["base_qty"] == 500.0
    assert s["quote_qty"] == 5.0


def test_chainrpc_swap_parsing_non_swap_skipped():
    """Non-SWAP transactions return None."""
    tx = {"type": "TRANSFER", "tokenTransfers": []}
    assert _chainrpc._swap_from_transfers(tx) is None


# ── theia-dexdata tests ──────────────────────────────────────────────────────


def test_dexdata_strip_net():
    assert _dexdata._strip_net("solana_abc123", "solana") == "abc123"
    assert _dexdata._strip_net("abc123", "solana") == "abc123"


# ── theia-security tests ────────────────────────────────────────────────────


def test_security_response_parsing():
    """GoPlus raw response formatting."""
    called_with = {}
    def mock_request_json(url, **kwargs):
        called_with["url"] = url
        return {
            "result": {
                "TOKEN1": {
                    "is_honeypot": "1",
                    "buy_tax": "5",
                    "sell_tax": "5",
                    "owner_address": "abc",
                }
            }
        }
    original = _security.request_json
    _security.request_json = mock_request_json
    try:
        result = _security.token_security("TOKEN1")
        assert result["mint"] == "TOKEN1"
        assert result["found"] is True
        assert result["raw"]["is_honeypot"] == "1"
    finally:
        _security.request_json = original


# ── theia-birdeye tests ─────────────────────────────────────────────────────


def test_birdeye_response_parsing():
    """Birdeye token_list response shape."""
    def mock_request_json(url, **kwargs):
        return {
            "data": {
                "tokens": [
                    {"address": "T1", "symbol": "ABC", "v24hUSD": 50000,
                     "price": 0.001, "mc": 10000}
                ]
            }
        }
    original = _birdeye.request_json
    _birdeye.request_json = mock_request_json
    try:
        result = _birdeye.token_list(limit=1)
        assert len(result) == 1
        assert result[0]["address"] == "T1"
    finally:
        _birdeye.request_json = original


# ── theia-store tests ─────────────────────────────────────────────────────────


def test_store_token_crud():
    """Upsert + get token."""
    db_path = _init_test_db(ROOT / "mcp" / "theia-store" / "schema.sql")
    orig = _patch_db_path(_store, db_path)
    try:
        _store.upsert_token("MINT1", symbol="ABC", name="Alpha Beta", created_ts=1000)
        t = _store.get_token("MINT1")
        assert t["mint"] == "MINT1"
        assert t["symbol"] == "ABC"
    finally:
        _store.DB_PATH = orig
        Path(db_path).unlink(missing_ok=True)


def test_store_screen_crud():
    """Record + get latest screen."""
    db_path = _init_test_db(ROOT / "mcp" / "theia-store" / "schema.sql")
    orig = _patch_db_path(_store, db_path)
    try:
        _store.record_screen("MINT1", verdict="pass", is_honeypot=0, buy_tax=0.0,
                            sell_tax=0.0, mint_auth_live=0, freeze_auth_live=0,
                            lp_locked=1, top10_share=0.2, wash_score=0.1,
                            rug_score=0.0, screen_score=0.05)
        s = _store.get_latest_screen("MINT1")
        assert s["verdict"] == "pass"
        assert s["mint"] == "MINT1"
    finally:
        _store.DB_PATH = orig
        Path(db_path).unlink(missing_ok=True)


def test_store_hypothesis_and_backtest():
    """Upsert hypothesis + record backtest, verify best metrics updated."""
    db_path = _init_test_db(ROOT / "mcp" / "theia-store" / "schema.sql")
    orig = _patch_db_path(_store, db_path)
    try:
        _store.upsert_hypothesis("H-001", "Test Hyp", "path.md",
                                 rule_spec={"entry": {"min_liq": 1000}})
        _store.record_backtest("B-001", "H-001", 1000, 2000,
                               params={"lag": 30}, n_trades=10,
                               expectancy=0.02, profit_factor=1.5,
                               win_rate=0.6, max_dd=-0.1)
        h = _store.get_hypothesis("H-001")
        assert h["best_expectancy"] == 0.02
        assert h["best_pf"] == 1.5
        assert h["best_winrate"] == 0.6
    finally:
        _store.DB_PATH = orig
        Path(db_path).unlink(missing_ok=True)


# ── theia_net shared infra tests ────────────────────────────────────────────


def test_api_key_rotator():
    keys = ["k1", "k2", "k3"]
    rot = ApiKeyRotator("test", keys, interval=0.0)
    assert rot.next() == "k1"
    assert rot.next() == "k2"
    assert rot.next() == "k3"
    assert rot.next() == "k1"


def test_disk_cache():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=tmp)
        cache.set("key1", {"data": 42})
        assert cache.get("key1") == {"data": 42}
        assert cache.get("key1", ttl=1) == {"data": 42}
        import time
        time.sleep(1.1)
        assert cache.get("key1", ttl=1) is None

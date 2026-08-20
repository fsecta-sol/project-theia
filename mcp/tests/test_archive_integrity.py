"""Store-bound integrity tests; all databases are temporary."""
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


class _MockFastMCP:
    def __init__(self, name):
        self.name = name

    def tool(self):
        return lambda fn: fn


sys.modules["mcp"] = type(sys)("mcp")
sys.modules["mcp.server"] = type(sys)("mcp.server")
sys.modules["mcp.server.fastmcp"] = type(sys)("mcp.server.fastmcp")
sys.modules["mcp.server.fastmcp"].FastMCP = _MockFastMCP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_store():
    path = ROOT / "mcp" / "theia-store" / "server.py"
    spec = importlib.util.spec_from_file_location("archive_integrity_store", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


store = _load_store()


def _entry():
    return {
        "seq": 0, "kind": "entry", "ts": 100, "qty": 10.0, "price": 0.1,
        "reserves_base": 100.0, "reserves_quote": 10.0, "gas_sol": 0.001,
        "slippage": 0.0, "amm_model": "v2",
    }


def _exit():
    return {
        "seq": 1, "kind": "hard_stop", "ts": 140, "qty": 10.0, "price": 0.065,
        "reserves_base": 90.0, "reserves_quote": 5.85, "gas_sol": 0.001,
        "slippage": 0.0, "amm_model": "v2",
    }


def _open(tmp_path):
    store.DB_PATH = str(tmp_path / "store.db")
    store._init()
    return store.open_paper_trade(
        "T", "M", "H", 100, 0.1, 1.0,
        entry_fill=_entry(),
    )


def test_store_close_requires_exit_fill_and_keeps_open(tmp_path):
    _open(tmp_path)
    with pytest.raises(store.LedgerIntegrityError, match="entry and exit"):
        store.close_trade("T", 140, -0.35, -0.35, -0.35, 0.002, 0, "hard_stop")
    conn = sqlite3.connect(store.DB_PATH)
    assert conn.execute("SELECT state FROM paper_trades WHERE trade_id='T'").fetchone()[0] == "open"
    assert conn.execute("SELECT COUNT(*) FROM archives").fetchone()[0] == 0
    conn.close()


def test_store_close_atomically_records_exit_and_immutable_archive(tmp_path):
    _open(tmp_path)
    result = store.close_trade(
        "T", 140, -0.35, -0.35, -0.35, 0.002, 0, "hard_stop",
        exit_fills=[_exit()],
    )
    assert result["hold_secs"] == 40
    with pytest.raises(store.LedgerIntegrityError, match="already archived"):
        store.close_trade(
            "T", 140, 99, 99, 99, 0, 0, "changed", exit_fills=[_exit()]
        )
    conn = sqlite3.connect(store.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM trade_fills").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE archives SET roi=99 WHERE trade_id='T'")
    conn.close()


def test_store_record_fill_never_replaces_sequence(tmp_path):
    _open(tmp_path)
    exit_fill = _exit()
    store.record_fill("T", **{k: exit_fill[k] for k in (
        "seq", "kind", "ts", "qty", "price", "reserves_base", "reserves_quote",
        "gas_sol", "slippage", "amm_model")})
    with pytest.raises(store.LedgerIntegrityError, match="duplicate fill"):
        store.record_fill("T", **{k: exit_fill[k] for k in (
            "seq", "kind", "ts", "qty", "price", "reserves_base", "reserves_quote",
            "gas_sol", "slippage", "amm_model")})


def test_store_init_is_idempotent_for_legacy_archives(tmp_path):
    store.DB_PATH = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(store.DB_PATH)
    conn.executescript(
        """
        CREATE TABLE archives (
            trade_id TEXT PRIMARY KEY,
            mint TEXT,
            hypothesis_id TEXT,
            entry_ts INTEGER,
            exit_ts INTEGER,
            hold_secs INTEGER,
            realized_pnl_sol REAL,
            roi REAL,
            expectancy_contrib REAL,
            gas_sol_total REAL,
            slippage_total REAL,
            exit_reason TEXT,
            created_ts INTEGER
        );
        CREATE TABLE trade_fills (trade_id TEXT, kind TEXT);
        INSERT INTO archives(
            trade_id, mint, hypothesis_id, entry_ts, exit_ts, hold_secs,
            realized_pnl_sol, roi, expectancy_contrib, gas_sol_total,
            slippage_total, exit_reason, created_ts
        ) VALUES ('legacy', 'M', 'H', 1, 2, 999, -1, -1, -1, 0, 0, 'old', 3);
        """
    )
    conn.commit()
    conn.close()

    store._init()
    store._init()

    conn = sqlite3.connect(store.DB_PATH)
    assert conn.execute(
        "SELECT reconstructable, integrity_error FROM archives WHERE trade_id='legacy'"
    ).fetchone() == (0, "missing_trade_fills")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE archives SET hold_secs=1000 WHERE trade_id='legacy'")
    conn.close()

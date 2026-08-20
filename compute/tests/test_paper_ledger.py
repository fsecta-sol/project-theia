"""Focused paper-ledger integrity tests (temporary DB only)."""
import sqlite3
import json
from pathlib import Path

import pytest

from compute.paper_ledger import (
    LedgerIntegrityError,
    close_trade_with_fills,
    open_trade_with_entry_fill,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "mcp" / "theia-store" / "schema.sql"


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text())
    return conn


def _entry(reserves=True):
    return {
        "seq": 0,
        "kind": "entry",
        "ts": 100,
        "qty": 100.0,
        "price": 0.01,
        "reserves_base": 1_000.0 if reserves else None,
        "reserves_quote": 10.0 if reserves else None,
        "gas_sol": 0.001,
        "slippage": 0.002,
        "amm_model": "v2",
    }


def _open(conn, reserves=True):
    open_trade_with_entry_fill(
        conn,
        trade_id="T-1",
        mint="MINT",
        hypothesis_id="H-1",
        entry_ts=100,
        entry_price=0.01,
        size_sol=1.0,
        stop_price=0.0065,
        tp_ladder=[],
        opened_by={"kind": "test"},
        entry_fill=_entry(reserves),
    )


def _exit(seq=1, ts=130, qty=100.0, reserves=True, price=0.0065):
    return {
        "seq": seq,
        "kind": "hard_stop",
        "ts": ts,
        "qty": qty,
        "price": price,
        "reserves_base": 900.0 if reserves else None,
        "reserves_quote": 5.85 if reserves else None,
        "gas_sol": 0.001,
        "slippage": 0.003,
        "amm_model": "v2",
    }


def _close(conn, fills, **overrides):
    values = {
        "exit_ts": max((fill["ts"] for fill in fills), default=130),
        "realized_pnl_sol": -0.35,
        "roi": -0.35,
        "expectancy_contrib": -0.35,
        "gas_sol_total": 0.002,
        "slippage_total": 0.005,
        "exit_reason": "hard_stop",
    }
    values.update(overrides)
    return close_trade_with_fills(conn, "T-1", fills, **values)


def test_new_trade_is_atomic_with_one_entry_fill():
    conn = _db()
    _open(conn)
    trade = conn.execute("SELECT state FROM paper_trades WHERE trade_id='T-1'").fetchone()
    fills = conn.execute("SELECT seq,kind,qty FROM trade_fills WHERE trade_id='T-1'").fetchall()
    assert trade[0] == "open"
    assert fills == [(0, "entry", 100.0)]


def test_missing_exit_fill_rejects_close_and_leaves_trade_open():
    conn = _db()
    _open(conn)
    with pytest.raises(LedgerIntegrityError, match="entry and exit"):
        _close(conn, [])
    assert conn.execute("SELECT state FROM paper_trades WHERE trade_id='T-1'").fetchone()[0] == "open"
    assert conn.execute("SELECT COUNT(*) FROM archives").fetchone()[0] == 0


def test_archive_is_immutable_on_duplicate_close():
    conn = _db()
    _open(conn)
    _close(conn, [_exit()])
    before = conn.execute("SELECT * FROM archives WHERE trade_id='T-1'").fetchone()
    with pytest.raises(LedgerIntegrityError, match="already archived"):
        _close(conn, [_exit(price=0.02)], realized_pnl_sol=99.0, exit_reason="changed")
    after = conn.execute("SELECT * FROM archives WHERE trade_id='T-1'").fetchone()
    assert tuple(after) == tuple(before)


def test_hold_secs_is_derived_from_final_exit_timestamp():
    conn = _db()
    _open(conn)
    _close(conn, [_exit(ts=137)])
    row = conn.execute("SELECT entry_ts,exit_ts,hold_secs FROM archives").fetchone()
    assert row == (100, 137, 37)


def test_partial_exit_quantities_must_sum_to_entry_quantity():
    conn = _db()
    _open(conn)
    fills = [_exit(seq=1, ts=120, qty=50), _exit(seq=2, ts=130, qty=50)]
    _close(conn, fills, exit_reason="tp_2x")
    assert conn.execute("SELECT SUM(qty) FROM trade_fills WHERE trade_id='T-1' AND kind != 'entry'").fetchone()[0] == 100

    conn = _db()
    _open(conn)
    with pytest.raises(LedgerIntegrityError, match="exceed entry"):
        _close(conn, [_exit(qty=100.0001)])
    assert conn.execute("SELECT COUNT(*) FROM archives").fetchone()[0] == 0
    assert conn.execute("SELECT state FROM paper_trades WHERE trade_id='T-1'").fetchone()[0] == "open"


def test_missing_reserves_are_explicitly_degraded_not_fabricated():
    conn = _db()
    _open(conn, reserves=False)
    _close(conn, [_exit(reserves=False)])
    row = conn.execute("SELECT reconstructable,integrity_error FROM archives").fetchone()
    assert row == (0, "missing_reserve_snapshot")
    assert conn.execute("SELECT reserves_base,reserves_quote FROM trade_fills").fetchall() == [(None, None), (None, None)]


def test_negative_duration_is_rejected_without_state_transition():
    conn = _db()
    _open(conn)
    with pytest.raises(LedgerIntegrityError, match="before entry"):
        _close(conn, [_exit(ts=99)])
    assert conn.execute("SELECT state FROM paper_trades WHERE trade_id='T-1'").fetchone()[0] == "open"


def test_legacy_archive_is_not_made_reconstructable_by_fills():
    conn = _db()
    conn.execute(
        "INSERT INTO archives(trade_id,mint,hypothesis_id,entry_ts,exit_ts,hold_secs,"
        "realized_pnl_sol,roi,expectancy_contrib,gas_sol_total,slippage_total,exit_reason,created_ts,"
        "reconstructable,integrity_error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("legacy", "M", "H", 1, 2, 999, -1, -1, -1, 0, 0, "old", 3, 0, "missing_trade_fills"),
    )
    row = conn.execute("SELECT reconstructable,integrity_error,hold_secs FROM archives").fetchone()
    assert row == (0, "missing_trade_fills", 999)

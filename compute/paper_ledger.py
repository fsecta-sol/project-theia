"""Transactional, append-only paper-trade ledger primitives.

This module is shared by the no-agent cron scripts and theia-store.  It stores
fills and archive/state transitions in one SQLite transaction; it does not
calculate P&L.  P&L values supplied by callers must come from deterministic
compute code.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any


EPSILON = 1e-9


class LedgerIntegrityError(ValueError):
    """Raised when a paper ledger transition would lose reconstructability."""


def _col(row: sqlite3.Row | tuple, name: str, index: int):
    return row[name] if isinstance(row, sqlite3.Row) else row[index]


def _now() -> int:
    return int(time.time())


def _validate_fill(fill: dict[str, Any], *, expected_kind: str | None = None) -> None:
    if expected_kind is not None and fill.get("kind") != expected_kind:
        raise LedgerIntegrityError(f"expected {expected_kind} fill")
    if not isinstance(fill.get("seq"), int) or fill["seq"] < 0:
        raise LedgerIntegrityError("fill sequence must be a non-negative integer")
    if not isinstance(fill.get("ts"), int):
        raise LedgerIntegrityError("fill timestamp must be an integer")
    if float(fill.get("qty") or 0) <= 0:
        raise LedgerIntegrityError("fill quantity must be positive")
    if float(fill.get("price") or 0) <= 0:
        raise LedgerIntegrityError("fill price must be positive")


def _fill_values(trade_id: str, fill: dict[str, Any]) -> tuple:
    return (
        trade_id,
        fill["seq"],
        fill["kind"],
        fill["ts"],
        float(fill["qty"]),
        float(fill["price"]),
        fill.get("reserves_base"),
        fill.get("reserves_quote"),
        fill.get("base_fee", 0),
        fill.get("priority_fee", 0),
        fill.get("native_usd", 0),
        fill.get("gas_sol", 0),
        fill.get("slippage", 0),
        fill.get("amm_model", "unknown"),
    )


def _insert_fill(conn: sqlite3.Connection, trade_id: str, fill: dict[str, Any]) -> None:
    _validate_fill(fill)
    try:
        conn.execute(
            """INSERT INTO trade_fills(
                trade_id,seq,kind,ts,qty,price,reserves_base,reserves_quote,
                base_fee,priority_fee,native_usd,gas_sol,slippage,amm_model
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            _fill_values(trade_id, fill),
        )
    except sqlite3.IntegrityError as exc:
        raise LedgerIntegrityError(f"duplicate fill sequence {fill['seq']}") from exc


def open_trade_with_entry_fill(
    conn: sqlite3.Connection,
    *,
    trade_id: str,
    mint: str,
    hypothesis_id: str,
    entry_ts: int,
    entry_price: float,
    size_sol: float,
    stop_price: float = 0,
    tp_ladder: list | None = None,
    opened_by: dict | None = None,
    entry_fill: dict[str, Any],
) -> dict:
    """Create a position and its sequence-0 entry fill atomically."""
    _validate_fill(entry_fill, expected_kind="entry")
    if entry_fill["seq"] != 0 or entry_fill["ts"] != entry_ts:
        raise LedgerIntegrityError("entry fill must be sequence 0 at entry_ts")
    if entry_price <= 0 or size_sol <= 0:
        raise LedgerIntegrityError("entry price and size must be positive")

    with conn:
        conn.execute(
            """INSERT INTO paper_trades(
                trade_id,mint,hypothesis_id,state,entry_ts,entry_price,size_sol,
                stop_price,tp_ladder,opened_by
            ) VALUES(?,?,?,'open',?,?,?,?,?,?)""",
            (
                trade_id,
                mint,
                hypothesis_id,
                entry_ts,
                entry_price,
                size_sol,
                stop_price,
                json.dumps(tp_ladder or []),
                json.dumps(opened_by or {}),
            ),
        )
        _insert_fill(conn, trade_id, entry_fill)
    return {"ok": True, "trade_id": trade_id, "entry_fill_seq": 0}


def record_fill(conn: sqlite3.Connection, trade_id: str, fill: dict[str, Any]) -> dict:
    """Append one fill; never replace an existing sequence."""
    row = conn.execute(
        "SELECT state FROM paper_trades WHERE trade_id=?", (trade_id,)
    ).fetchone()
    if row is None:
        raise LedgerIntegrityError(f"unknown trade {trade_id}")
    if row[0] == "archived":
        raise LedgerIntegrityError("cannot add a fill after archive")
    with conn:
        _insert_fill(conn, trade_id, fill)
    return {"ok": True, "trade_id": trade_id, "seq": fill["seq"]}


def close_trade_with_fills(
    conn: sqlite3.Connection,
    trade_id: str,
    fills: list[dict[str, Any]],
    *,
    exit_ts: int,
    realized_pnl_sol: float,
    roi: float,
    expectancy_contrib: float,
    gas_sol_total: float,
    slippage_total: float,
    exit_reason: str,
) -> dict:
    """Append exit fills and archive a trade in one validated transaction.

    ``fills`` contains new exit fills only; the sequence-0 entry fill must
    already exist.  Missing reserve snapshots deliberately produce a degraded
    archive rather than fabricated reserve values.
    """
    with conn:
        trade = conn.execute(
            "SELECT mint,hypothesis_id,entry_ts,state FROM paper_trades WHERE trade_id=?",
            (trade_id,),
        ).fetchone()
        if trade is None:
            raise LedgerIntegrityError(f"unknown trade {trade_id}")
        if conn.execute(
            "SELECT 1 FROM archives WHERE trade_id=?", (trade_id,)
        ).fetchone() is not None or _col(trade, "state", 3) == "archived":
            raise LedgerIntegrityError("trade is already archived")

        entry_fills = conn.execute(
            "SELECT * FROM trade_fills WHERE trade_id=? AND kind='entry' ORDER BY seq",
            (trade_id,),
        ).fetchall()
        if not entry_fills:
            raise LedgerIntegrityError("archive requires entry and exit fills")
        if not fills:
            raise LedgerIntegrityError("archive requires entry and exit fills")

        existing_seqs = {
            row[0]
            for row in conn.execute(
                "SELECT seq FROM trade_fills WHERE trade_id=?", (trade_id,)
            ).fetchall()
        }
        for fill in fills:
            _validate_fill(fill)
            if fill.get("kind") == "entry":
                raise LedgerIntegrityError("close accepts exit fills only")
            if fill["seq"] in existing_seqs:
                raise LedgerIntegrityError(f"duplicate fill sequence {fill['seq']}")
            existing_seqs.add(fill["seq"])

        entry_ts = int(_col(trade, "entry_ts", 2))
        if exit_ts < entry_ts:
            raise LedgerIntegrityError("exit timestamp is before entry")
        final_fill_ts = max(fill["ts"] for fill in fills)
        if final_fill_ts != exit_ts:
            raise LedgerIntegrityError("exit_ts must equal the final exit fill timestamp")

        entry_qty = sum(float(_col(row, "qty", 4)) for row in entry_fills)
        existing_exit_qty = sum(
            float(row[0])
            for row in conn.execute(
                "SELECT qty FROM trade_fills WHERE trade_id=? AND kind!='entry'",
                (trade_id,),
            ).fetchall()
        )
        new_exit_qty = sum(float(fill["qty"]) for fill in fills)
        if existing_exit_qty + new_exit_qty > entry_qty + EPSILON:
            raise LedgerIntegrityError("exit fills exceed entry quantity")
        if abs(existing_exit_qty + new_exit_qty - entry_qty) > EPSILON:
            raise LedgerIntegrityError("exit fills must sum to entry quantity")

        for fill in fills:
            _insert_fill(conn, trade_id, fill)

        all_fills = conn.execute(
            "SELECT reserves_base,reserves_quote FROM trade_fills WHERE trade_id=?",
            (trade_id,),
        ).fetchall()
        reconstructable = int(all(row[0] is not None and row[1] is not None for row in all_fills))
        integrity_error = None if reconstructable else "missing_reserve_snapshot"
        conn.execute(
            """INSERT INTO archives(
                trade_id,mint,hypothesis_id,entry_ts,exit_ts,hold_secs,
                realized_pnl_sol,roi,expectancy_contrib,gas_sol_total,slippage_total,
                exit_reason,created_ts,reconstructable,integrity_error
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade_id,
                _col(trade, "mint", 0),
                _col(trade, "hypothesis_id", 1),
                entry_ts,
                exit_ts,
                exit_ts - entry_ts,
                realized_pnl_sol,
                roi,
                expectancy_contrib,
                gas_sol_total,
                slippage_total,
                exit_reason,
                _now(),
                reconstructable,
                integrity_error,
            ),
        )
        conn.execute(
            "UPDATE paper_trades SET state='archived' WHERE trade_id=?", (trade_id,)
        )
    return {
        "ok": True,
        "trade_id": trade_id,
        "exit_ts": exit_ts,
        "hold_secs": exit_ts - entry_ts,
        "reconstructable": reconstructable,
        "integrity_error": integrity_error,
    }

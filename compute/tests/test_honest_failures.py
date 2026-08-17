"""Tests for honest-failure fixes:
- backtest_engine: missing reserves → skip + count, never fabricate
- task_runner: agent-handled tasks (monitor/delegate) stay 'ready', never faked
- task_runner._handle_backtest: real API-free backtest, honest on empty data
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compute import backtest_engine  # noqa: E402
from cron import task_runner  # noqa: E402


def _price_rows(mint, start_ts, n, start_c):
    rows, c, base_r = [], start_c, 1_000_000.0
    for i in range(n):
        c *= 1.1
        rows.append({
            "mint": mint, "ts": start_ts + i * 60,
            "o": c, "h": c * 1.05, "l": c * 0.95, "c": c,
            "volume_24h": 50000, "liquidity_usd": 50000,
            "reserves_base": base_r, "reserves_quote": base_r * c,
            "launch_ts": start_ts, "amm_model": "v2",
        })
    return rows


# ── backtest_engine: no fabricated reserves ─────────────────────────────────

def test_backtest_missing_reserves_skipped_and_counted():
    mint = "NORESERVES"
    start = 1000000000
    rows = _price_rows(mint, start, 12, 0.001)
    for r in rows:
        r.pop("reserves_base"); r.pop("reserves_quote")
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {"entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
            "size": {"notional_sol": 1.0}, "exit": {}}
    r = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    assert r["n_entered"] == 0, "must not fabricate reserves to force an entry"
    assert r["n_skipped_no_reserves"] == 1
    assert r["metrics"]["n"] == 0


def test_backtest_with_reserves_enters_normally():
    mint = "HASRESERVES"
    start = 1000000000
    rows = _price_rows(mint, start, 12, 0.001)
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {"entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
            "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.5}, "exit": {}}
    r = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    assert r["n_entered"] == 1
    assert r["n_skipped_no_reserves"] == 0


# ── task_runner: agent-handled tasks are never faked ────────────────────────

def _init_test_db() -> str:
    schema = Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql"
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tmp.name)
    conn.executescript(schema.read_text())
    conn.commit()
    conn.close()
    return tmp.name


def test_agent_handled_tasks_not_executed_by_runner():
    db = _init_test_db()
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        task_runner.enqueue("monitor-T-001", "monitor", {"trade_id": "T-001"})
        task_runner.enqueue("deleg-1", "delegate", {})
        results = task_runner.poll_and_run(limit=5)
        assert results == [], "runner must not execute agent-handled tasks"
        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        for tid in ("monitor-T-001", "deleg-1"):
            row = conn.execute("SELECT state, attempts FROM tasks WHERE id=?",
                               (tid,)).fetchone()
            assert row["state"] == "ready", f"{tid} must stay ready for the agent"
            assert row["attempts"] == 0, f"{tid} must not consume retry attempts"
        conn.close()
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


def test_mcp_bound_handlers_fail_honestly():
    db = _init_test_db()
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        for tid, ttype in (("d1", "discover-screen"), ("l1", "label-corpus"),
                           ("w1", "wallet-pnl-enrich")):
            task_runner.enqueue(tid, ttype, {})
        task_runner.poll_and_run(limit=5)
        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        for tid in ("d1", "l1", "w1"):
            row = conn.execute("SELECT state, result_ref FROM tasks WHERE id=?",
                               (tid,)).fetchone()
            res = json.loads(row["result_ref"])
            assert res["ok"] is False, f"{ttype} must not claim success"
            assert "MCP" in res["error"]
            assert row["state"] == "ready"  # retried until max attempts, not done
        conn.close()
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


# ── task_runner._handle_backtest: real engine, honest failures ──────────────

def test_handle_backtest_empty_history_fails_honestly():
    db = _init_test_db()
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO hypotheses(id, title, note_path, rule_spec, status, created_ts)"
            " VALUES(?,?,?,?,?,?)",
            ("H-1", "H1", "p.md", json.dumps({"entry": {"min_liquidity_usd": 0}}),
             "draft", 1000))
        conn.commit(); conn.close()

        res = task_runner._handle_backtest({"payload": {"hypothesis_id": "H-1"}})
        assert res["ok"] is False
        assert "price_snapshots_v2 is empty" in res["error"]
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


def test_handle_backtest_records_result_and_updates_best():
    db = _init_test_db()
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO hypotheses(id, title, note_path, rule_spec, status, created_ts)"
            " VALUES(?,?,?,?,?,?)",
            ("H-2", "H2", "p.md",
             json.dumps({"entry": {"min_liquidity_usd": 1000},
                         "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.5},
                         "exit": {}}),
             "draft", 1000))
        # Stored history WITHOUT reserves → engine must skip honestly
        for i in range(12):
            conn.execute(
                "INSERT INTO price_snapshots_v2(mint, ts, price_sol, volume_24h,"
                " liquidity_usd) VALUES(?,?,?,?,?)",
                ("M1", 1000 + i * 60, 0.001 * (1.1 ** i), 50000, 50000))
        conn.execute(
            "INSERT INTO screens(mint, screen_ts, verdict) VALUES(?,?,?)",
            ("M1", 1000, "pass"))
        conn.commit(); conn.close()

        res = task_runner._handle_backtest({"payload": {"hypothesis_id": "H-2"}})
        assert res["ok"] is True
        assert res["n_candidates"] == 1
        assert res["n_entered"] == 0, "no reserves in stored history → no fabricated fill"
        assert res["n_skipped_no_reserves"] == 1
        assert res["expectancy"] == 0.0

        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        bt = conn.execute(
            "SELECT * FROM backtests WHERE hypothesis_id='H-2'").fetchone()
        assert bt is not None and bt["n_trades"] == 0
        hyp = conn.execute("SELECT best_winrate FROM hypotheses WHERE id='H-2'").fetchone()
        assert hyp["best_winrate"] == 0.0
        conn.close()
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)

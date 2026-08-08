"""Golden tests for task runner and reconciler."""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cron import task_runner  # noqa: E402
from compute import reconcile  # noqa: E402


def _init_test_db(schema_path: Path) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tmp.name)
    conn.executescript(schema_path.read_text())
    conn.commit()
    conn.close()
    return tmp.name


# ── Task runner tests ────────────────────────────────────────────────────────


def test_task_runner_enqueue_and_execute():
    """Enqueue a task, run it, verify state='done'."""
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        task_runner.enqueue("task-1", "execute_code", {"task": "test"})
        results = task_runner.poll_and_run(limit=1)
        assert len(results) == 1
        assert results[0]["id"] == "task-1"
        assert results[0]["state"] == "done"
        assert results[0]["result"]["ok"] is True
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


def test_task_runner_deps_block_and_unblock():
    """Task B blocked until task A done."""
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        task_runner.enqueue("A", "execute_code", {"task": "A"})
        task_runner.enqueue("B", "execute_code", {"task": "B"}, deps=["A"])

        # First poll: A runs, B stays blocked (A not yet done when we check deps)
        r1 = task_runner.poll_and_run(limit=2)
        states = {x["id"]: x["state"] for x in r1}
        assert states["A"] == "done"
        assert "B" not in states  # B still blocked, not executed yet

        # Second poll: B unblocked (A now done) and runs
        r2 = task_runner.poll_and_run(limit=2)
        states2 = {x["id"]: x["state"] for x in r2}
        assert states2["B"] == "done"
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


def test_task_runner_retry_then_fail():
    """Task fails 3 times → state='failed'."""
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        # Unknown type → fails
        task_runner.enqueue("bad-task", "unknown_type", {})
        for _ in range(3):
            task_runner.poll_and_run(limit=1)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT state, attempts FROM tasks WHERE id='bad-task'").fetchone()
        conn.close()
        assert row["state"] == "failed"
        assert row["attempts"] == 3
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


def test_task_runner_status():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    original = task_runner.DB_PATH
    task_runner.DB_PATH = Path(db)
    try:
        task_runner.enqueue("s1", "execute_code", {})
        task_runner.enqueue("s2", "execute_code", {}, deps=["nonexistent"])
        status = task_runner.get_status()
        assert status["ready"] >= 1
        assert status["blocked"] >= 1
    finally:
        task_runner.DB_PATH = original
        Path(db).unlink(missing_ok=True)


# ── Reconciler tests ───────────────────────────────────────────────────────


def test_reconcile_empty_db():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    report = reconcile.on_boot(db)
    assert report["interrupted_tasks_recovered"] == 0
    assert report["open_positions"] == 0
    assert report["draft_hypotheses"] == 0
    assert report["queue_counts"]["ready"] == 0
    Path(db).unlink(missing_ok=True)


def test_reconcile_open_position_queues_monitor():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    conn = sqlite3.connect(db)
    conn.execute(
        """INSERT INTO paper_trades(trade_id,mint,hypothesis_id,state,entry_ts,entry_price,
            size_sol,stop_price,tp_ladder,opened_by)
         VALUES(?,?,?,'open',?,?,?,?,?,?)""",
        ("T-001", "MINTX", "H-1", 1000, 0.001, 1.0, 0.0005, "[]", "{}"),
    )
    conn.commit()
    conn.close()

    report = reconcile.on_boot(db)
    assert report["open_positions"] == 1
    assert any("queued monitor" in a for a in report["actions"])

    # Verify task created
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    t = conn.execute("SELECT * FROM tasks WHERE id='monitor-T-001'").fetchone()
    conn.close()
    assert t is not None
    assert t["state"] == "ready"
    Path(db).unlink(missing_ok=True)


def test_reconcile_draft_hypothesis_queues_backtest():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    conn = sqlite3.connect(db)
    conn.execute(
        """INSERT INTO hypotheses(id,title,note_path,rule_spec,status,created_ts)
         VALUES(?,?,?,?,?,?)""",
        ("H-DRAFT", "Draft H", "path.md", json.dumps({}), "draft", 1000),
    )
    conn.commit()
    conn.close()

    report = reconcile.on_boot(db)
    assert report["draft_hypotheses"] == 1
    assert any("queued backtest" in a for a in report["actions"])

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    t = conn.execute("SELECT * FROM tasks WHERE id='backtest-H-DRAFT'").fetchone()
    conn.close()
    assert t is not None
    assert t["state"] == "ready"
    Path(db).unlink(missing_ok=True)


def test_reconcile_running_task_reset():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks(id,type,payload,state,deps,attempts,updated_ts) VALUES(?,?,?,?,?,?,?)",
        ("CRASHED", "execute_code", "{}", "running", "[]", 1, 1000),
    )
    conn.commit()
    conn.close()

    report = reconcile.on_boot(db)
    assert report["interrupted_tasks_recovered"] == 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    t = conn.execute("SELECT * FROM tasks WHERE id='CRASHED'").fetchone()
    conn.close()
    assert t["state"] == "ready"  # attempt 2 < 3
    assert t["attempts"] == 2
    Path(db).unlink(missing_ok=True)


def test_reconcile_running_task_fails_after_max():
    db = _init_test_db(Path(__file__).resolve().parents[2] / "mcp" / "theia-store" / "schema.sql")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks(id,type,payload,state,deps,attempts,updated_ts) VALUES(?,?,?,?,?,?,?)",
        ("DEAD", "execute_code", "{}", "running", "[]", 3, 1000),
    )
    conn.commit()
    conn.close()

    report = reconcile.on_boot(db)
    assert report["interrupted_tasks_recovered"] == 1
    assert any("failed after" in w for w in report["warnings"])

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    t = conn.execute("SELECT * FROM tasks WHERE id='DEAD'").fetchone()
    conn.close()
    assert t["state"] == "failed"
    assert t["attempts"] == 4  # was 3, reconciler increments once more
    Path(db).unlink(missing_ok=True)

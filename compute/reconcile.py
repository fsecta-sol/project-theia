"""Reconciler — rebuild Theia state from the DB on boot.

Deterministic. No LLM. Reads the DB, queues what needs resuming, and returns
a boot report so the main agent knows where to start.

Usage:
    from compute.reconcile import on_boot
    report = on_boot()
    # report tells Theia what was recovered and what tasks were queued
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

# Resolve DB path (same logic as task_runner)
_DEFAULT_DB = str(Path.home() / ".hermes" / "theia" / "theia.db")


def _conn(db_path: str | None = None):
    p = db_path or _DEFAULT_DB
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


def _now() -> int:
    return int(time.time())


def on_boot(db_path: str | None = None) -> dict:
    """Reconcile state on boot. Returns report dict.

    Actions:
      1. Scan `tasks` table — reset interrupted 'running' tasks for retry.
      2. Scan `paper_trades` — queue monitor tasks for any open positions.
      3. Scan `hypotheses` — queue backtest tasks for draft hypotheses.
      4. Read `context_windows` — show active sessions.
      5. Return full report for Theia to decide next move.
    """
    conn = _conn(db_path)
    report = {"ts": _now(), "actions": [], "warnings": []}

    # ── 1. Recover interrupted tasks ─────────────────────────────────────────
    cur = conn.execute(
        "SELECT id, type, attempts, payload FROM tasks WHERE state='running'"
    )
    interrupted = [dict(r) for r in cur.fetchall()]
    for t in interrupted:
        attempts = (t["attempts"] or 0) + 1
        if attempts >= 3:
            new_state = "failed"
            report["warnings"].append(
                f"task {t['id']} failed after {attempts} attempts (was running on crash)"
            )
        else:
            new_state = "ready"
            report["actions"].append(
                f"resumed task {t['id']} ({t['type']}) attempt {attempts}"
            )
        conn.execute(
            "UPDATE tasks SET state=?, attempts=?, updated_ts=? WHERE id=?",
            (new_state, attempts, _now(), t["id"]),
        )
    conn.commit()

    # ── 2. Resume open positions → queue monitor tasks ───────────────────────
    cur = conn.execute("SELECT trade_id, mint, hypothesis_id, entry_ts FROM paper_trades WHERE state!='archived'")
    open_positions = [dict(r) for r in cur.fetchall()]
    for pos in open_positions:
        task_id = f"monitor-{pos['trade_id']}"
        # Check if task already exists
        exists = conn.execute(
            "SELECT 1 FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO tasks(id, type, payload, state, deps,
                    budget_cost, attempts, result_ref, updated_ts)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
                (task_id, "monitor", json.dumps({"trade_id": pos["trade_id"], "mint": pos["mint"]}),
                 "ready", "[]", 0, 0, "", _now()),
            )
            report["actions"].append(
                f"queued monitor task for open trade {pos['trade_id']} ({pos['mint']})"
            )

    # ── 3. Draft hypotheses → queue backtest tasks ──────────────────────────
    cur = conn.execute("SELECT id, title, rule_spec FROM hypotheses WHERE status IN ('draft','backtesting')")
    draft_hyps = [dict(r) for r in cur.fetchall()]
    for h in draft_hyps:
        task_id = f"backtest-{h['id']}"
        exists = conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO tasks(id, type, payload, state, deps,
                    budget_cost, attempts, result_ref, updated_ts)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
                (task_id, "backtest",
                 json.dumps({"hypothesis_id": h["id"], "title": h["title"]}),
                 "ready", "[]", 0, 0, "", _now()),
            )
            report["actions"].append(
                f"queued backtest task for draft hypothesis {h['id']}"
            )

    conn.commit()

    # ── 4. Context windows ─────────────────────────────────────────────────
    cur = conn.execute("SELECT session_id, last_shot_id, shots_count, token_budget_remaining FROM context_windows")
    sessions = [dict(r) for r in cur.fetchall()]

    # ── 5. Summary stats ─────────────────────────────────────────────────────
    counts = {}
    for st in ("ready", "blocked", "running", "done", "failed"):
        c = conn.execute("SELECT COUNT(*) FROM tasks WHERE state=?", (st,)).fetchone()[0]
        counts[st] = c

    conn.close()

    report.update({
        "interrupted_tasks_recovered": len(interrupted),
        "open_positions": len(open_positions),
        "draft_hypotheses": len(draft_hyps),
        "active_sessions": len(sessions),
        "queue_counts": counts,
    })

    return report

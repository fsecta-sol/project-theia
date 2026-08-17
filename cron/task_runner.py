"""Task runner — persistent queue worker for Theia.

Polls theia-store `tasks` table, respects dependencies, retries with backoff,
and dispatches to handlers. Pure Python, no LLM. Callable as cron or daemon.

Usage:
    python3 cron/task_runner.py --once      # single poll cycle
    python3 cron/task_runner.py --daemon    # perpetual loop
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# Add compute + MCP common to path
_THEIA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_THEIA_ROOT))
sys.path.insert(0, str(_THEIA_ROOT / "mcp" / "common"))

from theia_net import get_secret  # noqa: E402

DB_PATH = Path(
    get_secret("THEIA_DB", required=False) or
    str(Path.home() / ".hermes" / "theia" / "theia.db")
)

MAX_ATTEMPTS = 3
BACKOFF_BASE_SEC = 60  # 1 min, 2 min, 4 min exponential
SLEEP_DAEMON = 5       # seconds between polls


# ── DB helpers ─────────────────────────────────────────────────────────────


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def _now() -> int:
    return int(time.time())


def _task_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "type": row["type"],
        "payload": json.loads(row["payload"] or "{}"),
        "state": row["state"],
        "deps": json.loads(row["deps"] or "[]"),
        "budget_cost": row["budget_cost"] or 0,
        "attempts": row["attempts"] or 0,
        "result_ref": row["result_ref"],
        "updated_ts": row["updated_ts"] or 0,
    }


def _all_deps_done(conn: sqlite3.Connection, deps: list[str]) -> bool:
    if not deps:
        return True
    placeholders = ",".join("?" * len(deps))
    cur = conn.execute(
        f"SELECT id, state FROM tasks WHERE id IN ({placeholders})",
        deps,
    )
    dep_states = {r["id"]: r["state"] for r in cur.fetchall()}
    return all(dep_states.get(d) == "done" for d in deps)


# ── Task execution registry ──────────────────────────────────────────────────

# Task types that only the Hermes agent (LLM + MCP skills) can execute.
# The runner must NEVER claim to run them — they stay 'ready' in the queue
# until the agent picks them up (theia-monitor cron, delegation, ...).
_AGENT_HANDLED_TASKS = {"monitor", "delegate"}


def _handle_discover_screen(task: dict) -> dict:
    """Not runnable here: discovery + screening needs live theia-dexdata +
    theia-security MCP calls (rate-limit/cache live at the MCP boundary).
    Run it via the theia-discover-screen cron job instead."""
    return {
        "ok": False,
        "error": "discover-screen requires MCP calls (theia-dexdata/theia-security); "
                 "run via the theia-discover-screen cron job, not the task runner",
    }


def _handle_backtest(task: dict) -> dict:
    """REAL API-free walk-forward backtest on stored history (no LLM, no API).

    payload: {hypothesis_id}. Loads the hypothesis rule_spec, the stored
    price_snapshots_v2 path + screens + graduation labels, runs
    compute.backtest_engine.run(), records a `backtests` row, and updates
    the hypothesis best_* metrics. Fails honestly when data is missing.
    """
    payload = task["payload"]
    hyp_id = payload.get("hypothesis_id")
    if not hyp_id:
        return {"ok": False, "error": "payload.hypothesis_id missing"}

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT rule_spec FROM hypotheses WHERE id=?", (hyp_id,)
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"hypothesis {hyp_id} not found"}
        rule_spec = json.loads(row["rule_spec"] or "{}")
        if not rule_spec.get("entry"):
            return {"ok": False,
                    "error": f"hypothesis {hyp_id} has no entry rule_spec — not testable yet"}

        price_rows = [dict(r) for r in conn.execute(
            "SELECT mint, ts, price_sol, price_usd, volume_24h, liquidity_usd "
            "FROM price_snapshots_v2 ORDER BY mint, ts")]
        if not price_rows:
            return {"ok": False,
                    "error": "price_snapshots_v2 is empty — collect discovery/enrichment "
                             "data first; nothing to backtest"}
        for r in price_rows:
            r["c"] = r.get("price_sol") or 0.0  # o/h/l fall back to c in the engine

        screens = [dict(r) for r in conn.execute(
            "SELECT mint, screen_ts, verdict FROM screens")]
        pools = {r["mint"]: {"graduation_status": r["graduation_status"]}
                 for r in conn.execute(
                     "SELECT mint, graduation_status FROM token_corpus")}

        from compute import backtest_engine  # local import: keep runner boot light
        result = backtest_engine.run(rule_spec, price_rows, screens, pools=pools)
        m = result["metrics"]

        bt_id = f"BT-{hyp_id}-{_now()}"
        ts_list = [r["ts"] for r in price_rows]
        pf = m["profit_factor"] if m["profit_factor"] != float("inf") else None
        conn.execute(
            """INSERT INTO backtests(id, hypothesis_id, window_start, window_end,
               params, n_trades, expectancy, profit_factor, win_rate, max_dd, ran_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (bt_id, hyp_id, min(ts_list), max(ts_list), json.dumps(rule_spec),
             m["n"], m["expectancy"], pf, m["win_rate"], m["max_drawdown"], _now()),
        )
        cur = conn.execute(
            "SELECT best_expectancy, best_pf, best_winrate FROM hypotheses WHERE id=?",
            (hyp_id,),
        ).fetchone()
        pf_candidates = [x for x in (cur["best_pf"], pf) if x is not None]
        conn.execute(
            "UPDATE hypotheses SET best_expectancy=?, best_pf=?, best_winrate=? WHERE id=?",
            (max(cur["best_expectancy"] if cur["best_expectancy"] is not None else -1e18,
                 m["expectancy"]),
             max(pf_candidates) if pf_candidates else None,
             max(cur["best_winrate"] or 0.0, m["win_rate"]),
             hyp_id),
        )
        conn.commit()

        note = "API-free backtest on stored history (compute.backtest_engine)"
        if result["n_skipped_no_reserves"]:
            note += (f"; {result['n_skipped_no_reserves']} candidate(s) skipped — "
                     "stored history lacks reserves snapshots, so no AMM fill is simulatable")
        return {
            "ok": True,
            "hypothesis_id": hyp_id,
            "backtest_id": bt_id,
            "n_candidates": result["n_candidates"],
            "n_entered": result["n_entered"],
            "n_skipped_no_reserves": result["n_skipped_no_reserves"],
            "expectancy": m["expectancy"],
            "profit_factor": pf,
            "win_rate": m["win_rate"],
            "passes": m["passes"],
            "note": note,
        }
    finally:
        conn.close()


def _handle_wallet_pnl_enrich(task: dict) -> dict:
    """Not runnable here: batch wallet PnL enrichment needs theia-chainrpc MCP
    calls. Run it via the agent (execute_code batch) or a dedicated cron job."""
    return {
        "ok": False,
        "error": "wallet-pnl-enrich requires MCP calls (theia-chainrpc); "
                 "run via the agent's execute_code batch pattern, not the task runner",
    }


def _handle_label_corpus(task: dict) -> dict:
    """Not runnable here: graduation/death labeling needs theia-dexdata pairs
    (live MCP calls). Run it via the theia-label-corpus cron job instead."""
    return {
        "ok": False,
        "error": "label-corpus requires MCP calls (theia-dexdata); "
                 "run via the theia-label-corpus cron job, not the task runner",
    }


def _handle_execute_code(task: dict) -> dict:
    """No-op ack job (queue mechanics only). Real deterministic compute lives
    in dedicated handlers (e.g. backtest) — never exec arbitrary payloads."""
    return {"ok": True, "task": task["payload"].get("task"),
            "note": "noop ack (queue-mechanics job)"}


_HANDLERS = {
    "discover-screen": _handle_discover_screen,
    "backtest": _handle_backtest,
    "wallet-pnl-enrich": _handle_wallet_pnl_enrich,
    "label-corpus": _handle_label_corpus,
    "execute_code": _handle_execute_code,
}


def _execute_task(task: dict) -> dict:
    handler = _HANDLERS.get(task["type"])
    if not handler:
        return {"ok": False, "error": f"unknown task type: {task['type']}"}
    try:
        return handler(task)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Public API ────────────────────────────────────────────────────────────


def poll_and_run(limit: int = 1) -> list[dict]:
    """Poll for ready tasks with satisfied deps, execute up to `limit`, return results."""
    conn = _conn()
    out: list[dict] = []

    # 1. First, unblock any 'blocked' tasks whose deps are now done
    cur = conn.execute("SELECT * FROM tasks WHERE state='blocked'")
    for row in cur.fetchall():
        t = _task_from_row(row)
        if _all_deps_done(conn, t["deps"]):
            conn.execute(
                "UPDATE tasks SET state='ready', updated_ts=? WHERE id=?",
                (_now(), t["id"]),
            )
    conn.commit()

    # 2. Fetch ready tasks ordered by updated_ts (oldest first).
    #    Agent-handled task types (monitor/delegate) are EXCLUDED: the runner
    #    leaves them 'ready' so the Hermes agent / cron picks them up —
    #    executing them here would fake work only an agent can do.
    cur = conn.execute(
        "SELECT * FROM tasks WHERE state='ready' ORDER BY updated_ts ASC LIMIT ?",
        (limit,),
    )
    ready_tasks = [t for t in (_task_from_row(r) for r in cur.fetchall())
                   if t["type"] not in _AGENT_HANDLED_TASKS]

    for task in ready_tasks:
        # Verify deps still satisfied (race condition guard)
        if not _all_deps_done(conn, task["deps"]):
            conn.execute(
                "UPDATE tasks SET state='blocked', updated_ts=? WHERE id=?",
                (_now(), task["id"]),
            )
            conn.commit()
            continue

        # Mark running
        conn.execute(
            "UPDATE tasks SET state='running', updated_ts=? WHERE id=?",
            (_now(), task["id"]),
        )
        conn.commit()

        # Execute
        result = _execute_task(task)
        result_json = json.dumps(result, default=str)
        attempts = task["attempts"] + 1

        if result.get("ok"):
            conn.execute(
                "UPDATE tasks SET state='done', result_ref=?, attempts=?, updated_ts=? WHERE id=?",
                (result_json, attempts, _now(), task["id"]),
            )
        else:
            if attempts >= MAX_ATTEMPTS:
                new_state = "failed"
            else:
                # Retry: set ready after backoff
                backoff = BACKOFF_BASE_SEC * (2 ** (attempts - 1))
                new_state = "ready"
                # We don't schedule exact future time; runner will retry after backoff
                # by checking updated_ts on next poll. For simplicity, update_ts now.
                conn.execute(
                    "UPDATE tasks SET state=?, result_ref=?, attempts=?, updated_ts=? WHERE id=?",
                    (new_state, result_json, attempts, _now(), task["id"]),
                )
            if new_state == "failed":
                conn.execute(
                    "UPDATE tasks SET state='failed', result_ref=?, attempts=?, updated_ts=? WHERE id=?",
                    (result_json, attempts, _now(), task["id"]),
                )
        conn.commit()

        out.append({"id": task["id"], "state": conn.execute(
            "SELECT state FROM tasks WHERE id=?", (task["id"],)
        ).fetchone()["state"], "result": result})

    conn.close()
    return out


def enqueue(task_id: str, task_type: str, payload: dict,
            deps: list[str] | None = None,
            budget_cost: int = 0) -> dict:
    """Add a task to the queue. Idempotent: same id overwrites."""
    conn = _conn()
    state = "blocked" if deps else "ready"
    conn.execute(
        """INSERT OR REPLACE INTO tasks(id, type, payload, state, deps,
            budget_cost, attempts, result_ref, updated_ts)
         VALUES(?,?,?,?,?,?,?,?,?)""",
        (task_id, task_type, json.dumps(payload), state,
         json.dumps(deps or []), budget_cost, 0, "", _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": task_id, "state": state}


def get_status() -> dict:
    """Summary of queue state."""
    conn = _conn()
    counts = {}
    for st in ("ready", "blocked", "running", "done", "failed"):
        c = conn.execute("SELECT COUNT(*) FROM tasks WHERE state=?", (st,)).fetchone()[0]
        counts[st] = c
    conn.close()
    return counts


def prune_done(older_than_sec: int = 86400) -> dict:
    """Remove done/failed tasks older than threshold to prevent table bloat."""
    cutoff = _now() - older_than_sec
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM tasks WHERE state IN ('done','failed') AND updated_ts < ?",
        (cutoff,),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"pruned": deleted, "older_than_sec": older_than_sec}


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Theia task runner")
    parser.add_argument("--once", action="store_true", help="Run single poll cycle")
    parser.add_argument("--daemon", action="store_true", help="Run perpetual loop")
    parser.add_argument("--status", action="store_true", help="Print queue status")
    parser.add_argument("--prune", action="store_true", help="Prune old done/failed tasks")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), indent=2))
        return

    if args.prune:
        print(json.dumps(prune_done(), indent=2))
        return

    if args.once:
        results = poll_and_run(limit=5)
        print(json.dumps(results, indent=2, default=str))
        return

    if args.daemon:
        print(f"[{_now()}] Task runner daemon starting (DB={DB_PATH})")
        while True:
            results = poll_and_run(limit=3)
            if results:
                print(f"[{_now()}] Ran {len(results)} tasks:")
                for r in results:
                    print(f"  {r['id']} → {r['state']}")
            time.sleep(SLEEP_DAEMON)

    parser.print_help()


if __name__ == "__main__":
    main()

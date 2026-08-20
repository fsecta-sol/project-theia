"""Focused tests for the read-only wallet pipeline health watchdog."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "cron" / "pipeline_health.py"
_SPEC = importlib.util.spec_from_file_location("pipeline_health", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
check_health = _MODULE.check_health


JOB_IDS = (
    "theia-wallet-pipeline",
    "theia-wallet-monitor",
    "theia-wallet-discovery",
    "theia-wallet-report",
)
NOW = 1_755_663_600.0


def make_execution_db(path: Path, rows: list[tuple[str, str, str, str, str, str]]) -> None:
    """Create a fixture database containing execution rows."""
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE executions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            source TEXT NOT NULL,
            process_id TEXT NOT NULL,
            pid INTEGER NOT NULL,
            process_started_at INTEGER,
            status TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT
        )
        """
    )
    con.executemany(
        """
        INSERT INTO executions
          (id, job_id, source, process_id, pid, status,
           claimed_at, started_at, finished_at, error)
        VALUES (?, ?, 'direct', 'process', 1, ?, ?, ?, ?, NULL)
        """,
        rows,
    )
    con.commit()
    con.close()


class PipelineHealthTests(unittest.TestCase):
    def test_recent_completed_runs_and_executable_wrappers_are_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "executions.db"
            scripts = root / "scripts"
            scripts.mkdir()
            for job_id in JOB_IDS:
                wrapper = scripts / f"{job_id}.sh"
                wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
                wrapper.chmod(0o755)

            finished = "2025-08-20T04:19:00+00:00"
            rows = [
                (str(index), job_id, "completed", finished, finished, finished)
                for index, job_id in enumerate(JOB_IDS)
            ]
            make_execution_db(db, rows)

            report = check_health(
                db_path=db,
                scripts_dir=scripts,
                now=NOW,
                thresholds={job_id: 120 for job_id in JOB_IDS},
            )

            self.assertEqual(report.exit_code, 0)
            self.assertEqual(report.overall, "OK")
            self.assertTrue(all(item.status == "OK" for item in report.jobs))
            self.assertTrue(all("OK" in line for line in report.summary.splitlines()))

    def test_missing_execution_database_is_an_explicit_alert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            for job_id in JOB_IDS:
                wrapper = scripts / f"{job_id}.sh"
                wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
                wrapper.chmod(0o755)

            report = check_health(
                db_path=root / "missing-executions.db",
                scripts_dir=scripts,
                now=NOW,
                thresholds={job_id: 120 for job_id in JOB_IDS},
            )

            self.assertEqual(report.overall, "ALERT")
            self.assertTrue(all(item.detail == "executions database missing" for item in report.jobs))
            self.assertIn("executions database missing", report.summary)
            self.assertNotEqual(report.exit_code, 0)

    def test_failed_latest_run_is_reported_as_an_alert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "executions.db"
            scripts = root / "scripts"
            scripts.mkdir()
            for job_id in JOB_IDS:
                wrapper = scripts / f"{job_id}.sh"
                wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
                wrapper.chmod(0o755)

            finished = "2025-08-20T04:19:00+00:00"
            rows = [
                ("failed", "theia-wallet-pipeline", "failed", finished, finished, finished),
                *[
                    (str(index), job_id, "completed", finished, finished, finished)
                    for index, job_id in enumerate(JOB_IDS[1:], start=1)
                ],
            ]
            make_execution_db(db, rows)

            report = check_health(
                db_path=db,
                scripts_dir=scripts,
                now=NOW,
                thresholds={job_id: 120 for job_id in JOB_IDS},
            )

            pipeline = report.jobs[0]
            self.assertEqual(pipeline.status, "ALERT")
            self.assertEqual(pipeline.detail, "last run failed")
            self.assertIn("status=failed", report.summary)
            self.assertNotEqual(report.exit_code, 0)


if __name__ == "__main__":
    unittest.main()

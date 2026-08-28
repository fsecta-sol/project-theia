#!/usr/bin/env python3
"""Read-only freshness watchdog for Theia's wallet pipeline jobs.

The checker only opens the execution database in SQLite read-only mode and
never starts, stops, or modifies a runtime process.  It is intentionally
stdlib-only so it can run from the cron profile without project dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


REQUIRED_JOBS = (
    "theia-wallet-pipeline",
    "theia-wallet-monitor",
    "theia-wallet-discovery",
    "theia-source2-discovery",
    "theia-wallet-report",
)
DEFAULT_THRESHOLDS = {
    "theia-wallet-pipeline": 30 * 60,
    "theia-wallet-monitor": 15 * 60,
    "theia-wallet-discovery": 12 * 60 * 60,
    "theia-source2-discovery": 12 * 60 * 60,
    "theia-wallet-report": 36 * 60 * 60,
}
RUNTIME_SCRIPTS_DIR = Path("/home/hermes/.hermes/profiles/theia/scripts")
EXECUTIONS_DB = Path("/home/hermes/.hermes/profiles/theia/cron/executions.db")
JOBS_CONFIG = Path("/home/hermes/.hermes/profiles/theia/cron/jobs.json")
REPO_SOURCES = {
    "theia-wallet-pipeline": "wallet_pipeline_v3.py",
    "theia-wallet-monitor": "wallet_monitor_v2.py",
    "theia-wallet-discovery": "wallet_discovery_run.py",
    "theia-source2-discovery": "discover_source2.py",
    "theia-wallet-report": "wallet_report_v2.py",
}


@dataclass(frozen=True)
class JobResult:
    """Health evidence for one required job."""

    job_id: str
    status: str
    age_seconds: int | None
    threshold_seconds: int
    source: str
    detail: str
    execution_status: str = "missing"


@dataclass(frozen=True)
class FileResult:
    """Health evidence for one runtime wrapper or source hash."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class HealthReport:
    """Complete watchdog result, including stable display text."""

    jobs: tuple[JobResult, ...]
    wrappers: tuple[FileResult, ...]
    hashes: tuple[FileResult, ...]
    overall: str
    exit_code: int
    summary: str


def _timestamp(value: object) -> float | None:
    """Convert an execution timestamp to Unix seconds without local-time drift."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _job_id_mapping(jobs_config_path: Path | None) -> dict[str, str]:
    """Map logical job names to their configured runtime IDs."""
    mapping = {job_id: job_id for job_id in REQUIRED_JOBS}
    path = jobs_config_path or JOBS_CONFIG
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return mapping

    entries = config.get("jobs", []) if isinstance(config, dict) else []
    if not isinstance(entries, list):
        return mapping
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        logical_id = entry.get("name")
        runtime_id = entry.get("id")
        if logical_id in mapping and isinstance(runtime_id, str) and runtime_id:
            mapping[logical_id] = runtime_id
    return mapping


def _read_latest_runs(
    db_path: Path,
    job_id_mapping: Mapping[str, str] | None = None,
) -> dict[str, tuple[float, str, str]]:
    """Return newest execution event per logical job using a read-only SQLite handle."""
    if not db_path.is_file():
        return {}
    uri = f"file:{db_path.resolve()}?mode=ro"
    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(uri, uri=True)
        rows = con.execute(
            """
            SELECT job_id, status, claimed_at, started_at, finished_at
            FROM executions
            """
        ).fetchall()
    except (sqlite3.Error, OSError):
        return {}
    finally:
        if con is not None:
            con.close()

    latest: dict[str, tuple[float, str, str]] = {}
    logical_by_runtime_id = {job_id: job_id for job_id in REQUIRED_JOBS}
    for logical_id, runtime_id in (job_id_mapping or {}).items():
        if logical_id in REQUIRED_JOBS:
            logical_by_runtime_id[runtime_id] = logical_id
    for job_id, status, claimed_at, started_at, finished_at in rows:
        logical_id = logical_by_runtime_id.get(job_id)
        if logical_id is None:
            continue
        event_time = _timestamp(finished_at) or _timestamp(started_at) or _timestamp(claimed_at)
        if event_time is None:
            continue
        # A 'running' event is evidence of liveness, but its start time keeps
        # advancing with every overlapping tick — which makes a 5-min monitor
        # look perpetually "running" and never "completed" when the watchdog
        # races it. Prefer the newest COMPLETED event when one exists, so the
        # watchdog judges freshness, not race conditions.
        if logical_id not in latest or event_time > latest[logical_id][0]:
            latest[logical_id] = (event_time, str(status), "executions")
    # Second pass: prefer completed events over in-flight ones (race fix).
    completed: dict[str, tuple[float, str, str]] = {}
    for job_id, status, claimed_at, started_at, finished_at in rows:
        logical_id = logical_by_runtime_id.get(job_id)
        if logical_id is None or status != "completed":
            continue
        event_time = _timestamp(finished_at) or _timestamp(claimed_at)
        if event_time is None:
            continue
        if logical_id not in completed or event_time > completed[logical_id][0]:
            completed[logical_id] = (event_time, "completed", "executions")
    for logical_id, event in completed.items():
        latest[logical_id] = event
    return latest


def _thresholds(overrides: Mapping[str, float] | None) -> dict[str, int]:
    values = {job_id: int(DEFAULT_THRESHOLDS[job_id]) for job_id in REQUIRED_JOBS}
    for job_id, value in (overrides or {}).items():
        if job_id not in values:
            continue
        if value <= 0:
            raise ValueError(f"threshold for {job_id} must be positive")
        values[job_id] = int(value)
    return values


def _wrapper_results(scripts_dir: Path) -> tuple[FileResult, ...]:
    results = []
    for job_id in REQUIRED_JOBS:
        path = scripts_dir / f"{job_id}.sh"
        if not path.is_file():
            results.append(FileResult(job_id, "ALERT", "wrapper missing"))
        elif not (path.stat().st_mode & stat.S_IXUSR):
            results.append(FileResult(job_id, "ALERT", "wrapper not executable"))
        else:
            results.append(FileResult(job_id, "OK", "wrapper executable"))
    return tuple(results)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _enabled_jobs(jobs_config_path: Path | None) -> set[str]:
    """Jobs that are enabled in the scheduler config; empty set → assume all required.

    A required job that is intentionally DISABLED (e.g. theia-wallet-report,
    paused since 2026-08-22) must not produce a perpetual "no completed run"
    ALERT. If the config can't be read, fall back to all required jobs.
    """
    path = jobs_config_path or JOBS_CONFIG
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(REQUIRED_JOBS)
    entries = config.get("jobs", []) if isinstance(config, dict) else []
    if not isinstance(entries, list):
        return set(REQUIRED_JOBS)
    enabled = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") in REQUIRED_JOBS and entry.get("enabled"):
            enabled.add(entry["name"])
    return enabled or set(REQUIRED_JOBS)


def check_health(
    *,
    db_path: Path,
    scripts_dir: Path,
    now: float | None = None,
    thresholds: Mapping[str, float] | None = None,
    output_paths: Mapping[str, Path] | None = None,
    repo_scripts_dir: Path | None = None,
    check_hashes: bool = False,
    jobs_config_path: Path | None = None,
) -> HealthReport:
    """Check pipeline freshness and wrapper state without mutating any path."""
    current = float(now) if now is not None else time.time()
    limits = _thresholds(thresholds)
    evidence = _read_latest_runs(db_path, _job_id_mapping(jobs_config_path))
    required = _enabled_jobs(jobs_config_path)
    output_paths = output_paths or {}
    jobs = []
    for job_id in REQUIRED_JOBS:
        if job_id not in required:
            jobs.append(JobResult(job_id, "OK", None, limits[job_id], "config", "disabled (not required)", "disabled"))
            continue
        output = output_paths.get(job_id)
        output_time = output.stat().st_mtime if output and output.is_file() else None
        db_event = evidence.get(job_id)
        db_time = db_event[0] if db_event else None
        if output_time is not None and (db_time is None or output_time > db_time):
            event_time, source, event_status = output_time, "output", "completed"
        elif db_event is not None:
            event_time, event_status, source = db_event
        else:
            event_time, source, event_status = None, "none", "missing"

        if event_time is None:
            detail = "executions database missing" if not db_path.is_file() else "no completed run"
            jobs.append(JobResult(job_id, "ALERT", None, limits[job_id], source, detail, event_status))
            continue
        age = max(0, int(current - event_time))
        if event_status != "completed":
            status = "ALERT"
            detail = "last run failed" if event_status == "failed" else f"last run status={event_status}"
        elif age > limits[job_id]:
            status, detail = "ALERT", "stale"
        else:
            status, detail = "OK", "fresh"
        jobs.append(JobResult(job_id, status, age, limits[job_id], source, detail, event_status))

    wrappers = _wrapper_results(scripts_dir)
    hashes: tuple[FileResult, ...] = ()
    if check_hashes:
        if repo_scripts_dir is None:
            raise ValueError("repo_scripts_dir is required when check_hashes is enabled")
        hash_results = []
        for job_id in REQUIRED_JOBS:
            runtime = scripts_dir / REPO_SOURCES[job_id]
            source = repo_scripts_dir / REPO_SOURCES[job_id]
            if not runtime.is_file() or not source.is_file():
                hash_results.append(FileResult(job_id, "ALERT", "source or runtime script missing"))
            elif _sha256(runtime) != _sha256(source):
                hash_results.append(FileResult(job_id, "ALERT", "runtime hash differs from repo"))
            else:
                hash_results.append(FileResult(job_id, "OK", "runtime hash matches repo"))
        hashes = tuple(hash_results)

    has_alert = any(item.status == "ALERT" for item in (*jobs, *wrappers, *hashes))
    overall = "ALERT" if has_alert else "OK"
    lines = [f"THEIA PIPELINE HEALTH: {overall}"]
    for item in jobs:
        age = "missing" if item.age_seconds is None else f"{item.age_seconds}s"
        lines.append(
            f"{item.job_id}: {item.status} source={item.source} status={item.execution_status} age={age} "
            f"threshold={item.threshold_seconds}s detail={item.detail}"
        )
    for item in wrappers:
        lines.append(f"{item.name} wrapper: {item.status} {item.detail}")
    for item in hashes:
        lines.append(f"{item.name} hash: {item.status} {item.detail}")
    return HealthReport(tuple(jobs), wrappers, hashes, overall, 1 if has_alert else 0, "\n".join(lines))


def _parse_pairs(values: Sequence[str], label: str) -> dict[str, str]:
    result = {}
    for value in values:
        key, separator, raw = value.partition("=")
        if not separator or key not in REQUIRED_JOBS or not raw:
            raise ValueError(f"{label} must use JOB=value for a required job: {value}")
        result[key] = raw
    return result


def _environment_thresholds() -> dict[str, int]:
    result: dict[str, int] = {}
    for job_id in REQUIRED_JOBS:
        suffix = job_id.upper().replace("-", "_")
        raw = os.environ.get(f"THEIA_HEALTH_MAX_AGE_{suffix}_SECONDS")
        if raw is not None:
            result[job_id] = int(raw)
    raw_global = os.environ.get("THEIA_HEALTH_MAX_AGE_SECONDS")
    if raw_global is not None:
        result.update({job_id: int(raw_global) for job_id in REQUIRED_JOBS})
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=EXECUTIONS_DB)
    parser.add_argument("--scripts-dir", type=Path, default=RUNTIME_SCRIPTS_DIR)
    parser.add_argument("--max-age", action="append", default=[], metavar="JOB=SECONDS")
    parser.add_argument("--output", action="append", default=[], metavar="JOB=PATH")
    parser.add_argument("--check-hashes", action="store_true")
    parser.add_argument("--repo-scripts-dir", type=Path)
    parser.add_argument("--jobs-config", type=Path, default=JOBS_CONFIG)
    args = parser.parse_args(argv)
    try:
        max_age = _environment_thresholds()
        max_age.update({job_id: int(value) for job_id, value in _parse_pairs(args.max_age, "--max-age").items()})
        outputs = {job_id: Path(value) for job_id, value in _parse_pairs(args.output, "--output").items()}
        report = check_health(
            db_path=args.db,
            scripts_dir=args.scripts_dir,
            thresholds=max_age,
            output_paths=outputs,
            repo_scripts_dir=args.repo_scripts_dir,
            check_hashes=args.check_hashes,
            jobs_config_path=args.jobs_config,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"THEIA PIPELINE HEALTH: ALERT\nconfiguration error: {exc}")
        return 2
    print(report.summary)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())

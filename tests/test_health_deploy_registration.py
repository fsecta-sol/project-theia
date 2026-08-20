"""Focused validation for the read-only pipeline health deployment registration."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DEPLOY_SCRIPT = ROOT / "deploy" / "deploy_sync.sh"
HEALTH_SOURCE = ROOT / "cron" / "pipeline_health.py"
JOBS_SOURCE = ROOT / "cron" / "theia-jobs.json"


class HealthDeployRegistrationTests(unittest.TestCase):
    def test_source_job_registers_enabled_read_only_five_minute_script(self) -> None:
        config = json.loads(JOBS_SOURCE.read_text(encoding="utf-8"))
        matches = [job for job in config["jobs"] if job.get("id") == "theia-pipeline-health"]

        self.assertEqual(len(matches), 1)
        job = matches[0]
        self.assertTrue(job["enabled"])
        self.assertTrue(job["no_agent"])
        self.assertEqual(job["script"], "theia-pipeline-health.sh")
        self.assertEqual(job["schedule"]["expr"], "*/5 * * * *")
        self.assertNotIn("delivery", job)

    def test_apply_syncs_health_source_and_executable_wrapper_to_runtime_script_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {**os.environ, "HOME": str(home)}
            result = subprocess.run(
                ["bash", str(DEPLOY_SCRIPT), "--apply"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            expected_source = HEALTH_SOURCE.read_bytes()
            for path in (
                home / ".hermes" / "profiles" / "theia" / "scripts" / "pipeline_health.py",
                home / ".hermes" / "scripts" / "pipeline_health.py",
                home / "theia-gate" / "pipeline_health.py",
            ):
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.read_bytes(), expected_source)

            for directory_path in (
                home / ".hermes" / "profiles" / "theia" / "scripts",
                home / ".hermes" / "scripts",
            ):
                wrapper = directory_path / "theia-pipeline-health.sh"
                self.assertTrue(wrapper.is_file(), wrapper)
                self.assertTrue(wrapper.stat().st_mode & stat.S_IXUSR, wrapper)
                self.assertIn("pipeline_health.py", wrapper.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

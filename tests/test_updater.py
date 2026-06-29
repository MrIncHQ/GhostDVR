from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.updater import check_update_status, run_update


class UpdaterTests(unittest.TestCase):
    def test_check_update_status_reports_non_git_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status = check_update_status(root=Path(temp_dir))

            self.assertFalse(status.git_available)
            self.assertFalse(status.update_available)
            self.assertIn("Git checkout", status.message)

    def test_check_update_status_reports_behind_count_after_fetch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            with patch("ghost_dvr.updater.subprocess.run") as run:
                run.side_effect = [
                    _git_result("abc123\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result(""),
                    _git_result("2\n"),
                ]

                status = check_update_status(fetch=True, root=root)

            self.assertTrue(status.git_available)
            self.assertTrue(status.update_available)
            self.assertEqual(status.behind_count, 2)
            self.assertIn("2 commit", status.message)

    def test_run_update_reports_restart_message_after_pull(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            with patch("ghost_dvr.updater.subprocess.run") as run:
                run.side_effect = [
                    _git_result("abc123\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("1\n"),
                    _git_result("Updating\n"),
                    _git_result("def456\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("0\n"),
                ]

                status = run_update(root=root)

            self.assertEqual(status.commit, "def456")
            self.assertFalse(status.update_available)
            self.assertIn("Restart", status.message)


def _git_result(stdout: str, stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        ["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.updater import (
    RESTART_EXIT_CODE,
    check_update_status,
    run_update,
    update_applied,
)


class UpdaterTests(unittest.TestCase):
    def test_restart_exit_code_matches_launcher_contract(self):
        self.assertEqual(RESTART_EXIT_CODE, 75)

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
                    _git_result(""),
                    _git_result("Updating\n"),
                    _git_result("def456\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("0\n"),
                ]

                status = run_update(root=root)

            self.assertEqual(status.commit, "def456")
            self.assertFalse(status.update_available)
            self.assertIn("Restarting", status.message)
            self.assertTrue(update_applied(status))

    def test_run_update_restores_known_launcher_changes_before_pull(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            with patch("ghost_dvr.updater.subprocess.run") as run:
                run.side_effect = [
                    _git_result("abc123\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("1\n"),
                    _git_result(" M Run_Ghost_DVR_API_Pi.sh\n"),
                    _git_result(""),
                    _git_result("Updating\n"),
                    _git_result("def456\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("0\n"),
                ]

                status = run_update(root=root)

            self.assertTrue(update_applied(status))
            self.assertIn(
                ["git", "restore", "--", "Run_Ghost_DVR_API_Pi.sh"],
                [call.args[0] for call in run.call_args_list],
            )

    def test_run_update_blocks_unknown_local_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            with patch("ghost_dvr.updater.subprocess.run") as run:
                run.side_effect = [
                    _git_result("abc123\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("1\n"),
                    _git_result(" M README.md\n"),
                ]

                status = run_update(root=root)

            self.assertFalse(update_applied(status))
            self.assertIn("README.md", status.message)

    def test_git_error_message_keeps_useful_pull_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            with patch("ghost_dvr.updater.subprocess.run") as run:
                run.side_effect = [
                    _git_result("abc123\n"),
                    _git_result("main\n"),
                    _git_result("origin/main\n"),
                    _git_result("1\n"),
                    _git_result(""),
                    _git_result(
                        "",
                        stderr=(
                            "error: Your local changes to the following files would be overwritten by merge:\n"
                            "\tREADME.md\n"
                            "Please commit your changes or stash them before you merge.\n"
                            "Aborting\n"
                        ),
                        returncode=1,
                    ),
                ]

                status = run_update(root=root)

            self.assertIn("README.md", status.message)
            self.assertNotEqual(status.message, "Update failed: Aborting")


def _git_result(stdout: str, stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        ["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


if __name__ == "__main__":
    unittest.main()

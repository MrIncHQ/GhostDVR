from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ghost_dvr import __version__


@dataclass(frozen=True)
class UpdateStatus:
    version: str
    commit: str
    branch: str
    git_available: bool
    update_available: bool
    behind_count: int
    checked_at: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def check_update_status(
    *,
    fetch: bool = False,
    root: Path | None = None,
    timeout_seconds: int = 60,
) -> UpdateStatus:
    root = root or repo_root()
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if not (root / ".git").exists():
        return UpdateStatus(
            version=__version__,
            commit="-",
            branch="-",
            git_available=False,
            update_available=False,
            behind_count=0,
            checked_at=checked_at,
            message="Update checks require a Git checkout",
        )

    commit = _git_text(["rev-parse", "--short", "HEAD"], root, timeout_seconds)
    branch = _git_text(["rev-parse", "--abbrev-ref", "HEAD"], root, timeout_seconds)
    upstream = _git_text(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        root,
        timeout_seconds,
    )

    if not upstream:
        return UpdateStatus(
            version=__version__,
            commit=commit or "-",
            branch=branch or "-",
            git_available=True,
            update_available=False,
            behind_count=0,
            checked_at=checked_at,
            message="No upstream Git branch is configured",
        )

    if fetch:
        result = _run_git(["fetch", "--quiet", "--prune"], root, timeout_seconds)
        if result.returncode != 0:
            return UpdateStatus(
                version=__version__,
                commit=commit or "-",
                branch=branch or "-",
                git_available=True,
                update_available=False,
                behind_count=0,
                checked_at=checked_at,
                message=_git_error_message(result, "Update check failed"),
            )

    behind_text = _git_text(["rev-list", "--count", f"HEAD..{upstream}"], root, timeout_seconds)
    behind_count = int(behind_text or "0")
    message = (
        f"Update available: {behind_count} commit(s) behind {upstream}"
        if behind_count > 0
        else "Ghost DVR is up to date"
    )
    return UpdateStatus(
        version=__version__,
        commit=commit or "-",
        branch=branch or "-",
        git_available=True,
        update_available=behind_count > 0,
        behind_count=behind_count,
        checked_at=checked_at,
        message=message,
    )


def run_update(
    *,
    root: Path | None = None,
    timeout_seconds: int = 180,
) -> UpdateStatus:
    root = root or repo_root()
    current = check_update_status(fetch=False, root=root)
    if not current.git_available:
        return current

    result = _run_git(["pull", "--ff-only"], root, timeout_seconds)
    if result.returncode != 0:
        return UpdateStatus(
            version=__version__,
            commit=current.commit,
            branch=current.branch,
            git_available=True,
            update_available=current.update_available,
            behind_count=current.behind_count,
            checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            message=_git_error_message(result, "Update failed"),
        )

    updated = check_update_status(fetch=False, root=root)
    return UpdateStatus(
        version=updated.version,
        commit=updated.commit,
        branch=updated.branch,
        git_available=True,
        update_available=updated.update_available,
        behind_count=updated.behind_count,
        checked_at=updated.checked_at,
        message="Update applied. Restarting Ghost DVR.",
    )


def restart_current_process(delay_seconds: float = 1.0) -> None:
    threading.Thread(
        target=_restart_current_process,
        args=(delay_seconds,),
        daemon=True,
        name="ghost-dvr-process-restart",
    ).start()


def update_applied(status: UpdateStatus) -> bool:
    return status.git_available and status.message.startswith("Update applied.")


def _restart_current_process(delay_seconds: float) -> None:
    time.sleep(delay_seconds)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _git_text(args: list[str], root: Path, timeout_seconds: int) -> str:
    result = _run_git(args, root, timeout_seconds)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_git(
    args: list[str],
    root: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            env=env,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            ["git", *args],
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def _git_error_message(
    result: subprocess.CompletedProcess[str],
    fallback: str,
) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    if not detail:
        return fallback
    return f"{fallback}: {detail.splitlines()[-1]}"

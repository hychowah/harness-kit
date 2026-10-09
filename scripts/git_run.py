"""Run git for this kit.

A Windows checkout opened from WSL may refuse the repo or the index lock.
The first try is ordinary git. A dubious-ownership failure is retried once with
``safe.directory=*`` on that command only. An index lock that still cannot be
created is retried with Git for Windows, which can write this checkout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git_exe() -> str | None:
    """Git for Windows, when this tree is a Windows checkout opened from WSL."""
    candidate = Path("/mnt/c/Program Files/Git/cmd/git.exe")
    if candidate.is_file():
        return str(candidate)
    return None


def _win_path(path: str) -> str:
    if not path.startswith("/mnt/"):
        return path
    converted = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True)
    if converted.returncode != 0 or not converted.stdout.strip():
        return path
    return converted.stdout.strip()


def _args_for_git_exe(args: tuple[str, ...]) -> list[str]:
    return [_win_path(arg) if arg.startswith("/mnt/") else arg for arg in args]


def git_exec(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git. See the module docstring for the WSL retry."""
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode == 0:
        return result
    blob = result.stderr or ""
    if "dubious ownership" in blob:
        result = subprocess.run(
            ["git", "-c", "safe.directory=*", *args],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result
        blob = result.stderr or ""
    exe = _git_exe()
    if exe and (
        "index.lock" in blob or "dubious ownership" in blob or "unable to create" in blob.lower()
    ):
        return subprocess.run([exe, *_args_for_git_exe(args)], capture_output=True, text=True)
    return result


def git_out(repo: Path, *args: str) -> str | None:
    result = git_exec("-C", str(repo), *args)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

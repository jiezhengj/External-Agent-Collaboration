"""Cross-platform bounded subprocess execution for local CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
from pathlib import Path
import subprocess
from typing import Sequence


PROCESS_CLEANUP_GRACE_SECONDS = 1.0


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _creation_options() -> dict[str, int | bool]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _signal_process_group(process: subprocess.Popen[str], *, hard: bool) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        if not hard:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except (AttributeError, OSError, ValueError):
                pass
        elif process.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=PROCESS_CLEANUP_GRACE_SECONDS,
                )
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                pass
        try:
            process.terminate() if not hard else process.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(process.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except ProcessLookupError:
        pass


def _communicate(process: subprocess.Popen[str], timeout: float | None) -> tuple[str, str]:
    stdout, stderr = process.communicate(timeout=timeout)
    return _text(stdout), _text(stderr)


def run_bounded(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float | None,
) -> ProcessResult:
    """Run a CLI and terminate its process group when the deadline expires.

    ``subprocess.run(timeout=...)`` only manages the direct child. CLI launchers
    can leave descendants holding stdout/stderr open, so adapters need an
    explicit process group and bounded cleanup on both POSIX and Windows.
    """
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_creation_options(),
    )
    try:
        stdout, stderr = _communicate(process, timeout if timeout and timeout > 0 else None)
        return ProcessResult(process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as first_timeout:
        partial_stdout = _text(first_timeout.stdout)
        partial_stderr = _text(first_timeout.stderr)
        _signal_process_group(process, hard=False)
        try:
            stdout, stderr = _communicate(process, PROCESS_CLEANUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired as second_timeout:
            _signal_process_group(process, hard=True)
            try:
                stdout, stderr = _communicate(process, PROCESS_CLEANUP_GRACE_SECONDS)
            except subprocess.TimeoutExpired as final_timeout:
                stdout = _text(final_timeout.stdout) or partial_stdout
                stderr = _text(final_timeout.stderr) or partial_stderr
                try:
                    process.kill()
                    process.wait(timeout=PROCESS_CLEANUP_GRACE_SECONDS)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return ProcessResult(124, stdout or partial_stdout, stderr or partial_stderr, timed_out=True)

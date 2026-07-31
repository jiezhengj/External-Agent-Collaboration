"""Small, dependency-free platform helpers for the collaboration control plane."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any


def host_platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "posix"


def macos_keychain_supported() -> bool:
    return host_platform() == "macos"


def macos_keychain_unavailable_message() -> str:
    return "macOS Keychain authentication is unavailable on this platform; use auth_token or required_environment."


def supports_posix_shell_fallback() -> bool:
    return host_platform() != "windows"


def normalized_working_directory(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def workspace_identity(path: Path | str) -> str:
    value = normalized_working_directory(path).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def infer_path_platform(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        return "windows"
    if normalized.startswith("/Users/"):
        return "macos"
    if normalized.startswith("/"):
        return "posix"
    return None


def record_host_platform(record: dict[str, Any]) -> str | None:
    declared = record.get("host_platform")
    if declared in {"windows", "macos", "posix"}:
        return str(declared)
    return infer_path_platform(record.get("working_directory"))


def session_matches_workspace(session: dict[str, Any], workdir: Path) -> bool:
    if record_host_platform(session) != host_platform():
        return False
    recorded_identity = session.get("workspace_identity")
    if isinstance(recorded_identity, str) and recorded_identity:
        return recorded_identity == workspace_identity(workdir)
    recorded_workdir = session.get("working_directory")
    return isinstance(recorded_workdir, str) and normalized_working_directory(recorded_workdir) == normalized_working_directory(workdir)


def capability_matches_host(record: dict[str, Any] | None) -> bool:
    return bool(record and record.get("host_platform") == host_platform())

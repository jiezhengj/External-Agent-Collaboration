"""Load non-secret local profiles for a harness that owns cached authentication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class HarnessProfileError(ValueError):
    pass


def profile_path(control_root: Path) -> Path:
    return control_root / "harness-profiles.local.json"


def trust_path(control_root: Path) -> Path:
    return control_root / "trusted-harnesses.local.json"


def load_profiles(control_root: Path) -> dict[str, dict[str, Any]]:
    path = profile_path(control_root)
    if not path.is_file():
        raise HarnessProfileError("Harness profiles are missing. Copy harness-profiles.local.example.json to harness-profiles.local.json and configure a non-secret profile.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessProfileError(f"Invalid JSON in {path.name}: {exc.msg}") from exc
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        raise HarnessProfileError("harness-profiles.local.json must contain a profiles object.")
    output: dict[str, dict[str, Any]] = {}
    for name, profile in profiles.items():
        if not isinstance(name, str) or not isinstance(profile, dict):
            raise HarnessProfileError("Each harness profile must have a string name and object value.")
        if profile.get("harness") != "antigravity":
            raise HarnessProfileError(f"Harness profile '{name}' must declare harness=antigravity.")
        mode = profile.get("mode", "plan")
        if mode not in {"plan", "accept-edits"}:
            raise HarnessProfileError(f"Harness profile '{name}' mode must be plan or accept-edits.")
        if mode == "accept-edits":
            scope = profile.get("execution_scope")
            if not isinstance(scope, dict):
                raise HarnessProfileError(f"Harness profile '{name}' accept-edits mode requires execution_scope.")
            paths = scope.get("allowed_paths")
            commands = scope.get("allowed_commands")
            if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item and not Path(item).is_absolute() and ".." not in Path(item).parts for item in paths):
                raise HarnessProfileError(f"Harness profile '{name}' execution_scope.allowed_paths must be non-empty safe relative paths.")
            if not isinstance(commands, list) or not all(isinstance(item, str) and item and "\n" not in item for item in commands):
                raise HarnessProfileError(f"Harness profile '{name}' execution_scope.allowed_commands must be a string list.")
        if any(marker in key.upper() for key in profile for marker in ("TOKEN", "SECRET", "PASSWORD", "KEY")):
            raise HarnessProfileError(f"Harness profile '{name}' must not contain credentials; Antigravity uses its interactive cached login.")
        launcher = profile.get("launcher", "agy")
        if not isinstance(launcher, str) or not launcher or "/" in launcher or "\\" in launcher:
            raise HarnessProfileError(f"Harness profile '{name}' launcher must be a PATH command.")
        output[name] = dict(profile)
    return output


def profile_fingerprint(profile: dict[str, Any]) -> str:
    encoded = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def trusted(control_root: Path, profile_name: str, profile: dict[str, Any]) -> bool:
    path = trust_path(control_root)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    record = data.get("profiles", {}).get(profile_name) if isinstance(data, dict) else None
    return isinstance(record, dict) and record.get("approved") is True and record.get("profile_fingerprint") == profile_fingerprint(profile)

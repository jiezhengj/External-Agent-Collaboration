#!/usr/bin/env python3
"""Migrate only state that is provably owned by this Skill repository.

The command deliberately never copies state into a target project.  ``--dry-run``
is the default and emits counts, schema versions and content hashes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_state import RUNTIME_SCHEMA_VERSION, decorate_legacy_record
from state_store import save
from workspace_context import skill_project_root


ROOT = skill_project_root()
CONTROL = ROOT / ".ai-collaboration"
RUNTIME_FILES = {
    "sessions": CONTROL / "sessions.json",
    "topics": CONTROL / "topics.json",
    "goals": CONTROL / "goals",
    "trust": CONTROL / "trusted-providers.local.json",
    "health": CONTROL / "provider-health.json",
    "metrics": CONTROL / "provider-metrics.json",
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def annotate(name: str, value: Any) -> tuple[Any, int]:
    if value is None:
        return value, 0
    changed = 0
    if name == "sessions" and isinstance(value, dict):
        for item in value.get("sessions", []):
            if isinstance(item, dict) and decorate_legacy_record(item):
                changed += 1
        value["schema_version"] = max(RUNTIME_SCHEMA_VERSION, int(value.get("schema_version", 1)))
    elif name in {"trust", "health"} and isinstance(value, dict):
        for provider, item in value.get("providers", {}).items():
            if isinstance(item, dict) and decorate_legacy_record(item, str(provider)):
                changed += 1
        value["schema_version"] = max(RUNTIME_SCHEMA_VERSION, int(value.get("schema_version", 1)))
    elif name == "metrics" and isinstance(value, dict):
        for item in value.get("events", []):
            if isinstance(item, dict) and decorate_legacy_record(item, str(item.get("provider", "unknown"))):
                changed += 1
        value["schema_version"] = max(RUNTIME_SCHEMA_VERSION, int(value.get("schema_version", 1)))
    elif name == "topics" and isinstance(value, dict):
        value["schema_version"] = max(1, int(value.get("schema_version", 1)))
    else:
        if not isinstance(value, dict):
            raise ValueError(f"{name} state must be a JSON object")
    return value, changed


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = CONTROL / "backups" / f"migration-{path.stem}-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect only; this is the default")
    mode.add_argument("--apply", action="store_true", help="Create ignored backups and atomically annotate owned state")
    args = parser.parse_args()
    report: dict[str, Any] = {"schema_version": 1, "ok": True, "mode": "apply" if args.apply else "dry-run", "records": {}}
    try:
        for name, path in RUNTIME_FILES.items():
            if name == "goals":
                entries = []
                if path.is_dir():
                    entries = sorted(item for item in path.glob("*.json") if item.is_file())
                report["records"][name] = {"exists": bool(entries), "count": len(entries), "hashes": [digest(load_json(item)) for item in entries]}
                continue
            value = load_json(path)
            if value is None:
                report["records"][name] = {"exists": False, "count": 0, "schema_version": None, "changed_records": 0}
                continue
            before_hash = digest(value)
            updated, changed = annotate(name, value)
            report["records"][name] = {"exists": True, "count": len(value.get("sessions", value.get("events", value.get("providers", {})))) if isinstance(value, dict) else 0, "schema_version": value.get("schema_version") if isinstance(value, dict) else None, "changed_records": changed, "before_sha256": before_hash, "after_sha256": digest(updated)}
            if args.apply and changed:
                report["records"][name]["backup"] = str(backup(path).relative_to(ROOT))
                save(path, updated)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": type(exc).__name__}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

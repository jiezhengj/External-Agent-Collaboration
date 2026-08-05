#!/usr/bin/env python3
"""Dry-run or annotate legacy Claude runtime records with harness identity."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_state import RUNTIME_SCHEMA_VERSION, decorate_legacy_record
from workspace_context import skill_project_root


PROJECT_ROOT = skill_project_root()
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
RUNTIME_FILES = {
    "sessions": CONTROL_ROOT / "sessions.json",
    "trust": CONTROL_ROOT / "trusted-providers.local.json",
    "health": CONTROL_ROOT / "provider-health.json",
    "capabilities": CONTROL_ROOT / "provider-capabilities.json",
    "metrics": CONTROL_ROOT / "provider-metrics.json",
}


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def annotate(name: str, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    changed = 0
    if name == "sessions":
        items = data.get("sessions", [])
        if not isinstance(items, list):
            raise ValueError("sessions.json must contain sessions array.")
        for record in items:
            if isinstance(record, dict) and decorate_legacy_record(record):
                changed += 1
    elif name in {"trust", "health", "capabilities"}:
        records = data.get("providers", {})
        if not isinstance(records, dict):
            raise ValueError(f"{name} runtime must contain providers object.")
        for provider, record in records.items():
            if isinstance(record, dict) and decorate_legacy_record(record, str(provider)):
                changed += 1
    elif name == "metrics":
        events = data.get("events", [])
        if not isinstance(events, list):
            raise ValueError("provider-metrics.json must contain events array.")
        for record in events:
            if isinstance(record, dict) and decorate_legacy_record(record, str(record.get("model_profile") or record.get("provider") or "unknown")):
                changed += 1
    data["schema_version"] = max(RUNTIME_SCHEMA_VERSION, int(data.get("schema_version", 1)))
    return data, changed


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = CONTROL_ROOT / "backups" / f"{path.stem}-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write annotations after creating local backups.")
    args = parser.parse_args()
    report: dict[str, Any] = {"ok": True, "applied": args.apply, "records": {}}
    try:
        for name, path in RUNTIME_FILES.items():
            if name == "sessions":
                default = {"schema_version": 1, "sessions": []}
            elif name == "metrics":
                default = {"schema_version": 1, "events": []}
            else:
                default = {"schema_version": 1, "providers": {}}
            data = read_json(path, default)
            annotated, changed = annotate(name, data)
            entry: dict[str, Any] = {"path": str(path.relative_to(PROJECT_ROOT)), "changed_records": changed, "exists": path.exists()}
            if args.apply and path.exists() and changed:
                entry["backup"] = str(backup(path).relative_to(PROJECT_ROOT))
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_text(json.dumps(annotated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                temporary.replace(path)
            report["records"][name] = entry
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

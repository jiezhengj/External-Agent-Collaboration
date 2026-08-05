#!/usr/bin/env python3
"""Dependency-free source, schema and privacy quality gate."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_ROOT = ROOT / ".agents" / "skills" / "external-agent-collaboration" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
SECRET_PATTERNS = (re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----"), re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"), re.compile(r"\b[A-Z][A-Z0-9_]*(?:TOKEN|API_KEY|SECRET|PASSWORD)\s*=\s*['\"][^'\"]+['\"]"))


def python_files() -> list[Path]:
    return sorted(path for path in SCRIPT_ROOT.glob("*.py") if "__pycache__" not in path.parts)


def ast_errors() -> list[str]:
    errors: list[str] = []
    for path in python_files():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"{path.name}: {exc}")
    return errors


def source_policy_errors() -> list[str]:
    errors: list[str] = []
    for path in python_files():
        if path.name.startswith("test_"):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if "shell=True" in source and path.name != "quality_gate.py":
            errors.append(f"{path.name}: shell=True is not allowed")
        if "Path(__file__).resolve().parents[4]" in source and path.name not in {"quality_gate.py", "run_regression.py"}:
            errors.append(f"{path.name}: fixed parents[4] project root")
    return errors


def privacy_errors() -> list[str]:
    errors: list[str] = []
    try:
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True, shell=False, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        files = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file()]
    forbidden_parts = (".ai-collaboration/bad-cases/", ".ai-collaboration/outputs/", ".ai-collaboration/logs/", "providers.local.json", "trusted-providers.local.json")
    for name in files:
        if any(part in name.replace("\\", "/") for part in forbidden_parts):
            errors.append(f"versioned runtime/private artifact: {name}")
            continue
        path = ROOT / name
        try:
            data = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            synthetic = any(marker in data for marker in ("test_value", "fixture-token", "/Users/example", "C:/Users/example", "/home/user/project"))
            if pattern.search(data) and not synthetic:
                errors.append(f"possible credential in {name}")
                break
        if (re.search(r"/(?:Users|home)/[A-Za-z0-9._-]+", data) or re.search(r"\b[A-Z]:\\Users\\", data)) and not synthetic:
            errors.append(f"absolute user path in {name}")
    return sorted(set(errors))


def json_errors() -> list[str]:
    errors: list[str] = []
    candidates = list((ROOT / ".agents" / "skills" / "external-agent-collaboration" / "references").glob("*.json")) + list((ROOT / ".ai-collaboration").glob("*.example.json"))
    candidates.append(ROOT / "docs" / "专题" / "2026-08-05-global-skill-production-hardening" / "goal-contract.json")
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"JSON root must be object: {path.relative_to(ROOT)}")
            continue
        if path.name.endswith("schema.json"):
            if not isinstance(value.get("type"), (str, list)) or not isinstance(value.get("required"), list) or not isinstance(value.get("properties"), dict):
                errors.append(f"schema shape is incomplete: {path.relative_to(ROOT)}")
        if path.name == "goal-contract.json":
            try:
                from goal_lifecycle import validate_contract
                validate_contract(value)
            except Exception as exc:
                errors.append(f"invalid production Goal contract {path.relative_to(ROOT)}: {type(exc).__name__}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--privacy", action="store_true")
    args = parser.parse_args()
    errors = ast_errors() + source_policy_errors() + json_errors()
    if args.privacy:
        errors += privacy_errors()
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "checked_python_files": len(python_files()), "privacy": args.privacy}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

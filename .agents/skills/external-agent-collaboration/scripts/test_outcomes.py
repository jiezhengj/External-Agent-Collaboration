#!/usr/bin/env python3
"""Local regression tests for expected-outcome evaluation; no provider call."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    temporary = Path(tempfile.mkdtemp(prefix="outcomes-test-", dir=collaborate.PROJECT_ROOT))
    try:
        rel = temporary.relative_to(collaborate.PROJECT_ROOT)
        text_file = temporary / "result.md"
        text_file.write_text("# done\n", encoding="utf-8")
        json_file = temporary / "result.json"
        json_file.write_text(json.dumps({"status": "ok", "items": [1, 2]}), encoding="utf-8")
        changed = [f"{rel}/result.md", f"{rel}/result.json"]

        outcomes = [
            {"type": "file_exists", "path": f"{rel}/result.md"},
            {"type": "file_contains", "path": f"{rel}/result.md", "text": "done"},
            {"type": "file_equals", "path": f"{rel}/result.md", "text": "# done\n"},
            {"type": "changed_paths", "min": 2, "max": 2},
            {"type": "json_schema", "path": f"{rel}/result.json", "schema": {"type": "object", "required": ["status", "items"], "properties": {"status": {"const": "ok"}, "items": {"type": "array", "minItems": 2, "items": {"type": "integer"}}}, "additionalProperties": False}},
        ]
        results = collaborate.evaluate_outcomes(outcomes, changed, temporary, [])
        check(all(result["passed"] for result in results), f"Expected all outcomes to pass: {results}")

        failures = collaborate.evaluate_outcomes([{"type": "file_exists", "path": f"{rel}/missing.md"}], changed, temporary, [])
        check(failures[0]["passed"] is False, "Missing file must fail.")

        unapproved = collaborate.evaluate_outcomes([{"type": "command_succeeds", "command": "true"}], changed, temporary, [])
        check(unapproved[0]["passed"] is False and "error" in unapproved[0], "Unapproved validation command must fail.")

        approved = collaborate.evaluate_outcomes([{"type": "command_succeeds", "command": "true"}], changed, temporary, ["true"])
        check(approved[0]["passed"] is True, f"Approved validation command must pass: {approved}")

        checkpoint = Path(tempfile.mkdtemp(prefix="outcomes-checkpoint-", dir=collaborate.PROJECT_ROOT))
        try:
            before = {f"{rel}/result.md": collaborate.hashlib.sha256(text_file.read_bytes()).hexdigest()}
            backup = checkpoint / rel / "result.md"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(text_file, backup)
            text_file.write_text("partial external output\n", encoding="utf-8")
            after = {f"{rel}/result.md": collaborate.hashlib.sha256(text_file.read_bytes()).hexdigest()}
            collaborate.restore_changed(before, after, checkpoint)
            check(text_file.read_text(encoding="utf-8") == "# done\n", "Outcome failure rollback must restore original content.")
        finally:
            shutil.rmtree(checkpoint)

        symlink = temporary / "outside-link"
        symlink.symlink_to(text_file)
        symlink_manifest = collaborate.manifest(temporary)
        check("outside-link" in symlink_manifest and symlink_manifest["outside-link"].startswith("symlink:"), "Symlinks must appear in a manifest.")
        binary_file = temporary / "binary.dat"
        binary_file.write_bytes(b"\0binary")
        check(f"{rel}/binary.dat" in collaborate.binary_changed_paths([f"{rel}/binary.dat"]), "Binary modifications must be detectable.")
        print("expected-outcome tests passed")
    finally:
        shutil.rmtree(temporary)


if __name__ == "__main__":
    main()

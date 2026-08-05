#!/usr/bin/env python3
"""Parse/contract failure must roll back an already-mutated execute workspace."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate_transaction", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="execute-transaction-") as directory:
        root = Path(directory)
        (root / "docs").mkdir()
        (root / "docs" / "target.md").write_text("before\n", encoding="utf-8")
        (root / "handoff.md").write_text("bounded execute", encoding="utf-8")
        (root / "outcomes.json").write_text(json.dumps({"outcomes": [{"type": "file_exists", "path": "docs/target.md"}]}), encoding="utf-8")
        config = root / "config"; config.mkdir()
        original = {name: getattr(collaborate, name) for name in ("PROJECT_ROOT", "CONTROL_ROOT", "TRUST_FILE", "SESSIONS_FILE", "METRICS_FILE", "HEALTH_FILE", "TOPICS_FILE", "GOALS_DIR")}
        collaborate.PROJECT_ROOT = root
        collaborate.CONTROL_ROOT = root / ".ai-collaboration"
        collaborate.TRUST_FILE = collaborate.CONTROL_ROOT / "trusted.json"
        collaborate.SESSIONS_FILE = collaborate.CONTROL_ROOT / "sessions.json"
        collaborate.METRICS_FILE = collaborate.CONTROL_ROOT / "metrics.json"
        collaborate.HEALTH_FILE = collaborate.CONTROL_ROOT / "health.json"
        collaborate.TOPICS_FILE = collaborate.CONTROL_ROOT / "topics.json"
        collaborate.GOALS_DIR = collaborate.CONTROL_ROOT / "goals"
        old_argv = sys.argv
        sys.argv = ["collaborate.py", "--action", "execute", "--provider", "provider_a", "--topic", "tx", "--handoff", str(root / "handoff.md"), "--working-directory", str(root), "--allow-path", "docs", "--expected-outcomes", str(root / "outcomes.json")]
        def mutate(*_args, **_kwargs):
            (root / "docs" / "target.md").write_text("mutated\n", encoding="utf-8")
            return 0, "not-json", ""
        try:
            with patch.object(collaborate, "profiles", return_value={"provider_a": {"config_dir": str(config)}}), patch.object(collaborate, "trust_registry", return_value={"providers": {}}), patch.object(collaborate, "trusted_profiles", side_effect=lambda configured, _trust: configured), patch.object(collaborate, "profile_problem", return_value=None), patch.object(collaborate, "invoke", side_effect=mutate), patch.object(collaborate, "require_execute_guard", return_value=None):
                assert collaborate.main() == 2
        finally:
            sys.argv = old_argv
            for name, value in original.items():
                setattr(collaborate, name, value)
        assert (root / "docs" / "target.md").read_text(encoding="utf-8") == "before\n"
    print("execute-transaction tests passed")


if __name__ == "__main__":
    main()

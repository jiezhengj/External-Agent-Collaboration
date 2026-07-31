#!/usr/bin/env python3
"""Regression tests for local provider availability state and failure classes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("provider_health.py")
SPEC = importlib.util.spec_from_file_location("provider_health", SCRIPT)
assert SPEC and SPEC.loader
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)

COLLABORATE_SCRIPT = Path(__file__).with_name("collaborate.py")
COLLABORATE_SPEC = importlib.util.spec_from_file_location("collaborate", COLLABORATE_SCRIPT)
assert COLLABORATE_SPEC and COLLABORATE_SPEC.loader
collaborate = importlib.util.module_from_spec(COLLABORATE_SPEC)
COLLABORATE_SPEC.loader.exec_module(collaborate)


def main() -> None:
    data = health.default_health()
    at = datetime.now(timezone.utc)
    record = health.record_failure(data, "deepseek", "billing", at)
    assert record["failure_kind"] == "billing" and not health.is_available(data, "deepseek", at)
    assert health.is_available(data, "deepseek", at + timedelta(hours=24, seconds=1))
    health.record_success(data, "deepseek", at)
    assert health.status(data, "deepseek")["state"] == "healthy"
    health.record_failure(data, "mimo", "transport", at)
    assert not health.is_available(data, "mimo", at + timedelta(minutes=4))
    assert health.is_available(data, "mimo", at + timedelta(minutes=5, seconds=1))
    retry = health.record_failure(data, "mimo", "transport", at + timedelta(minutes=6))
    assert retry["failure_count"] == 1
    assert health.classify_failure(1, "HTTP 401 invalid API key") == "authentication"
    assert health.classify_failure(1, "validation failed for expected outcome") is None
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        available = {
            "deepseek": {"config_dir": str(root)},
            "mimo": {"config_dir": str(root)},
        }
        workdir = root / "project"
        workdir.mkdir()
        sessions = [{
            "status": "active", "topic": "topic", "working_directory": str(workdir.resolve()),
            "workspace_identity": collaborate.workspace_identity(workdir), "host_platform": collaborate.host_platform(),
            "provider": "deepseek", "key": "old",
        }]
        health.record_success(data, "mimo", at)
        health.record_failure(data, "deepseek", "billing", at)
        provider, session, auto, route = collaborate.select_provider("auto", "topic", workdir, sessions, available, {"round_robin_cursor": {}, "events": []}, data, "code", "execute")
        assert provider == "mimo" and session is None and auto and route["basis"] == "active_session_availability_failover"
        selected, _, auto, route = collaborate.select_provider("auto", "fresh", workdir, [], available, {"round_robin_cursor": {}, "events": []}, data, "research", "analyze")
        assert selected == "mimo" and auto and route["basis"] == "starter_policy_text_reasoning_rotation"
        launcher = root / "fake-claude"
        argv_path = root / "argv.json"
        helper = root / "fake-claude.py"
        helper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            "print('{}')\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            launcher = root / "fake-claude.cmd"
            launcher.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake-claude.py" %*\r\n', encoding="utf-8")
        else:
            launcher.write_text(helper.read_text(encoding="utf-8"), encoding="utf-8")
            launcher.chmod(0o700)
        code, _stdout, _stderr = collaborate.invoke(
            {"launcher": str(launcher), "config_dir": str(root), "environment": {"ARGS_FILE": str(argv_path), "ANTHROPIC_MODEL": "provider-default"}},
            "consult", "test", root, None, True, False, [], 10,
        )
        argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert code == 0 and "--model" not in argv and "--json-schema" in argv
    print("provider-health tests passed")


if __name__ == "__main__":
    main()

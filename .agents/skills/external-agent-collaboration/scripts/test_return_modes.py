#!/usr/bin/env python3
"""Regression tests for bounded external-result returns and one-page topic state."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def record(result: dict) -> dict:
    return {
        "run_id": "run-1", "status": "completed", "provider": "provider_a", "action": "consult",
        "task_type": "planning", "mode": "analyze", "routing": {"basis": "test"}, "topic": "return-mode",
        "result": result, "changed_files": ["docs/a.md"], "restored_violations": [], "outcome_results": [{"type": "file_exists", "path": "docs/a.md", "passed": True}],
    }


def main() -> None:
    valid = {
        "summary": "Completed a bounded review.", "changed_files": ["docs/a.md"], "commands_run": [],
        "validation_results": ["No command required."], "risks": [], "uncertainty": "None.",
    }
    full = record({"result": json.dumps(valid), "session_id": "session-1", "total_cost_usd": 0.01})
    response, errors = collaborate.parse_response_contract(full["result"])
    assert errors == [] and response == valid

    compact = collaborate.return_payload("compact", full, ".ai-collaboration/outputs/run-1.json", response, errors)
    assert "result" not in compact and compact["result_contract_failed"] is False
    assert len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) <= collaborate.COMPACT_RETURN_BYTES

    structured = collaborate.return_payload("structured", full, ".ai-collaboration/outputs/run-1.json", response, errors)
    assert structured["response"] == valid and "result" not in structured

    file_only = collaborate.return_payload("file_only", full, ".ai-collaboration/outputs/run-1.json", response, errors)
    assert "result" not in file_only and "result_summary" not in file_only and "output_sha256" in file_only

    huge = record({"result": "汉" * 10000})
    invalid_response, invalid_errors = collaborate.parse_response_contract(huge["result"])
    assert invalid_response is None and invalid_errors
    huge_compact = collaborate.return_payload("compact", huge, ".ai-collaboration/outputs/run-2.json", invalid_response, invalid_errors)
    assert huge_compact["result_contract_failed"] is True
    assert len(json.dumps(huge_compact, ensure_ascii=False).encode("utf-8")) <= collaborate.COMPACT_RETURN_BYTES
    token_like = "sk-" + "abcdefghijklmnopqrstuvwxyz012345"
    secret = record({"result": "unexpected token " + token_like})
    secret_payload = collaborate.return_payload("compact", secret, ".ai-collaboration/outputs/run-3.json", None, ["not JSON"])
    assert token_like not in json.dumps(secret_payload, ensure_ascii=False)
    assert "[REDACTED_SECRET]" in secret_payload["result_summary"]

    original_root, original_control = collaborate.PROJECT_ROOT, collaborate.CONTROL_ROOT
    with tempfile.TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        collaborate.PROJECT_ROOT = temporary_root
        collaborate.CONTROL_ROOT = temporary_root / ".ai-collaboration"
        try:
            state_rel = collaborate.write_topic_state("long topic / 2026", temporary_root, "Goal " + "x" * 2000, "Stop " + "y" * 2000, "completed", "consult", ["docs/a.md"], ".ai-collaboration/outputs/run-1.json")
            state = (temporary_root / state_rel).read_text(encoding="utf-8")
            assert "Handoff:" not in state and len(state) <= collaborate.TOPIC_STATE_MAX_CHARS + 1
            assert "Evidence:" in state and "Stop rule:" in state
        finally:
            collaborate.PROJECT_ROOT, collaborate.CONTROL_ROOT = original_root, original_control
    print("return-mode tests passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Portable fake-launcher tests for the read-only Antigravity adapter."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from antigravity_adapter import AntigravityAdapter, AntigravityInvocation


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}
UNICODE_SUMMARY = "\u7f16\u7801\u56de\u5f52"


def main() -> None:
    adapter = AntigravityAdapter()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        argv_path = root / "argv.json"
        helper = root / "fake-agy.py"
        helper.write_text(
            "import json, os, sys\nsys.stdout.reconfigure(encoding='utf-8')\nfrom pathlib import Path\n"
            "Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            "print(json.dumps({'conversation_id': 'agy-conversation', 'status': 'SUCCESS', 'response': '{\\\"summary\\\":\\\"\\u7f16\\u7801\\u56de\\u5f52\\\"}', 'structured_output': {'summary': '\\u7f16\\u7801\\u56de\\u5f52'}}, ensure_ascii=False))\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            launcher = root / "fake-agy.cmd"
            launcher.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake-agy.py" %*\r\n', encoding="utf-8")
        else:
            launcher = root / "fake-agy"
            launcher.write_text(f"#!{sys.executable}\n" + helper.read_text(encoding="utf-8"), encoding="utf-8")
            launcher.chmod(0o700)
        request = AntigravityInvocation(
            launcher=str(launcher), prompt="review", workdir=root, environment={**os.environ, "ARGS_FILE": str(argv_path)},
            timeout=10, response_schema=SCHEMA, profile={"mode": "plan"}, conversation_id="previous-conversation",
        )
        code, stdout, stderr = adapter.invoke(request)
        assert code == 0 and not stderr and UNICODE_SUMMARY in stdout and "\ufffd" not in stdout
        argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert "--dangerously-skip-permissions" not in argv and argv[argv.index("--mode") + 1] == "plan"
        assert argv[argv.index("--conversation") + 1] == "previous-conversation"
        assert json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
        result = adapter.parse_outer_result(stdout)
        assert adapter.structured_output(result) == {"summary": UNICODE_SUMMARY}
        assert adapter.resume_id({"external_session_id": "agy-conversation"}) == "agy-conversation"
        assert adapter.permission_state(result) == "allowed"
    assert adapter.permission_state({"status": "SUCCESS", "error": "permission denied for run_command"}) == "blocked_by_permission"
    assert adapter.permission_state({"status": "ERROR", "error": "unknown model"}) == "failed"
    assert adapter.classify_error(1, "authentication required") == "authentication"
    assert adapter.classify_error(1, "invalid model selection") == "configuration"
    stream = "\n".join((
        json.dumps({"event": "init", "init": {"permission_mode": "request-review"}}),
        json.dumps({"event": "step_update", "step_update": {"text_delta": "do-not-store-this-model-text", "state": "ACTIVE"}}),
        json.dumps({"event": "result", "result": {"conversation_id": "stream-conversation", "status": "SUCCESS", "structured_output": {"summary": "ok"}}}),
    ))
    streamed, diagnostics = adapter.parse_stream_result(stream)
    assert streamed["conversation_id"] == "stream-conversation" and diagnostics["startup_observed"]
    assert diagnostics["terminal_status"] == "SUCCESS" and "do-not-store-this-model-text" not in json.dumps(diagnostics)
    execute_argv = adapter.command(AntigravityInvocation("agy", "review", Path.cwd(), {}, 10, SCHEMA, {"mode": "accept-edits"}))
    assert execute_argv[execute_argv.index("--mode") + 1] == "accept-edits"
    print("antigravity-adapter tests passed")


if __name__ == "__main__":
    main()

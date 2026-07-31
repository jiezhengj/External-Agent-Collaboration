#!/usr/bin/env python3
"""Portable fake-launcher tests for Claude Code native schema output."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


VALID = {
    "summary": "Completed.", "changed_files": [], "commands_run": [],
    "validation_results": [], "risks": [], "uncertainty": "None.",
}


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        argv_path = root / "argv.json"
        helper = root / "fake-claude.py"
        helper.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            "print(json.dumps({'structured_output': {'summary': 'Completed.', 'changed_files': [], 'commands_run': [], 'validation_results': [], 'risks': [], 'uncertainty': 'None.'}}))\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            launcher = root / "fake-claude.cmd"
            launcher.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake-claude.py" %*\r\n', encoding="utf-8")
        else:
            launcher = root / "fake-claude"
            launcher.write_text(f"#!{sys.executable}\n" + helper.read_text(encoding="utf-8"), encoding="utf-8")
            launcher.chmod(0o700)
        code, stdout, stderr = collaborate.invoke(
            {"launcher": str(launcher), "config_dir": str(root), "environment": {"ARGS_FILE": str(argv_path)}},
            "consult", "test", root, {"session_id": "saved-session"}, False, True, [], 10,
        )
        assert code == 0 and not stderr
        argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert "--model" not in argv and "--json-schema" in argv
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        assert schema == collaborate.RESPONSE_CONTRACT_SCHEMA
        assert argv[argv.index("--resume") + 1] == "saved-session" and "--fork-session" in argv
        outer = collaborate.parse_result(stdout)
        response, errors = collaborate.parse_response_contract(outer)
        assert response == VALID and errors == []
        code, _stdout, stderr = collaborate.invoke(
            {"launcher": str(launcher), "config_dir": str(root), "environment": {"ARGS_FILE": str(argv_path)}},
            "consult", "test", root, None, True, False, [], 10, True,
        )
        assert code == 0 and not stderr
        stream_argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert stream_argv[stream_argv.index("--output-format") + 1] == "stream-json" and "--verbose" in stream_argv

    stream = "\n".join((
        json.dumps({"type": "system", "subtype": "init", "mcp_servers": ["safe-name"]}),
        json.dumps({"type": "rate_limit_event", "message": "retry scheduled"}),
        json.dumps({"type": "assistant", "content": [{"text": "do-not-store-this-model-text"}]}),
        json.dumps({"type": "result", "session_id": "stream-session", "structured_output": VALID}),
    ))
    outer, diagnostics = collaborate.CLAUDE_ADAPTER.parse_stream_result(stream)
    assert outer["session_id"] == "stream-session" and diagnostics["startup_observed"]
    assert diagnostics["api_retry_count"] == 1 and diagnostics["terminal_observed"]
    assert "do-not-store-this-model-text" not in json.dumps(diagnostics)

    blocked_command = collaborate.CLAUDE_ADAPTER.command(
        collaborate.ClaudeInvocation(
            launcher="claude", prompt="test", workdir=Path.cwd(), config_dir="/tmp", environment={},
            tools=["Bash"], allowed_tools=[], disallowed_tools=["Bash"], timeout=10,
        )
    )
    assert blocked_command[blocked_command.index("--disallowed-tools") + 1] == "Bash"

    fallback, errors = collaborate.parse_response_contract({"result": json.dumps(VALID)})
    assert fallback == VALID and errors == []
    conflict, errors = collaborate.parse_response_contract({"structured_output": {"summary": "bad"}, "result": json.dumps(VALID)})
    assert conflict is None and errors and "missing required property" in errors[0]
    malformed, errors = collaborate.parse_response_contract({"structured_output": "not-json", "result": json.dumps(VALID)})
    assert malformed is None and errors and "structured_output is not valid JSON" in errors[0]
    print("claude-code-adapter tests passed")


if __name__ == "__main__":
    main()

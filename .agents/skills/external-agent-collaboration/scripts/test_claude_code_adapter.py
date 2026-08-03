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
UNICODE_SUMMARY = "\u7f16\u7801\u56de\u5f52"
UTF8_VALID = {**VALID, "summary": UNICODE_SUMMARY}


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        argv_path = root / "argv.json"
        helper = root / "fake-claude.py"
        helper.write_text(
            "import json, os, sys\nsys.stdout.reconfigure(encoding='utf-8')\nfrom pathlib import Path\n"
            "Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            "print(json.dumps({'structured_output': {'summary': '\\u7f16\\u7801\\u56de\\u5f52', 'changed_files': [], 'commands_run': [], 'validation_results': [], 'risks': [], 'uncertainty': 'None.'}}, ensure_ascii=False))\n",
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
            {"launcher": str(launcher), "config_dir": str(root), "environment": {"ARGS_FILE": str(argv_path), "PYTHONHASHSEED": "0"}},
            "consult", "test", root, {"session_id": "saved-session"}, False, True, [], 10,
        )
        assert code == 0 and not stderr and UNICODE_SUMMARY in stdout and "\ufffd" not in stdout
        argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert "--model" not in argv and "--json-schema" in argv
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        assert schema == collaborate.RESPONSE_CONTRACT_SCHEMA
        assert argv[argv.index("--resume") + 1] == "saved-session" and "--fork-session" in argv
        outer = collaborate.parse_result(stdout)
        response, errors = collaborate.parse_response_contract(outer)
        assert response == UTF8_VALID and errors == []
        code, _stdout, stderr = collaborate.invoke(
            {"launcher": str(launcher), "config_dir": str(root), "environment": {"ARGS_FILE": str(argv_path), "PYTHONHASHSEED": "0"}},
            "consult", "test", root, None, True, False, [], 10, True,
        )
        assert code == 0 and not stderr
        stream_argv = json.loads(argv_path.read_text(encoding="utf-8"))
        assert stream_argv[stream_argv.index("--output-format") + 1] == "stream-json" and "--verbose" in stream_argv

        hanging_source = root / "hanging-claude.py"
        hanging_source.write_text(
            "import json, os, sys, time\n"
            "payload = {'structured_output': {'summary': 'ok', 'changed_files': [], 'commands_run': [], 'validation_results': [], 'risks': [], 'uncertainty': 'None.'}}\n"
            "format_name = sys.argv[sys.argv.index('--output-format') + 1]\n"
            "if format_name == 'stream-json':\n"
            "    payload = {'type': 'result', 'subtype': os.environ.get('HANG_SUBTYPE', 'success'), 'is_error': os.environ.get('HANG_IS_ERROR') == '1', **payload}\n"
            "if os.environ.get('HANG_ERROR') == '1':\n"
            "    payload = {'is_error': True, 'error': {'message': 'Insufficient account balance'}}\n"
            "print(json.dumps(payload), flush=True)\n"
            "if os.environ.get('HANG_EXIT') == '1':\n"
            "    sys.exit(1)\n"
            "time.sleep(5)\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            hanging_launcher = root / "hanging-claude.cmd"
            hanging_launcher.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0hanging-claude.py" %*\r\n', encoding="utf-8")
        else:
            hanging_launcher = root / "hanging-claude"
            hanging_launcher.write_text(f"#!{sys.executable}\n" + hanging_source.read_text(encoding="utf-8"), encoding="utf-8")
            hanging_launcher.chmod(0o700)

        def invoke_hanging(*, stream: bool, subtype: str = "success", is_error: bool = False, error: bool = False, exit_code: bool = False) -> tuple[int, str, str]:
            return collaborate.CLAUDE_ADAPTER.invoke(collaborate.ClaudeInvocation(
                launcher=str(hanging_launcher), prompt="test", workdir=root, config_dir=str(root),
                environment={
                    "HANG_SUBTYPE": subtype, "HANG_IS_ERROR": "1" if is_error else "0",
                    "HANG_ERROR": "1" if error else "0", "HANG_EXIT": "1" if exit_code else "0",
                    "PYTHONHASHSEED": "0",
                },
                tools=[], allowed_tools=[], disallowed_tools=[], timeout=1, stream_diagnostics=stream,
            ))

        code, stdout, stderr = invoke_hanging(stream=False)
        assert code == 0 and stderr == "" and "structured_output" in stdout
        code, stdout, stderr = invoke_hanging(stream=True)
        assert code == 0 and stderr == "" and '"type": "result"' in stdout
        code, _stdout, stderr = invoke_hanging(stream=True, subtype="error_during_execution", is_error=True)
        assert code == 1 and "terminal error" in stderr and "Timed out" not in stderr
        code, _stdout, stderr = invoke_hanging(stream=False, error=True, exit_code=True)
        assert code == 1 and "category=billing" in stderr and "balance" not in stderr

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

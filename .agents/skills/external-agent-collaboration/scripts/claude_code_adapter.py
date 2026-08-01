"""Claude Code headless adapter with native structured-output support."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from harness_state import CLAUDE_CODE, external_session_id
from stream_diagnostics import StreamDiagnosticsError, parse_ndjson


class ClaudeCodeAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaudeInvocation:
    launcher: str
    prompt: str
    workdir: Path
    config_dir: str
    environment: dict[str, str]
    tools: list[str]
    allowed_tools: list[str]
    disallowed_tools: list[str]
    timeout: int
    session_id: str | None = None
    ephemeral: bool = False
    fork_session: bool = False
    response_schema: dict[str, Any] | None = None
    stream_diagnostics: bool = False


class ClaudeCodeAdapter:
    """Keep Claude CLI argv, outer JSON, and structured result semantics together."""

    name = CLAUDE_CODE

    @staticmethod
    def doctor(profile: dict[str, Any]) -> list[str]:
        return [] if isinstance(profile.get("config_dir"), str) else ["Claude profile has no config_dir."]

    @staticmethod
    def resume_id(session: dict[str, Any]) -> str:
        value = external_session_id(session)
        if not value:
            raise ClaudeCodeAdapterError("Claude session has no external session ID.")
        return value

    @staticmethod
    def capabilities(action: str, commands: list[str]) -> list[str]:
        tools = ["Read", "Glob", "Grep"]
        if action == "execute":
            tools.extend(["Edit", "Write"])
            if commands:
                tools.append("Bash")
        return tools

    @staticmethod
    def classify_error(_exit_code: int, _stderr: str) -> str | None:
        # Provider-specific availability classification remains in provider_health.
        return None

    @staticmethod
    def permission_state(result: dict[str, Any]) -> str:
        return "blocked_by_permission" if result.get("permission_denials") else "allowed"

    def command(self, request: ClaudeInvocation) -> list[str]:
        output_format = "stream-json" if request.stream_diagnostics else "json"
        command = [request.launcher, "-p", request.prompt, "--output-format", output_format, "--permission-mode", "dontAsk"]
        if request.stream_diagnostics:
            command.append("--verbose")
        if request.response_schema is not None:
            command.extend(["--json-schema", json.dumps(request.response_schema, ensure_ascii=False, separators=(",", ":"))])
        command.extend(["--tools", ",".join(request.tools), "--allowed-tools", ",".join(request.allowed_tools)])
        if request.disallowed_tools:
            command.extend(["--disallowed-tools", ",".join(request.disallowed_tools)])
        if request.session_id and not request.ephemeral:
            command.extend(["--resume", request.session_id])
            if request.fork_session:
                command.append("--fork-session")
        if request.ephemeral:
            command.append("--no-session-persistence")
        return command

    def invoke(self, request: ClaudeInvocation) -> tuple[int, str, str]:
        environment = request.environment.copy()
        environment["CLAUDE_CONFIG_DIR"] = request.config_dir
        try:
            completed = subprocess.run(
                self.command(request), cwd=request.workdir, env=environment,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=request.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", f"Timed out after {request.timeout}s"
        return completed.returncode, completed.stdout, completed.stderr

    @staticmethod
    def parse_outer_result(stdout: str) -> dict[str, Any]:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeAdapterError(f"Claude CLI did not return valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ClaudeCodeAdapterError("Claude CLI JSON result must be an object.")
        return data

    @staticmethod
    def parse_stream_result(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            return parse_ndjson(stdout, stream_kind="claude")
        except StreamDiagnosticsError as exc:
            raise ClaudeCodeAdapterError(str(exc)) from exc

    @staticmethod
    def structured_output(result: dict[str, Any]) -> tuple[Any | None, str | None]:
        """Return structured output and its source; absence permits legacy fallback."""
        if "structured_output" not in result:
            return None, None
        value = result.get("structured_output")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ClaudeCodeAdapterError(f"structured_output is not valid JSON: {exc.msg}") from exc
        return value, "structured_output"

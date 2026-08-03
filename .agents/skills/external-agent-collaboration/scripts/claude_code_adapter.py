"""Claude Code headless adapter with native structured-output support."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from harness_state import CLAUDE_CODE, external_session_id
from buffered_http_proxy import BufferedProviderProxy
from process_support import run_bounded
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
    response_transport: str = "direct"


class ClaudeCodeAdapter:
    """Keep Claude CLI argv, outer JSON, and structured result semantics together."""

    name = CLAUDE_CODE
    _ERROR_SUBTYPES = {"error", "failed", "failure"}
    _ERROR_STATUSES = {"error", "failed", "failure"}
    _TERMINAL_FAILURE_MARKERS = (
        ("billing", ("insufficient balance", "insufficient account balance", "insufficient quota", "payment required", "billing", "http 402")),
        ("authentication", ("invalid api key", "authentication", "unauthorized", "http 401", "http 403")),
        ("endpoint", ("base url", "endpoint", "certificate verify", "ssl", "dns", "name or service not known")),
        ("rate_limit", ("rate limit", "too many requests", "http 429")),
        ("server", ("http 500", "http 502", "http 503", "http 504", "internal server error", "service unavailable")),
        ("transport", ("timed out", "timeout", "connection reset", "connection refused", "network is unreachable")),
    )

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
        relay: BufferedProviderProxy | None = None
        if request.response_transport == "buffered_sse":
            upstream = environment.get("ANTHROPIC_BASE_URL")
            relay = BufferedProviderProxy(upstream or "")
            environment["ANTHROPIC_BASE_URL"] = relay.start()
        elif request.response_transport != "direct":
            raise ClaudeCodeAdapterError(f"Unsupported Claude response transport: {request.response_transport}")
        try:
            completed = run_bounded(
                self.command(request), cwd=request.workdir, env=environment, timeout=request.timeout,
            )
        finally:
            if relay is not None:
                relay.close()
        if completed.timed_out:
            terminal = self._terminal_from_output(completed.stdout, request.stream_diagnostics)
            if terminal is not None:
                if self._terminal_is_error(terminal):
                    return 1, completed.stdout, self._terminal_error(terminal)
                return 0, completed.stdout, completed.stderr
            return 124, completed.stdout, f"Timed out after {request.timeout}s"
        terminal = self._terminal_from_output(completed.stdout, request.stream_diagnostics)
        if terminal is not None and self._terminal_is_error(terminal):
            return completed.returncode or 1, completed.stdout, self._terminal_error(terminal)
        return completed.returncode, completed.stdout, completed.stderr

    @classmethod
    def _terminal_from_output(cls, stdout: str, stream_diagnostics: bool) -> dict[str, Any] | None:
        """Recover a complete CLI result when cleanup follows output completion.

        Some Claude launchers keep a child process alive after writing the final
        JSON/NDJSON event.  A bounded cleanup timeout must not turn an already
        emitted result into a transport failure.  Invalid or partial output
        deliberately returns ``None`` so the caller retains the real timeout.
        """
        try:
            if stream_diagnostics:
                return parse_ndjson(stdout, stream_kind="claude")[0]
            return cls.parse_outer_result(stdout)
        except (ClaudeCodeAdapterError, StreamDiagnosticsError):
            return None

    @classmethod
    def _terminal_is_error(cls, terminal: dict[str, Any]) -> bool:
        if terminal.get("is_error") is True:
            return True
        error = terminal.get("error")
        errors = terminal.get("errors")
        if (isinstance(error, dict) and bool(error)) or (isinstance(error, str) and bool(error.strip())) or (isinstance(errors, list) and bool(errors)):
            return True
        for key, markers in (("subtype", cls._ERROR_SUBTYPES), ("status", cls._ERROR_STATUSES)):
            value = terminal.get(key)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in markers or any(normalized.startswith(f"{marker}_") for marker in markers):
                    return True
        return False

    @classmethod
    def _terminal_error(cls, terminal: dict[str, Any]) -> str:
        """Describe only bounded terminal metadata; never echo model content."""
        fields: list[str] = []
        for key in ("subtype", "status"):
            value = terminal.get(key)
            if isinstance(value, str) and value:
                fields.append(f"{key}={value[:80]}")
        if terminal.get("is_error") is True:
            fields.append("is_error=true")
        category = cls._terminal_failure_category(terminal)
        if category:
            fields.append(f"category={category}")
        detail = ", ".join(fields) or "terminal_error"
        return f"Claude CLI returned terminal error ({detail})"

    @classmethod
    def _terminal_failure_category(cls, terminal: dict[str, Any]) -> str | None:
        """Classify terminal metadata transiently without retaining its text."""
        try:
            text = json.dumps(terminal, ensure_ascii=False, separators=(",", ":")).lower()
        except (TypeError, ValueError):
            return None
        for category, markers in cls._TERMINAL_FAILURE_MARKERS:
            if any(marker in text for marker in markers):
                return category
        return None

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

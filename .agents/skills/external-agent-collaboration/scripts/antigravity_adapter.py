"""Read-only Antigravity headless adapter; no automatic runner integration yet."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from harness_state import external_session_id
from stream_diagnostics import StreamDiagnosticsError, parse_ndjson


class AntigravityAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AntigravityInvocation:
    launcher: str
    prompt: str
    workdir: Path
    environment: dict[str, str]
    timeout: int
    response_schema: dict[str, Any]
    profile: dict[str, Any]
    conversation_id: str | None = None


class AntigravityAdapter:
    """Owns `agy` conversation, terminal-status, and soft-permission semantics."""

    name = "antigravity"
    READ_ONLY_ACTIONS = {"consult", "critique"}
    TERMINAL_SUCCESS = "SUCCESS"

    @staticmethod
    def doctor(profile: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        if not isinstance(profile.get("launcher", "agy"), str) or not str(profile.get("launcher", "agy")):
            problems.append("Antigravity profile has no launcher.")
        if profile.get("mode", "plan") != "plan":
            problems.append("Read-only Antigravity adapter requires fixed mode=plan.")
        return problems

    def command(self, request: AntigravityInvocation) -> list[str]:
        problems = self.doctor(request.profile)
        if problems:
            raise AntigravityAdapterError("; ".join(problems))
        command = [request.launcher, "-p", request.prompt, "--output-format", "json", "--json-schema", json.dumps(request.response_schema, ensure_ascii=False, separators=(",", ":")), "--mode", "plan"]
        for field, flag in (("model", "--model"), ("effort", "--effort"), ("agent", "--agent")):
            value = request.profile.get(field)
            if isinstance(value, str) and value:
                command.extend([flag, value])
        if request.conversation_id:
            command.extend(["--conversation", request.conversation_id])
        if request.timeout > 0:
            command.extend(["--print-timeout", f"{request.timeout}s"])
        return command

    def invoke(self, request: AntigravityInvocation) -> tuple[int, str, str]:
        try:
            completed = subprocess.run(self.command(request), cwd=request.workdir, env=request.environment, capture_output=True, text=True, timeout=request.timeout)
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", f"Timed out after {request.timeout}s"
        return completed.returncode, completed.stdout, completed.stderr

    @staticmethod
    def parse_outer_result(stdout: str) -> dict[str, Any]:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AntigravityAdapterError(f"Antigravity CLI did not return valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AntigravityAdapterError("Antigravity CLI JSON result must be an object.")
        return data

    @staticmethod
    def parse_stream_result(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            return parse_ndjson(stdout, stream_kind="antigravity")
        except StreamDiagnosticsError as exc:
            raise AntigravityAdapterError(str(exc)) from exc

    @staticmethod
    def resume_id(session: dict[str, Any]) -> str:
        value = external_session_id(session)
        if not value:
            raise AntigravityAdapterError("Antigravity session has no conversation ID.")
        return value

    @staticmethod
    def capabilities(_action: str, _commands: list[str]) -> list[str]:
        return ["read_only"]

    @staticmethod
    def classify_error(exit_code: int, stderr: str) -> str | None:
        text = stderr.lower()
        if any(marker in text for marker in ("authentication required", "not authenticated", "not logged in", "login required")):
            return "authentication"
        if any(marker in text for marker in ("unknown model", "invalid model", "json schema", "invalid flag", "invalid mode", "settings")):
            return "configuration"
        if "permission" in text or "approval" in text:
            return "permission"
        if exit_code == 124 or "timeout" in text:
            return "transport"
        return None

    @staticmethod
    def permission_state(result: dict[str, Any]) -> str:
        status = str(result.get("status", "")).upper()
        detail = " ".join(str(result.get(key, "")) for key in ("error", "response")).lower()
        if any(marker in detail for marker in ("permission", "approval", "soft-denied", "soft denied")):
            return "blocked_by_permission"
        return "allowed" if status == "SUCCESS" else "failed"

    @classmethod
    def structured_output(cls, result: dict[str, Any]) -> dict[str, Any]:
        if str(result.get("status", "")).upper() != cls.TERMINAL_SUCCESS:
            raise AntigravityAdapterError(f"Antigravity terminal status is {result.get('status', 'missing')}.")
        value = result.get("structured_output")
        if not isinstance(value, dict):
            raise AntigravityAdapterError("Antigravity result has no object structured_output.")
        return value

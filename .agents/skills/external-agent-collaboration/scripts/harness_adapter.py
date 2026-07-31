"""Small, local contract shared by independent headless CLI harnesses."""

from __future__ import annotations

from typing import Any, Protocol


class HarnessAdapter(Protocol):
    """A harness owns its CLI semantics; it never shares another harness's state."""

    name: str

    def doctor(self, profile: dict[str, Any]) -> list[str]: ...

    def invoke(self, request: Any) -> tuple[int, str, str]: ...

    def parse_outer_result(self, stdout: str) -> dict[str, Any]: ...

    def resume_id(self, session: dict[str, Any]) -> str: ...

    def capabilities(self, action: str, commands: list[str]) -> list[str]: ...

    def classify_error(self, exit_code: int, stderr: str) -> str | None: ...

    def permission_state(self, result: dict[str, Any]) -> str: ...

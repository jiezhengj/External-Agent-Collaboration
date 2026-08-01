"""Deterministic harness-role selection; never mixes Antigravity with provider routing."""

from __future__ import annotations

from typing import Any


ANTIGRAVITY = "antigravity"
CLAUDE_CODE = "claude_code"
INDEPENDENT_REVIEW_MARKERS = (
    "independent review", "second opinion", "counterargument", "risk review",
    "独立评审", "第二方案", "第二意见", "反方", "反证", "风险审查", "风险清单",
)


def choose_harness(
    request: str,
    action: str,
    sensitive: bool,
    matching_sessions: list[dict[str, Any]],
    antigravity_ready: bool,
    requested_harness: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Select role only; provider routing remains inside the Claude Code pool."""
    if requested_harness:
        if requested_harness == ANTIGRAVITY and (sensitive or action not in {"consult", "critique"}):
            return CLAUDE_CODE, {"basis": "requested_antigravity_ineligible"}
        return requested_harness, {"basis": "user_specified_harness"}
    if matching_sessions:
        harnesses = {str(item.get("harness", CLAUDE_CODE)) for item in matching_sessions}
        if len(harnesses) == 1:
            harness = harnesses.pop()
            if harness == ANTIGRAVITY and action not in {"consult", "critique", "continue"}:
                return CLAUDE_CODE, {"basis": "antigravity_session_action_ineligible"}
            return harness, {"basis": "matching_active_session"}
        return CLAUDE_CODE, {"basis": "ambiguous_cross_harness_session"}
    normalized = request.lower()
    explicit_independent_review = any(marker in normalized for marker in INDEPENDENT_REVIEW_MARKERS)
    if not sensitive and action in {"consult", "critique"} and explicit_independent_review:
        if antigravity_ready:
            return ANTIGRAVITY, {"basis": "explicit_independent_review"}
        return CLAUDE_CODE, {"basis": "antigravity_not_ready"}
    return CLAUDE_CODE, {"basis": "default_project_collaborator"}

#!/usr/bin/env python3
"""Regression coverage for deterministic, role-only harness selection."""

from harness_routing import ANTIGRAVITY, CLAUDE_CODE, choose_harness


def main() -> None:
    selected, detail = choose_harness("请给我第二方案", "consult", False, [], True)
    assert selected == ANTIGRAVITY and detail["basis"] == "explicit_independent_review"
    selected, detail = choose_harness("implement this change", "execute", False, [], True)
    assert selected == CLAUDE_CODE and detail["basis"] == "default_project_collaborator"
    selected, detail = choose_harness("风险审查", "consult", True, [], True)
    assert selected == CLAUDE_CODE and detail["basis"] == "default_project_collaborator"
    selected, detail = choose_harness("second opinion", "consult", False, [], False)
    assert selected == CLAUDE_CODE and detail["basis"] == "antigravity_not_ready"
    selected, detail = choose_harness("second opinion", "consult", False, [{"harness": CLAUDE_CODE}], True)
    assert selected == CLAUDE_CODE and detail["basis"] == "matching_active_session"
    selected, detail = choose_harness("second opinion", "consult", False, [], True, ANTIGRAVITY)
    assert selected == ANTIGRAVITY and detail["basis"] == "user_specified_harness"
    selected, detail = choose_harness("second opinion", "execute", False, [], True, ANTIGRAVITY)
    assert selected == CLAUDE_CODE and detail["basis"] == "requested_antigravity_ineligible"
    print("harness-routing tests passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Quality gate smoke test."""

from quality_gate import ast_errors, source_policy_errors


def main() -> None:
    assert not ast_errors(), ast_errors()
    assert not source_policy_errors(), source_policy_errors()
    print("quality-gate tests passed")


if __name__ == "__main__":
    main()

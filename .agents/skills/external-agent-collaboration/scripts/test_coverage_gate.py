#!/usr/bin/env python3
"""Regression tests for the stdlib trace coverage gate."""

from __future__ import annotations

from coverage_gate import CORE_MODULES, statement_lines, threshold_errors


def main() -> None:
    assert CORE_MODULES
    lines = statement_lines(__import__("coverage_gate").SCRIPT_ROOT / "workspace_context.py")
    assert 38 in lines and 148 in lines
    passing = {
        "total": {"percent": 80.0},
        "modules": {name: {"percent": 90.0} for name in CORE_MODULES},
    }
    assert threshold_errors(passing) == []
    failing = {
        "total": {"percent": 79.99},
        "modules": {name: {"percent": 89.99} for name in CORE_MODULES},
    }
    errors = threshold_errors(failing)
    assert len(errors) == len(CORE_MODULES) + 1
    print("coverage-gate tests passed")


if __name__ == "__main__":
    main()

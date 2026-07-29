#!/usr/bin/env python3
"""Local regression tests for one-pass independent review orchestration."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("review_execution.py")
SPEC = importlib.util.spec_from_file_location("review_execution", SCRIPT)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def main() -> None:
    assert review.review_provider("mimo", "auto") == "deepseek"
    assert review.review_provider("deepseek", "auto") == "mimo"
    try:
        review.review_provider("mimo", "mimo")
    except ValueError:
        pass
    else:
        raise AssertionError("Reviewer must differ from source provider.")
    text = review.handoff_text({"topic": "x", "changed_files": ["src/a.py"], "outcome_results": [{"passed": True}]})
    assert "Do not edit files" in text and "src/a.py" in text
    print("review-execution tests passed")


if __name__ == "__main__":
    main()

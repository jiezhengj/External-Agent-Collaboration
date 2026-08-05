#!/usr/bin/env python3
"""Structured activation and classifier false-positive tests."""

from classify_task import classify, efficiency_fields


def main() -> None:
    structured = classify('{"schema_version":1,"request":"review the routing code","task_type":"code","mode":"critique","independent_review":true,"sensitive":false}')
    assert structured["structured"] is True and structured["delegation"] == "external_agent"
    current_code = classify("Review the current implementation files and fix the bug")
    assert current_code["task_type"] != "current_information"
    small = classify("Rewrite this short paragraph")
    fields = efficiency_fields(small, "Rewrite this short paragraph")
    assert fields["recommended_return_mode"] == "compact"
    print("activation-case tests passed")


if __name__ == "__main__":
    main()

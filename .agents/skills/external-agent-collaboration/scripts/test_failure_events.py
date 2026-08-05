#!/usr/bin/env python3
"""Privacy and exactly-once failure ledger tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from failure_events import STAGES, TERMINAL_STATUSES, event_path, write_failure_event
from workspace_context import WorkspaceContext


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="failure-events-") as directory:
        root = Path(directory)
        context = WorkspaceContext(root, root, root, root, root / ".shared", root / ".ai-collaboration", root / ".shared" / "bad-cases")
        secret_fixture = "sk-" + "abcdefghijklmnopqrstuvwxyz012345"
        path = write_failure_event(context, invocation_id="inv-test", error_code="provider_unclassified_failure", terminal_status="failed_invocation", stage="invocation", message=f"{secret_fixture} at {root / 'private.env'}", working_directory=str(root))
        assert path == event_path(context, "inv-test") and path.is_file()
        record = json.loads(path.read_text(encoding="utf-8"))
        encoded = json.dumps(record, ensure_ascii=False)
        assert secret_fixture not in encoded
        assert str(root) not in encoded
        write_failure_event(context, invocation_id="inv-test", error_code="provider_timeout", message="updated")
        assert len(list((root / ".shared" / "bad-cases").glob("inv-test.json"))) == 1
        assert json.loads(path.read_text(encoding="utf-8"))["error_code"] == "provider_timeout"
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["terminal_status"] in TERMINAL_STATUSES and record["stage"] in STAGES
        assert record["skill_runtime_version"]
    print("failure-event tests passed")


if __name__ == "__main__":
    main()

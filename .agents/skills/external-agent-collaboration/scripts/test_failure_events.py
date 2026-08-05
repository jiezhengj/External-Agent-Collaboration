#!/usr/bin/env python3
"""Privacy and exactly-once failure ledger tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from failure_events import STAGES, TERMINAL_STATUSES, event_path, write_failure_event
from workspace_context import WorkspaceContext


def main() -> None:
    assert write_failure_event(None, invocation_id="inv-none") is None
    assert write_failure_event(WorkspaceContext(Path.cwd(), Path.cwd(), Path.cwd(), Path.cwd(), Path.cwd(), Path.cwd(), Path.cwd()), invocation_id="bad/id") is None
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
        outside = root.parent / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        write_failure_event(context, invocation_id="inv-paths", error_code="not-a-real-code", terminal_status="not-a-status", stage="not-a-stage", working_directory=str(outside), message=None)
        paths_record = json.loads((root / ".shared" / "bad-cases" / "inv-paths.json").read_text(encoding="utf-8"))
        assert paths_record["error_code"] == "unexpected_internal_error"
        assert paths_record["terminal_status"] == "failed_invocation"
        assert paths_record["stage"] == "unexpected"
        with patch("failure_events.subprocess.run", side_effect=OSError):
            write_failure_event(context, invocation_id="inv-git-error")
        with patch("failure_events.os.replace", side_effect=OSError):
            try:
                write_failure_event(context, invocation_id="inv-write-error")
            except OSError:
                pass
            else:
                raise AssertionError("ledger replace failure must be observable")
        assert not list((root / ".shared" / "bad-cases").glob(".inv-write-error.*.tmp"))
        outside.unlink()
    print("failure-event tests passed")


if __name__ == "__main__":
    main()

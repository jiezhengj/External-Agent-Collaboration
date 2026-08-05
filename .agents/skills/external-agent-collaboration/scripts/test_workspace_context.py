#!/usr/bin/env python3
"""Cross-project path and platform-neutral containment tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from workspace_context import WorkspaceContextError, resolve_context


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="workspace-context-") as directory:
        root = Path(directory)
        (root / ".git").mkdir()
        child = root / "src"
        child.mkdir()
        try:
            resolve_context(child)
        except WorkspaceContextError as exc:
            assert exc.code == "project_root_required_for_non_git_workspace"
        else:
            raise AssertionError("a fake .git directory must not be treated as a repository")
        context = resolve_context(child, root)
        assert context.target_project_root == root.resolve()
        assert context.target_workdir == child.resolve()
        assert context.target_relative(child / "file.txt").as_posix() == "src/file.txt"
        try:
            context.target_path("../escape")
        except WorkspaceContextError:
            pass
        else:
            raise AssertionError("parent traversal must be rejected")
    print("workspace-context tests passed")


if __name__ == "__main__":
    main()

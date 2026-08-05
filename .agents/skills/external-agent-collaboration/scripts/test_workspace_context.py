#!/usr/bin/env python3
"""Cross-project path and platform-neutral containment tests."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import patch

import workspace_context
from workspace_context import WorkspaceContextError, link_like, nearest_git_root, resolve_context


def main() -> None:
    with patch("workspace_context.os.path.commonpath", side_effect=ValueError):
        assert workspace_context._contains(Path("C:/repo"), Path("D:/repo")) is False
    with patch("workspace_context.subprocess.run", return_value=CompletedProcess([], 1, "", "")):
        assert nearest_git_root(Path.cwd()) is None
    with patch("workspace_context.subprocess.run", side_effect=OSError):
        assert nearest_git_root(Path.cwd()) is None
    with patch("workspace_context.subprocess.run", side_effect=workspace_context.subprocess.TimeoutExpired("git", 1)):
        assert nearest_git_root(Path.cwd()) is None
    with patch("workspace_context.subprocess.run", return_value=CompletedProcess([], 0, "", "")):
        assert nearest_git_root(Path("/path-that-does-not-exist-for-context-test")) is None
    try:
        link_like(Path("/path-that-does-not-exist-for-context-test"))
    except WorkspaceContextError as exc:
        assert exc.code == "scope_guard_unavailable"
    else:
        raise AssertionError("missing path link inspection must fail closed")

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
        try:
            context.target_path(Path(directory) / "absolute")
        except WorkspaceContextError:
            pass
        else:
            raise AssertionError("absolute target path must be rejected")
        try:
            context.target_relative(Path(directory).parent / "outside")
        except WorkspaceContextError:
            pass
        else:
            raise AssertionError("target-relative escape must be rejected")
        try:
            context.skill_relative(Path(directory).parent / "outside")
        except WorkspaceContextError:
            pass
        else:
            raise AssertionError("skill-relative escape must be rejected")
        with patch("workspace_context.os.path.samefile", side_effect=OSError):
            assert context.cross_project is True
        assert context.workspace_hash
        assert context.target_path("src/file.txt") == (root / "src/file.txt").resolve()

    with tempfile.TemporaryDirectory(prefix="workspace-context-errors-") as directory:
        root = Path(directory)
        child = root / "child"
        child.mkdir()
        with patch("workspace_context.skill_project_root", return_value=Path.cwd()):
            try:
                resolve_context(child, root / "missing")
            except WorkspaceContextError as exc:
                assert exc.code == "project_root_not_directory"
            else:
                raise AssertionError("missing explicit project root must fail")
            other = root / "other"
            other.mkdir()
            outside = root.parent / f"workspace-context-outside-{root.name}"
            outside.mkdir()
            with patch("workspace_context.nearest_git_root", side_effect=[other, None]):
                try:
                    resolve_context(outside, root)
                except WorkspaceContextError as exc:
                    assert exc.code == "project_root_git_root_conflict"
                else:
                    raise AssertionError("conflicting discovered root must fail")
            with patch("workspace_context.nearest_git_root", side_effect=[other, other]):
                try:
                    resolve_context(child, root)
                except WorkspaceContextError as exc:
                    assert exc.code == "project_root_git_root_conflict"
                else:
                    raise AssertionError("explicit root Git mismatch must fail")
            with patch("workspace_context.nearest_git_root", side_effect=[root.resolve(), root.resolve()]):
                try:
                    resolve_context(outside, root)
                except WorkspaceContextError as exc:
                    assert exc.code == "target_workdir_outside_project"
                else:
                    raise AssertionError("workdir outside explicit root must fail")
            outside.rmdir()

    fake_reparse = SimpleNamespace(st_mode=0, st_file_attributes=0x400)
    with patch("workspace_context.os.name", "nt"), patch("workspace_context.os.lstat", return_value=fake_reparse):
        assert link_like(Path("reparse-point")) is True
    fake_kernel = SimpleNamespace(GetFileAttributesW=lambda _path: 0x400)
    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(kernel32=fake_kernel))
    with patch("workspace_context.os.name", "nt"), patch("workspace_context.os.lstat", return_value=SimpleNamespace(st_mode=0)), patch.dict(sys.modules, {"ctypes": fake_ctypes}):
        assert link_like(Path("reparse-point-fallback")) is True
    fake_kernel_fail = SimpleNamespace(GetFileAttributesW=lambda _path: 0xFFFFFFFF)
    fake_ctypes_fail = SimpleNamespace(windll=SimpleNamespace(kernel32=fake_kernel_fail))
    with patch("workspace_context.os.name", "nt"), patch("workspace_context.os.lstat", return_value=SimpleNamespace(st_mode=0)), patch.dict(sys.modules, {"ctypes": fake_ctypes_fail}):
        try:
            link_like(Path("reparse-point-failed"))
        except WorkspaceContextError as exc:
            assert exc.code == "scope_guard_unavailable"
        else:
            raise AssertionError("failed Windows reparse inspection must fail closed")
    print("workspace-context tests passed")


if __name__ == "__main__":
    main()

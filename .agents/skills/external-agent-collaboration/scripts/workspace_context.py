"""Cross-project and cross-platform workspace resolution for the Skill runner.

The Skill lives in one repository, while the files being reviewed or edited may
live in another repository.  This module is deliberately dependency-light so
every public entrypoint can use the same path and control-root rules.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorkspaceContextError(RuntimeError):
    def __init__(self, message: str, code: str = "cross_project_context_unsupported") -> None:
        super().__init__(message)
        self.code = code


def _canonical(path: Path) -> Path:
    return Path(os.path.realpath(os.fspath(path)))


def _contains(root: Path, candidate: Path) -> bool:
    try:
        root_norm = os.path.normcase(os.path.normpath(os.fspath(root)))
        candidate_norm = os.path.normcase(os.path.normpath(os.fspath(candidate)))
        common = os.path.commonpath([root_norm, candidate_norm])
        return common == root_norm
    except (ValueError, OSError):
        return False


def nearest_git_root(path: Path) -> Path | None:
    """Find a Git root without invoking a shell or following user shell config."""
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    root = _canonical(Path(value))
    return root if root.is_dir() else None


def _skill_root() -> Path:
    # .../.agents/skills/external-agent-collaboration/scripts/workspace_context.py
    return _canonical(Path(__file__).resolve().parents[1])


def skill_project_root() -> Path:
    root = nearest_git_root(_skill_root())
    if root is None:
        raise WorkspaceContextError("Cannot determine the Git root containing the Skill.", "skill_project_root_unavailable")
    expected = root / ".agents" / "skills" / "external-agent-collaboration"
    try:
        same_skill = os.path.samefile(expected, _skill_root())
    except OSError:
        same_skill = _canonical(expected) == _skill_root()
    if not same_skill:
        raise WorkspaceContextError("The resolved Skill directory is not inside its declared project root.", "skill_project_root_unavailable")
    return root


def link_like(path: Path) -> bool:
    """Detect symlinks and Windows junction/reparse points without following them."""
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise WorkspaceContextError(f"Cannot inspect path link state: {path}", "scope_guard_unavailable") from exc
    if stat.S_ISLNK(info.st_mode):
        return True
    if os.name == "nt":
        attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        file_attributes = getattr(info, "st_file_attributes", None)
        if file_attributes is None:
            try:
                import ctypes
                value = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            except (AttributeError, OSError) as exc:
                raise WorkspaceContextError("Windows reparse-point inspection is unavailable.", "scope_guard_unavailable") from exc
            if value == 0xFFFFFFFF:
                raise WorkspaceContextError("Windows reparse-point inspection failed.", "scope_guard_unavailable")
            file_attributes = value
        if file_attributes & attribute:
            return True
    return False


@dataclass(frozen=True)
class WorkspaceContext:
    skill_project_root: Path
    skill_root: Path
    target_project_root: Path
    target_workdir: Path
    shared_control_root: Path
    target_control_root: Path
    failure_ledger_root: Path

    @property
    def cross_project(self) -> bool:
        try:
            return not os.path.samefile(self.skill_project_root, self.target_project_root)
        except OSError:
            return _canonical(self.skill_project_root) != _canonical(self.target_project_root)

    @property
    def workspace_hash(self) -> str:
        value = os.path.normcase(os.path.normpath(os.fspath(self.target_project_root))).encode("utf-8", "surrogatepass")
        return hashlib.sha256(value).hexdigest()

    def target_relative(self, path: Path) -> Path:
        candidate = _canonical(path)
        if not _contains(self.target_project_root, candidate):
            raise WorkspaceContextError(f"Path is outside target project root: {path}", "target_workdir_outside_project")
        return candidate.relative_to(self.target_project_root)

    def skill_relative(self, path: Path) -> Path:
        candidate = _canonical(path)
        if not _contains(self.skill_project_root, candidate):
            raise WorkspaceContextError(f"Path is outside Skill project root: {path}", "cross_project_context_unsupported")
        return candidate.relative_to(self.skill_project_root)

    def target_path(self, relative: str | Path) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise WorkspaceContextError("Target-relative path must not be absolute or contain '..'.", "target_workdir_outside_project")
        path = self.target_project_root / candidate
        if not _contains(self.target_project_root, _canonical(path)):
            raise WorkspaceContextError("Target-relative path escapes the project root.", "target_workdir_outside_project")
        return path


def resolve_context(working_directory: str | Path | None = None, project_root: str | Path | None = None) -> WorkspaceContext:
    skill_root = _skill_root()
    skill_root_project = skill_project_root()
    requested_workdir = _canonical(Path(working_directory) if working_directory is not None else skill_root_project)
    if not requested_workdir.is_dir():
        raise WorkspaceContextError("Working directory does not exist.", "target_workdir_outside_project")

    explicit_root = _canonical(Path(project_root)) if project_root is not None else None
    if explicit_root is not None:
        if not explicit_root.is_dir():
            raise WorkspaceContextError("Explicit project root is not a directory.", "project_root_not_directory")
        discovered = nearest_git_root(requested_workdir)
        git_root = nearest_git_root(explicit_root)
        if git_root is not None and git_root != explicit_root:
            raise WorkspaceContextError("Explicit project root is not the Git root.", "project_root_git_root_conflict")
        if discovered is not None and discovered != explicit_root and _contains(explicit_root, requested_workdir) is False:
            raise WorkspaceContextError("Working directory and explicit project root conflict.", "project_root_git_root_conflict")
        target_root = explicit_root
    else:
        target_root = nearest_git_root(requested_workdir)
        if target_root is None:
            raise WorkspaceContextError("A non-Git workspace requires --project-root.", "project_root_required_for_non_git_workspace")
    if not _contains(target_root, requested_workdir):
        raise WorkspaceContextError("Working directory is outside the target project root.", "target_workdir_outside_project")
    target_root = _canonical(target_root)
    return WorkspaceContext(
        skill_project_root=skill_root_project,
        skill_root=skill_root,
        target_project_root=target_root,
        target_workdir=requested_workdir,
        shared_control_root=skill_root_project / ".ai-collaboration",
        target_control_root=target_root / ".ai-collaboration",
        failure_ledger_root=skill_root_project / ".ai-collaboration" / "bad-cases",
    )


def default_context() -> WorkspaceContext:
    return resolve_context()

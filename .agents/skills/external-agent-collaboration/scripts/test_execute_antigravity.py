#!/usr/bin/env python3
"""Unit checks for main-worktree Antigravity execute policy."""
from execute_antigravity import full_auto_requires_isolation

assert full_auto_requires_isolation({"dangerously_skip_permissions": True})
assert not full_auto_requires_isolation({"dangerously_skip_permissions": False})
assert not full_auto_requires_isolation({})
print("execute-antigravity tests passed")

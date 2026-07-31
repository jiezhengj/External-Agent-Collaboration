#!/usr/bin/env python3
"""Regression test for minimal local collaboration-state initialization."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("bootstrap.py")
SPEC = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def main() -> None:
    original = bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL, bootstrap.SHARED_EXAMPLE, bootstrap.SHARED, bootstrap.PLATFORM_EXAMPLE, bootstrap.TRUST_EXAMPLE, bootstrap.TRUST_LOCAL, bootstrap.HARNESS_EXAMPLE, bootstrap.HARNESS_LOCAL, bootstrap.HARNESS_TRUST_EXAMPLE, bootstrap.HARNESS_TRUST_LOCAL
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = root / ".ai-collaboration"
        control.mkdir()
        example = control / "providers.local.example.json"
        example.write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        shared_example = control / "providers.shared.example.json"
        shared_example.write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        platform_example = control / f"providers.local.{bootstrap.host_platform()}.example.json"
        platform_example.write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        trust_example = control / "trusted-providers.local.example.json"
        trust_example.write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        harness_example = control / "harness-profiles.local.example.json"
        harness_example.write_text('{"schema_version": 1, "profiles": {}}\n', encoding="utf-8")
        harness_trust_example = control / "trusted-harnesses.local.example.json"
        harness_trust_example.write_text('{"schema_version": 1, "profiles": {}}\n', encoding="utf-8")
        bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL, bootstrap.SHARED_EXAMPLE, bootstrap.SHARED, bootstrap.PLATFORM_EXAMPLE, bootstrap.TRUST_EXAMPLE, bootstrap.TRUST_LOCAL, bootstrap.HARNESS_EXAMPLE, bootstrap.HARNESS_LOCAL, bootstrap.HARNESS_TRUST_EXAMPLE, bootstrap.HARNESS_TRUST_LOCAL = root, control, example, control / "providers.local.json", shared_example, control / "providers.shared.json", platform_example, trust_example, control / "trusted-providers.local.json", harness_example, control / "harness-profiles.local.json", harness_trust_example, control / "trusted-harnesses.local.json"
        try:
            assert bootstrap.initialize() == 0
            assert (control / "project-context.md").is_file()
            assert (control / "decisions.md").is_file()
            assert (control / "topics").is_dir()
            assert (control / "providers.shared.json").is_file()
            assert (control / "trusted-providers.local.json").is_file()
            assert (control / "harness-profiles.local.json").is_file()
            assert (control / "trusted-harnesses.local.json").is_file()
            assert bootstrap.check() == 0
            warning = bootstrap.protect_local_file(control / "providers.local.json")
            if bootstrap.host_platform() == "windows":
                assert warning and "ACL" in warning
            else:
                assert warning is None
        finally:
            bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL, bootstrap.SHARED_EXAMPLE, bootstrap.SHARED, bootstrap.PLATFORM_EXAMPLE, bootstrap.TRUST_EXAMPLE, bootstrap.TRUST_LOCAL, bootstrap.HARNESS_EXAMPLE, bootstrap.HARNESS_LOCAL, bootstrap.HARNESS_TRUST_EXAMPLE, bootstrap.HARNESS_TRUST_LOCAL = original
    print("bootstrap tests passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run one full-auto Antigravity experiment in a disposable project copy."""
from __future__ import annotations

import argparse, json, os, shutil, tempfile, time, uuid
from pathlib import Path

import collaborate
from antigravity_adapter import AntigravityAdapter, AntigravityInvocation
from harness_profile_support import load_profiles, trusted


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", default="antigravity_local_full_auto")
    p.add_argument("--handoff", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--expected", required=True)
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()
    profile = load_profiles(collaborate.SHARED_CONTROL_ROOT).get(args.profile)
    if not profile or profile.get("dangerously_skip_permissions") is not True or not trusted(collaborate.SHARED_CONTROL_ROOT, args.profile, profile):
        raise SystemExit("Isolated full-auto requires a trusted explicit local-full-auto profile.")
    handoff = (collaborate.PROJECT_ROOT / args.handoff).read_text(encoding="utf-8")
    collaborate.validate_handoff_sensitivity(handoff)
    with tempfile.TemporaryDirectory(prefix="agy-isolated-") as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        target = root / args.target
        target.parent.mkdir(parents=True)
        source = collaborate.PROJECT_ROOT / args.target
        if source.exists():
            shutil.copy2(source, target)
        before = target.read_text(encoding="utf-8") if target.exists() else None
        manifest_before = collaborate.manifest(root)
        prompt = f"Edit only {args.target}; replace its entire content with exactly: {args.expected}\nDo not use shell or change any other file.\n\n{handoff}"
        adapter = AntigravityAdapter()
        code, stdout, stderr = adapter.invoke(AntigravityInvocation(str(profile.get("launcher", "agy")), prompt, root, os.environ.copy(), args.timeout, collaborate.RESPONSE_CONTRACT_SCHEMA, profile, output_format="stream-json"))
        result, diag = adapter.parse_stream_result(stdout) if code == 0 else ({}, {"terminal_status": "process_error"})
        manifest_after = collaborate.manifest(root)
        changed = sorted(path for path in set(manifest_before) | set(manifest_after) if path != args.target and manifest_before.get(path) != manifest_after.get(path))
        matched = target.is_file() and target.read_text(encoding="utf-8") == args.expected + "\n"
        record = {"run_id": f"isolated-{int(time.time())}-{uuid.uuid4().hex[:8]}", "exit_code": code, "target_matched": matched, "target_before": before, "tool_diagnostics": diag, "non_target_changed_paths": changed, "permission_state": adapter.permission_state({**result, "error": stderr})}
        collaborate.write_json(collaborate.output_path(record["run_id"], "outputs"), record)
        print(json.dumps(record, ensure_ascii=False))
        return 0 if matched else 3


if __name__ == "__main__":
    raise SystemExit(main())

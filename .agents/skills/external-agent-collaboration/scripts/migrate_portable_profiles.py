#!/usr/bin/env python3
"""Copy legacy direct tokens into the current platform's ignored configuration file without printing them."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from platform_support import host_platform, infer_path_platform
from profile_support import ProfileConfigError, platform_local_file_path, profile_file_paths, provider_map, read_json


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
MIGRATION_STATE = CONTROL_ROOT / "providers.migration.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def token_environment_name(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper() or "PROVIDER"
    return f"EXT_AGENT_{normalized}_ANTHROPIC_AUTH_TOKEN"


def portable_directory(profile: dict[str, Any], provider: str) -> str:
    configured = profile.get("config_dir")
    if isinstance(configured, str) and configured:
        name = PurePosixPath(configured.replace("\\", "/")).name
        if name.startswith("."):
            return name
    return ".claude-" + re.sub(r"[^A-Za-z0-9._-]+", "-", provider).strip("-")


def non_secret_environment(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
        and not any(marker in key.upper() for marker in ("TOKEN", "KEY", "SECRET", "PASSWORD"))
    }


def portable_profile(provider: str, legacy: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "config_dir_relative_to_home": portable_directory(legacy, provider),
        "launcher": "claude",
    }
    environment = non_secret_environment(legacy.get("environment"))
    if environment:
        result["environment"] = environment
    required = legacy.get("required_environment")
    if isinstance(required, list):
        remaining = [name for name in required if isinstance(name, str) and name != "ANTHROPIC_AUTH_TOKEN"]
        if remaining:
            result["required_environment"] = remaining
    return result


def legacy_profiles() -> dict[str, dict[str, Any]]:
    _shared, local = profile_file_paths(CONTROL_ROOT)
    if not local.is_file():
        raise ProfileConfigError("No legacy providers.local.json exists to migrate.")
    return provider_map(read_json(local), local.name)


def direct_token(profile: dict[str, Any]) -> str | None:
    token = profile.get("auth_token")
    return token if isinstance(token, str) and token else None


def platform_local_fields(profile: dict[str, Any], platform: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for field in ("config_dir", "launcher"):
        value = profile.get(field)
        if not isinstance(value, str) or not value:
            continue
        value_platform = infer_path_platform(value)
        if value_platform is None or value_platform == platform:
            output[field] = value
    return output


def migration_preview(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    providers = [provider for provider, profile in profiles.items() if direct_token(profile)]
    return {
        "platform": host_platform(),
        "providers_with_direct_tokens": sorted(providers),
        "shared_profile": "providers.shared.json",
        "platform_overlay": platform_local_file_path(CONTROL_ROOT).name,
        "credential_target": "current platform local configuration file",
        "legacy_cleanup": "not performed; run explicitly after both macOS and Windows migrations complete",
    }


def migration_status(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "platform": host_platform(),
        "legacy_direct_token_providers": sorted(provider for provider, profile in profiles.items() if direct_token(profile)),
        "platform_overlays": {platform: platform_local_file_path(CONTROL_ROOT, platform).is_file() for platform in ("windows", "macos")},
        "legacy_cleanup_ready": all(platform_local_file_path(CONTROL_ROOT, platform).is_file() for platform in ("windows", "macos")),
    }


def apply(profiles: dict[str, dict[str, Any]], *, home: Path | None = None) -> dict[str, Any]:
    platform = host_platform()
    shared_file, _local = profile_file_paths(CONTROL_ROOT)
    shared_document = read_json(shared_file) if shared_file.is_file() else {"schema_version": 1, "providers": {}}
    shared_providers = provider_map(shared_document, shared_file.name)
    overlay_file = platform_local_file_path(CONTROL_ROOT, platform)
    overlay_document = read_json(overlay_file) if overlay_file.is_file() else {"schema_version": 1, "providers": {}}
    overlay_providers = provider_map(overlay_document, overlay_file.name)
    migrated: list[str] = []
    initialized_directories: list[str] = []
    for provider, profile in profiles.items():
        token = direct_token(profile)
        if not token:
            continue
        if provider not in shared_providers:
            shared_providers[provider] = portable_profile(provider, profile)
        else:
            shared_providers[provider].pop("auth_token_env", None)
        relative_directory = shared_providers[provider].get("config_dir_relative_to_home")
        if isinstance(relative_directory, str) and relative_directory:
            (home or Path.home()).joinpath(relative_directory).mkdir(parents=True, exist_ok=True)
            initialized_directories.append(provider)
        overlay_providers[provider] = {"auth_token": token, **platform_local_fields(profile, platform)}
        migrated.append(provider)
    if not migrated:
        raise ProfileConfigError("No direct auth_token values were found in providers.local.json.")
    shared_document["schema_version"] = max(1, int(shared_document.get("schema_version", 1)))
    shared_document["providers"] = shared_providers
    overlay_document["schema_version"] = max(1, int(overlay_document.get("schema_version", 1)))
    overlay_document["providers"] = overlay_providers
    write_json(shared_file, shared_document)
    write_json(overlay_file, overlay_document)
    state = read_json(MIGRATION_STATE) if MIGRATION_STATE.is_file() else {"schema_version": 1, "platforms": {}}
    state.setdefault("platforms", {})[platform] = {"migrated_at": datetime.now(timezone.utc).isoformat(), "providers": sorted(migrated)}
    write_json(MIGRATION_STATE, state)
    return {"platform": platform, "migrated_providers": sorted(migrated), "initialized_config_directories": sorted(initialized_directories), "credential_target": overlay_file.name}


def remove_windows_environment(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if host_platform() != "windows":
        raise ProfileConfigError("Windows environment-variable cleanup must run on Windows.")
    import winreg

    removed: list[str] = []
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)
    try:
        for provider, profile in profiles.items():
            if not direct_token(profile):
                continue
            try:
                winreg.DeleteValue(key, token_environment_name(provider))
            except FileNotFoundError:
                continue
            removed.append(provider)
    finally:
        winreg.CloseKey(key)
    return {"platform": "windows", "removed_environment_token_references": sorted(removed)}


def restore_windows_environment(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if host_platform() != "windows":
        raise ProfileConfigError("Windows environment-variable restoration must run on Windows.")
    import winreg

    restored: list[str] = []
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)
    try:
        for provider, profile in profiles.items():
            token = direct_token(profile)
            if not token:
                continue
            winreg.SetValueEx(key, token_environment_name(provider), 0, winreg.REG_SZ, token)
            restored.append(provider)
    finally:
        winreg.CloseKey(key)
    return {"platform": "windows", "restored_environment_token_references": sorted(restored)}


def cleanup_legacy(*, home: Path | None = None) -> dict[str, Any]:
    _shared, local_file = profile_file_paths(CONTROL_ROOT)
    missing = [platform for platform in ("windows", "macos") if not platform_local_file_path(CONTROL_ROOT, platform).is_file()]
    if missing:
        raise ProfileConfigError("Legacy cleanup requires completed platform overlays: " + ", ".join(missing))
    profiles = legacy_profiles()
    if not any(direct_token(profile) for profile in profiles.values()):
        raise ProfileConfigError("Legacy profile contains no direct token values to clean up.")
    backup = (home or Path.home()) / ".external-agent-collaboration" / "providers.local.legacy-backup.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(local_file.read_bytes())
    write_json(local_file, {"schema_version": 1, "providers": {}})
    return {"legacy_profile_cleaned": True, "backup_created": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Copy direct tokens into the current host's ignored platform profile.")
    mode.add_argument("--cleanup-legacy", action="store_true", help="After both platform migrations, remove direct tokens from the synced legacy profile.")
    mode.add_argument("--remove-windows-env", action="store_true", help="Remove only environment token values previously created by this migration tool.")
    mode.add_argument("--restore-windows-env", action="store_true", help="Restore environment token values from the ignored legacy profile without printing them.")
    mode.add_argument("--status", action="store_true", help="Show migration readiness without reading or printing token values.")
    args = parser.parse_args()
    try:
        profiles = legacy_profiles()
        payload = cleanup_legacy() if args.cleanup_legacy else restore_windows_environment(profiles) if args.restore_windows_env else remove_windows_environment(profiles) if args.remove_windows_env else apply(profiles) if args.apply else migration_status(profiles) if args.status else migration_preview(profiles)
    except ProfileConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

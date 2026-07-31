"""Load portable shared provider profiles with optional local overlays."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from platform_support import host_platform


class ProfileConfigError(ValueError):
    """Raised when provider profile documents are invalid or unsafe to share."""


def profile_file_paths(control_root: Path) -> tuple[Path, Path]:
    return control_root / "providers.shared.json", control_root / "providers.local.json"


def platform_local_file_path(control_root: Path, platform: str | None = None) -> Path:
    return control_root / f"providers.local.{platform or host_platform()}.json"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileConfigError(f"Invalid JSON in {path.name}: {exc.msg}") from exc


def provider_map(data: Any, name: str) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        raise ProfileConfigError(f"{name} must be a JSON object.")
    providers = data.get("providers", data)
    if not isinstance(providers, dict):
        raise ProfileConfigError(f"{name}.providers must be an object.")
    invalid = [key for key, value in providers.items() if not isinstance(key, str) or not isinstance(value, dict)]
    if invalid:
        raise ProfileConfigError(f"{name} must map provider keys to objects.")
    return providers


def merge_profile(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key == "environment" and isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def portable_launcher(value: Any) -> bool:
    return isinstance(value, str) and value and "/" not in value and "\\" not in value and not value.lower().endswith(".exe")


def safe_relative_directory(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    posix = value.replace("\\", "/")
    return not posix.startswith("/") and not (len(posix) >= 2 and posix[1] == ":") and ".." not in PurePosixPath(posix).parts


def home_relative_directory(relative: str, platform: str, home: Path | None) -> str:
    base = str(home or Path.home())
    if platform == "windows":
        return str(PureWindowsPath(base) / PureWindowsPath(relative))
    return str(PurePosixPath(base) / PurePosixPath(relative))


def validate_shared_profile(provider: str, profile: dict[str, Any]) -> None:
    if "auth_token" in profile or "auth_token_keychain_service" in profile:
        raise ProfileConfigError(f"Shared provider '{provider}' must reference local authentication, not store auth_token or Keychain settings.")
    if "config_dir" in profile:
        raise ProfileConfigError(f"Shared provider '{provider}' must use config_dir_relative_to_home, not config_dir.")
    relative = profile.get("config_dir_relative_to_home")
    if not safe_relative_directory(relative):
        raise ProfileConfigError(f"Shared provider '{provider}' needs a safe relative config_dir_relative_to_home value.")
    launcher = profile.get("launcher", "claude")
    if not portable_launcher(launcher):
        raise ProfileConfigError(f"Shared provider '{provider}' launcher must be a PATH-resolved command without a platform file extension.")
    environment = profile.get("environment", {})
    if not isinstance(environment, dict):
        raise ProfileConfigError(f"Shared provider '{provider}'.environment must be an object.")
    sensitive = [key for key in environment if any(marker in str(key).upper() for marker in ("TOKEN", "KEY", "SECRET", "PASSWORD"))]
    if sensitive:
        raise ProfileConfigError(f"Shared provider '{provider}' environment must not contain credential values.")


def platform_override(profile: dict[str, Any], platform: str) -> dict[str, Any]:
    overrides = profile.get("platform_overrides", {})
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise ProfileConfigError("platform_overrides must be an object.")
    value = overrides.get(platform, {})
    if not isinstance(value, dict):
        raise ProfileConfigError(f"platform_overrides.{platform} must be an object.")
    return value


def resolve_profile(profile: dict[str, Any], *, platform: str | None = None, home: Path | None = None) -> dict[str, Any]:
    platform = platform or host_platform()
    resolved = merge_profile(profile, platform_override(profile, platform))
    resolved.pop("platform_overrides", None)
    relative = resolved.pop("config_dir_relative_to_home", None)
    if relative is not None and "config_dir" not in resolved:
        if not safe_relative_directory(relative):
            raise ProfileConfigError("config_dir_relative_to_home must be a safe relative path.")
        resolved["config_dir"] = home_relative_directory(relative, platform, home)
    resolved.setdefault("launcher", "claude")
    return resolved


def load_profiles(control_root: Path) -> dict[str, dict[str, Any]]:
    shared_file, local_file = profile_file_paths(control_root)
    platform_file = platform_local_file_path(control_root)
    shared = provider_map(read_json(shared_file), shared_file.name) if shared_file.is_file() else {}
    local = provider_map(read_json(local_file), local_file.name) if local_file.is_file() else {}
    platform_local = provider_map(read_json(platform_file), platform_file.name) if platform_file.is_file() else {}
    if not shared and not local and not platform_local:
        raise ProfileConfigError(
            "Provider profiles are missing. Create providers.shared.json from its public example, "
            "or configure providers.local.json for one machine."
        )
    for provider, profile in shared.items():
        validate_shared_profile(provider, profile)
    output: dict[str, dict[str, Any]] = {}
    for provider in sorted(set(shared) | set(local) | set(platform_local)):
        combined = merge_profile(shared.get(provider, {}), platform_override(shared.get(provider, {}), host_platform()))
        combined.pop("platform_overrides", None)
        combined = merge_profile(combined, local.get(provider, {}))
        combined = merge_profile(combined, platform_local.get(provider, {}))
        output[provider] = resolve_profile(combined)
    return output


def environment_token(profile: dict[str, Any]) -> str | None:
    name = profile.get("auth_token_env")
    if not isinstance(name, str) or not name:
        return None
    return os.environ.get(name) or None

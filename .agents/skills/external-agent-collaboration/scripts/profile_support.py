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


ROUTING_SCHEMA_VERSION = 1
ROUTING_STRATEGIES = {"fair_round_robin", "fixed", "weighted_round_robin"}
ROUTING_TASK_TYPES = {"code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information"}
ROUTING_MODES = {"analyze", "draft", "critique", "revise", "execute", "verify"}
MAX_PROVIDER_WEIGHT = 100
MAX_TOTAL_PROVIDER_WEIGHT = 1000


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
    if "providers" not in data and "routing" in data:
        extras = set(data) - {"routing", "schema_version"}
        if extras:
            raise ProfileConfigError(f"{name} mixes routing with flat provider keys {sorted(extras)}; wrap providers under a providers object.")
        return {}
    providers = data.get("providers", data)
    if not isinstance(providers, dict):
        raise ProfileConfigError(f"{name}.providers must be an object.")
    invalid = [key for key, value in providers.items() if not isinstance(key, str) or not isinstance(value, dict)]
    if invalid:
        raise ProfileConfigError(f"{name} must map provider keys to objects.")
    return providers


def routing_config(data: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        raise ProfileConfigError(f"{name} must be a JSON object.")
    if "routing" not in data:
        return None
    routing = data["routing"]
    if not isinstance(routing, dict):
        raise ProfileConfigError(f"{name}.routing must be an object.")
    return copy.deepcopy(routing)


def default_routing() -> dict[str, Any]:
    return {
        "schema_version": ROUTING_SCHEMA_VERSION,
        "default": {"strategy": "fair_round_robin"},
        "task_overrides": {},
    }


def _merge_policy(base: Any, overlay: Any) -> Any:
    if not isinstance(overlay, dict):
        return copy.deepcopy(overlay)
    merged = copy.deepcopy(base) if isinstance(base, dict) else {}
    for key, value in overlay.items():
        if key == "weights" and isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **copy.deepcopy(value)}
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_routing_core(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key == "default":
            merged[key] = _merge_policy(merged.get(key), value)
        elif key == "task_overrides" and isinstance(value, dict):
            current = merged.setdefault(key, {})
            if not isinstance(current, dict):
                current = {}
                merged[key] = current
            for task_key, policy in value.items():
                current[task_key] = _merge_policy(current.get(task_key), policy)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_routing(base: dict[str, Any] | None, overlay: dict[str, Any] | None, platform: str | None = None) -> dict[str, Any]:
    """Merge a routing overlay and its optional platform-specific section."""
    merged = copy.deepcopy(base) if isinstance(base, dict) else default_routing()
    if overlay is None:
        return merged
    if not isinstance(overlay, dict):
        raise ProfileConfigError("routing overlay must be an object.")
    core = {key: value for key, value in overlay.items() if key != "platform_overrides"}
    merged = _merge_routing_core(merged, core)
    platform_overrides = overlay.get("platform_overrides")
    if platform_overrides is not None:
        if not isinstance(platform_overrides, dict):
            raise ProfileConfigError("routing.platform_overrides must be an object.")
        selected = platform_overrides.get(platform or host_platform(), {})
        if not isinstance(selected, dict):
            raise ProfileConfigError("routing.platform_overrides.<platform> must be an object.")
        merged = _merge_routing_core(merged, selected)
    return merged


def _validate_policy(policy: Any, provider_keys: set[str], location: str) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise ProfileConfigError(f"{location} must be an object.")
    unknown = set(policy) - {"strategy", "provider", "weights"}
    if unknown:
        raise ProfileConfigError(f"{location} contains unsupported fields: {sorted(unknown)}.")
    strategy = policy.get("strategy")
    if strategy not in ROUTING_STRATEGIES:
        raise ProfileConfigError(f"{location}.strategy must be one of {sorted(ROUTING_STRATEGIES)}.")
    if strategy == "fair_round_robin":
        if "provider" in policy or "weights" in policy:
            raise ProfileConfigError(f"{location} fair_round_robin cannot define provider or weights.")
        return {"strategy": strategy}
    if strategy == "fixed":
        provider = policy.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            raise ProfileConfigError(f"{location}.provider is required for fixed routing.")
        if provider not in provider_keys:
            raise ProfileConfigError(f"routing_provider_unknown: {location}.provider '{provider}' is not configured.")
        if "weights" in policy:
            raise ProfileConfigError(f"{location} fixed cannot define weights.")
        return {"strategy": strategy, "provider": provider}
    weights = policy.get("weights")
    if not isinstance(weights, dict) or not weights:
        raise ProfileConfigError(f"{location}.weights must be a non-empty object for weighted_round_robin.")
    normalized: dict[str, int] = {}
    for provider, weight in weights.items():
        if not isinstance(provider, str) or provider not in provider_keys:
            raise ProfileConfigError(f"routing_provider_unknown: {location}.weights references '{provider}'.")
        if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= MAX_PROVIDER_WEIGHT:
            raise ProfileConfigError(f"{location}.weights.{provider} must be an integer from 1 to {MAX_PROVIDER_WEIGHT}.")
        normalized[provider] = weight
    if sum(normalized.values()) > MAX_TOTAL_PROVIDER_WEIGHT:
        raise ProfileConfigError(f"{location}.weights total must not exceed {MAX_TOTAL_PROVIDER_WEIGHT}.")
    return {"strategy": strategy, "weights": normalized}


def validate_routing_policy(policy: Any, provider_keys: set[str] | list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise ProfileConfigError("routing must be an object.")
    version = policy.get("schema_version", ROUTING_SCHEMA_VERSION)
    if isinstance(version, bool) or version != ROUTING_SCHEMA_VERSION:
        raise ProfileConfigError(f"routing_config_invalid: routing.schema_version must be {ROUTING_SCHEMA_VERSION}.")
    allowed = {"schema_version", "default", "task_overrides"}
    unknown = set(policy) - allowed
    if unknown:
        raise ProfileConfigError(f"routing_config_invalid: routing contains unsupported fields {sorted(unknown)}.")
    providers = set(provider_keys)
    default = _validate_policy(policy.get("default"), providers, "routing.default")
    overrides = policy.get("task_overrides", {})
    if not isinstance(overrides, dict):
        raise ProfileConfigError("routing.task_overrides must be an object.")
    normalized_overrides: dict[str, dict[str, Any]] = {}
    for task_key, override in overrides.items():
        if not isinstance(task_key, str) or ":" not in task_key:
            raise ProfileConfigError(f"routing.task_overrides key '{task_key}' must be task_type:mode.")
        task_type, mode = task_key.split(":", 1)
        if task_type not in ROUTING_TASK_TYPES or mode not in ROUTING_MODES:
            raise ProfileConfigError(f"routing.task_overrides key '{task_key}' is not a known task_type:mode.")
        normalized_overrides[task_key] = _validate_policy(override, providers, f"routing.task_overrides[{task_key}]")
    return {"schema_version": ROUTING_SCHEMA_VERSION, "default": default, "task_overrides": normalized_overrides}


def load_routing(control_root: Path, provider_keys: set[str] | list[str] | tuple[str, ...] = (), platform: str | None = None) -> dict[str, Any]:
    """Load shared and local routing overlays without mixing them into profiles."""
    platform = platform or host_platform()
    merged = default_routing()
    shared_file, local_file = profile_file_paths(control_root)
    files = (shared_file, local_file, platform_local_file_path(control_root, platform))
    for path in files:
        if path.is_file():
            data = read_json(path)
            merged = merge_routing(merged, routing_config(data, path.name), platform)
    return validate_routing_policy(merged, provider_keys)


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
    response_transport = profile.get("response_transport", "direct")
    if response_transport not in {"direct", "buffered_sse"}:
        raise ProfileConfigError(f"Shared provider '{provider}' response_transport must be 'direct' or 'buffered_sse'.")


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
        if output[provider].get("response_transport", "direct") not in {"direct", "buffered_sse"}:
            raise ProfileConfigError(f"Provider '{provider}' response_transport must be 'direct' or 'buffered_sse'.")
    return output


def environment_token(profile: dict[str, Any]) -> str | None:
    name = profile.get("auth_token_env")
    if not isinstance(name, str) or not name:
        return None
    return os.environ.get(name) or None

#!/usr/bin/env python3
"""Record or revoke a user's local approval for one configured provider profile."""

from __future__ import annotations

import argparse

import collaborate
from harness_state import decorate_legacy_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, help="Provider key from providers.local.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true", help="Approve this provider's current non-secret profile configuration.")
    group.add_argument("--revoke", action="store_true", help="Remove its local collaboration approval.")
    args = parser.parse_args()
    configured = collaborate.profiles()
    profile = configured.get(args.provider)
    if not profile:
        raise collaborate.CollaborationError(f"Provider '{args.provider}' is not configured.")
    trust = collaborate.trust_registry()
    providers = trust["providers"]
    if args.approve:
        providers[args.provider] = {"approved": True, "profile_fingerprint": collaborate.profile_fingerprint(profile)}
        decorate_legacy_record(providers[args.provider], args.provider, collaborate.host_platform())
        collaborate.write_json(collaborate.TRUST_FILE, trust)
        print(f"Approved local external collaboration for provider '{args.provider}'. No credential or endpoint value was printed.")
    else:
        providers.pop(args.provider, None)
        collaborate.write_json(collaborate.TRUST_FILE, trust)
        print(f"Revoked local external collaboration approval for provider '{args.provider}'.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except collaborate.CollaborationError as exc:
        print(str(exc))
        raise SystemExit(2)

# Headless CLI Reference Baseline

This directory contains the Markdown conversions of two official headless-CLI documents used as an important engineering baseline for this project. They are reference material, not a claim that every documented option has been tested, enabled, or is safe in this runner.

| Reference | Local copy | Source | How this project uses it |
|---|---|---|---|
| Claude Code headless / Agent SDK CLI | [claude-code-headless.md](claude-code-headless.md) | [Official page](https://code.claude.com/docs/en/headless) | Invocation flags, native JSON Schema output, permission semantics, sessions, streaming and `--bare` trade-offs. |
| Antigravity CLI headless | [antigravity-cli-headless.md](antigravity-cli-headless.md) | [Official page](https://antigravity.google/docs/cli/headless) | Future harness adapter, JSON/stream output, conversation identity, soft permission denial, timeout and platform test design. |

The source pages were converted on 2026-07-31. Before relying on a time-sensitive CLI flag, Agent or implementation must re-check the official source and the locally installed CLI's `--help`; a reference copy does not replace either verification.

All future changes to invocation, profile, permission, session, output, classification or test behavior must consider both macOS and Windows. Each change records its platform impact and supplies two-platform verification, or a concrete reason why a platform is not affected.

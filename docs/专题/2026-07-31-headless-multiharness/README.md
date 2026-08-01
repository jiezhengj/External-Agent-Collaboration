# Headless multi-harness architecture

## Status

WP-11.0–WP-11.3 are implemented and now have macOS and Windows evidence. Windows completed the full local regression suite, a Claude Code native-schema smoke plus exact session resume, an Antigravity P2 read-only schema smoke, and a Claude exact-text smoke. Default Claude Code + DeepSeek/MiMo routing remains unchanged; Antigravity has no automatic routing. P3 diagnostics also completed: macOS/Windows controlled experiments and a macOS disposable full-auto experiment exposed the write tool and effective `always-proceed`, yet did not modify the declared target. AGY is therefore fixed to its verified P2 read-only role; automatic project execute remains Claude Code only. P4 candidate policy remains out of scope.

## Problem and baseline

The project grew from a Claude Code-specific runner. It now needs a deliberate boundary between a CLI harness, a provider/account target, a model profile, a session identity, permissions, health and structured results. The reference material is [Headless CLI reference baseline](../../headless-cli-references/README.md), containing converted official Claude Code and Antigravity pages.

## Confirmed direction

- First repair Claude Code structured output with native JSON Schema and isolate its adapter without changing DeepSeek/MiMo provider routing or profile-owned model aliases.
- Treat Antigravity as a distinct harness with separate auth, conversation IDs, permission semantics, health, trust and platform capabilities.
- Claude Code is the default project collaborator: it resumes its own sessions, performs bounded project edits, uses verified CC Switch plugin/MCP capabilities, and handles ordinary new project collaboration. Its healthy DeepSeek/MiMo providers remain a fair-rotation pool.
- Once P2 is verified, Antigravity is selected only when the task explicitly requests an independent review, second proposal, counterargument, or risk list, and is new, no-history, non-sensitive, and read-only. A new topic or session alone never selects it. It never fairly rotates with Claude Code; broadening that role requires a benchmark and a new DEC.
- Do not use subjective model-task matching. Classifier selection is based on existing session, user instruction, verified capabilities/permissions, required output contract, risk, task role and platform availability.
- Every iteration must cover macOS and Windows, or explain and verify why a platform is not affected.

## Phased evidence gates

| Phase | Scope | Gate before the next phase |
|---|---|---|
| P0 | ClaudeCodeAdapter and native JSON Schema output | macOS/Windows fake CLI tests; existing profile behavior unchanged. |
| P1 | Common adapter/state schema and dry-run migration | no cross-harness session, trust, health or capability reuse. |
| P2 | Antigravity read-only adapter | two-platform fake CLI plus a minimal real smoke for each configured, trusted local profile. |
| P3 | Antigravity controlled execute | Not admitted: the isolated full-auto experiment did not satisfy its target outcome. Revalidate only after a future CLI/agent update. |
| P4 | Optional harness candidate policy | user-approved benchmark evidence and explicit DEC. |

## Current documents

- [Decision record](../../决策记录/DEC-20260731-headless-multiharness.md)
- [Technical design](../../技术方案文档.md)
- [Implementation plan](../../实施计划文档.md)
- [Test cases](../../测试用例文档.md)
- [Windows Codex handoff](WINDOWS_HANDOFF.md)

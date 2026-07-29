---
name: external-agent-collaboration
description: Coordinate persistent collaborators from locally configured providers through the local Claude Code CLI, including automatic session recovery and bounded external file edits. Use when continuing a project/topic owned by an external collaborator, when large local context, an independent perspective, or scoped multi-file execution materially improves the work. Do not use for trivial chat, unverified current information, connector data, native image/document/spreadsheet production, secrets, deployments, or destructive operations.
---

# External Agent Collaboration

Coordinate one clear handoff and return per user request. Codex remains the user-facing coordinator; Configured providers are persistent collaborators, not disposable subprocesses.

## Choose the collaboration action

- `consult`: obtain an independent, read-only analysis.
- `continue`: resume the matching persistent topic session.
- `draft`: produce a text or planning artifact in the shared workspace.
- `critique`: assess a proposal or existing artifact without changing it.
- `execute`: modify files and run only explicitly allowed validation commands.

Use a native Codex tool instead for timely web facts, connected-account data, images, slides, spreadsheets, PDFs, or final formatted office artifacts. Do not delegate a simple task merely to obtain agreement.

## Prepare the handoff

1. Read `.ai-collaboration/project-context.md`, `current-state.md`, and `decisions.md` when they exist.
2. Write a non-sensitive request file and run `scripts/classify_task.py`; read [references/task-classification.md](references/task-classification.md). Stop on `prohibited`; use a native Codex tool on `native_codex`; continue only when the result is `external_agent` or a recorded override makes delegation materially useful.
3. Resolve action, topic, working directory, allowed paths, required checks, and provider.
4. Respect a user-named provider. Otherwise resume a matching active session; for a new topic, use the routing rule in `references/collaboration-protocol.md`.
5. For an `execute` task that needs a new file or directory, run `scripts/probe_capabilities.py --provider <provider>` when the provider capability record is missing, older than seven days, or invalidated by a Claude CLI/profile change. Do the same after a tool-availability failure. Do not probe before ordinary read-only work or every resumed session.
6. Read `.ai-collaboration/provider-capabilities.json` and the target session's `initial_toolset` in `sessions.json`. Provider capability describes a fresh session; any resumed session created before a new tool was enabled can retain its earlier tool set. Use native `Write` only when both records support it. Otherwise provide the minimum precise Bash creation command as an `--allow-command` and retain the path checkpoint. Fork/create a new session only when the task benefits more from the new tool set than from uninterrupted session identity.
7. Write a concise handoff into `.ai-collaboration/handoffs/`. For every `execute`, also write an expected-outcomes JSON file using [references/expected-outcomes.md](references/expected-outcomes.md). Include the objective, only relevant background, allowed paths, prohibited paths, validation commands, expected output, and uncertainty. Never copy the complete Codex chat.
8. Do not include `.env` contents, tokens, credentials, private keys, customer exports, or unrelated private files.

## Invoke

Run `scripts/doctor.py --provider <provider>` before the first call to a provider in a task. It checks prerequisites without reading secret values.

Run `scripts/collaborate.py` with the handoff and explicit action. For `execute`, always pass one or more `--allow-path` entries, `--expected-outcomes`, only the required `--allow-command` entries, and any exact `--validation-command` entries referenced by outcomes. The script performs a before/after checkpoint, restores out-of-scope or sensitive file changes, and restores the task change set when expected outcomes fail.

Never change the CC Switch global active provider. The script uses the selected provider's isolated `CLAUDE_CONFIG_DIR` from `.ai-collaboration/providers.local.json`.

## Session rules

- Bind every session to one topic, provider, model profile, and working directory.
- Resume only with a saved `session_id`; never use Claude CLI `--continue`.
- Create a new session when provider, model profile, working directory, or sustained topic changes.
- Create a separate session for a forked approach. Do not migrate a session from one provider profile to another.

## Execute-mode safety

The external collaborator may edit only the passed allowed paths. It may not commit, push, merge, deploy, publish, rewrite Git history, install global packages, access secrets, or use unapproved shell commands. Treat script-detected out-of-scope changes as failed execution even if the collaborator reports success.

After every call, read the generated result and log. For code, shell, security, architecture, or factual claims, inspect the change summary and independently run the required validation before reporting completion. For low-risk drafts or brainstorming, preserve the collaborator's distinct contribution when useful.

For a high-risk completed `execute`, run `scripts/review_execution.py --run-id <run_id> --provider <different-provider-key>` once after Codex has inspected the required validation. It creates a read-only critique with an explicitly selected different provider and never calls the executor again automatically. For creative or planning work, use one explicit provider per candidate; compare candidates in Codex instead of asking providers to debate each other.

After Codex judges a completed external run or observes user adoption, call `scripts/assess_run.py --run-id <id> --quality-score 0..5 --user-adopted true|false --rework-count <n>`. It updates only the anonymous metric event; never put the assessment rationale or user content in the metrics file.

## Report to the user

State the provider, action, session continuity, main contribution, changed files, validation performed by Codex, and any unresolved risk. Do not claim that the underlying model is Claude merely because the CLI harness is Claude Code.

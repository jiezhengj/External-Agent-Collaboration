---
name: external-agent-collaboration
description: Proactively coordinate persistent external collaborators from locally configured providers through the local Claude Code CLI for non-trivial repository work. Use when resuming an external-collaborator topic, the user asks for an independent or second-model review, the request covers a whole repository, related modules, or multiple files, or a bounded independent implementation would materially improve the result. Prefer this skill over solo handling when one of those conditions clearly applies. Do not use for simple questions, routine reviews, small single-file changes, current information, connected-account data, native image/document/spreadsheet production, secrets, deployments, or destructive operations. Use only when the project has a usable local provider configuration.
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

1. Read `.ai-collaboration/project-context.md` and `decisions.md` when they exist. For a continuing topic, locate and read only its one-page state in `.ai-collaboration/topics/`; do not load runtime outputs or transcripts by default.
2. Write a non-sensitive request file and run `scripts/classify_task.py`; read [references/task-classification.md](references/task-classification.md). Stop on `prohibited`; use a native Codex tool on `native_codex`; continue only when the result is `external_agent` or a recorded override makes delegation materially useful.
3. Resolve action, topic, working directory, allowed paths, required checks, and provider. Before the first real external invocation, ensure the provider's current local profile has a non-secret fingerprint record with `trust_provider.py --provider <key> --approve`. In this repository, `AGENTS.md` supplies the maintainer's standing authorization to create or refresh that local record as part of an implementation; do not request a redundant conversational approval. This does not bypass a Codex platform egress approval when the host requires one.
4. Respect a user-named provider. Otherwise resume a matching active session; for a new topic, use the routing rule in `references/collaboration-protocol.md`. For large non-sensitive text, first create and review a dry-run manifest using [references/batch-protocol.md](references/batch-protocol.md); do not use one large `execute`.
5. For an `execute` task that needs a new file or directory, run `scripts/probe_capabilities.py --provider <provider>` when the main-session file-creation capability record is missing, older than seven days, or invalidated by a Claude CLI/profile/platform change. Do the same after a main-process tool-availability failure. Do not probe before ordinary read-only work or every resumed session. This checks the runner's own `Write`/shell boundary only; it never probes, routes, or certifies Claude Code's internal subagents.
6. Read `.ai-collaboration/provider-capabilities.json` and the target session's `initial_toolset` in `sessions.json`. Provider capability describes a fresh session on one host platform; any resumed session created before a new tool was enabled can retain its earlier tool set. Never resume a session from a different host platform or workspace identity. Use native `Write` only when both records support it. A precise Bash creation command is allowed only when the current capability record explicitly confirms a POSIX shell; otherwise fork/create a session with `Write` or stop safely.
7. Write a concise handoff into `.ai-collaboration/handoffs/`. For every `execute`, also write an expected-outcomes JSON file using [references/expected-outcomes.md](references/expected-outcomes.md). For a persistent topic, pass a short `--topic-goal` and `--stop-rule`; they create/update one local topic-state page, not a transcript. Include only the objective, relevant background, allowed paths, prohibited paths, validation commands, expected output, and uncertainty. Never copy the complete Codex chat.
8. Do not include `.env` contents, tokens, credentials, private keys, customer exports, or unrelated private files.

## Reference and platform discipline

Use [the headless CLI reference baseline](../../../docs/headless-cli-references/README.md) when changing a harness invocation, permissions, sessions, structured output, or classifier policy. Treat it as design input only: verify a version-sensitive option against the official page and the locally installed CLI before relying on it.

Every iteration must explicitly consider macOS and Windows. A change must record its platform impact and include two-platform validation or a concrete not-affected rationale. Do not assume POSIX paths, Bash, file permissions, launchers, shell behavior, or credential stores on Windows.

## Invoke

Run `scripts/doctor.py --provider <provider>` before the first Claude Code provider call in a task. It checks prerequisites without reading secret values. A ready Antigravity P2 read-only profile additionally needs `scripts/doctor_harness.py --profile antigravity_readonly --json` and a current `trust_harness.py` fingerprint record. Under the maintainer's standing authorization, create or refresh that non-secret record before the real call.

`trusted-providers.local.json` is a second ignored local file. It permits the runner to use a named provider only while that provider's non-secret profile fingerprint matches its local record. A provider profile changing endpoint, model mapping, config directory, or non-secret environment invalidates the record; refresh it automatically under the maintainer's standing authorization. This project-level gate makes the trust state visible and auditable; it does not bypass Codex platform egress approval.

For a new external task, run `scripts/route_harness.py` with the original request, handoff and action. It resumes an exact session first; otherwise it automatically selects Antigravity only for a new/no-history, non-sensitive, explicit independent read-only `consult` or `critique` with a ready profile. It sends every other eligible task to Claude Code, where provider routing remains DeepSeek/MiMo-only. An Antigravity role that is not ready is reported as such and returned to Codex; it is never silently substituted with Claude Code. `route_harness.py` rejects Antigravity `execute`/`draft`, commands, outcomes, fork, full-auto profiles and non-standard response contracts. It delegates to `scripts/collaborate.py` or `scripts/consult_antigravity.py`; either direct entry remains available only when the caller has already made that routing decision.

The default `--return-mode compact` prints at most an 8 KiB envelope: run/status/outcomes, bounded summary and a local output path. The complete CLI JSON remains only in ignored `.ai-collaboration/outputs/`. A strictly outer ` ```json ` fence is normalized before contract validation; if an otherwise usable response still fails the contract, do not repeat the same consult automatically—consume the bounded result or inspect its explicit local path. Use `structured` only when the handoff requires the documented JSON response contract, `file_only` for workers, and `debug` only for explicit diagnosis. For Claude Code `execute`, always pass one or more `--allow-path` entries, `--expected-outcomes`, only the required `--allow-command` entries, and any exact `--validation-command` entries referenced by outcomes. The script performs a before/after checkpoint, restores out-of-scope or sensitive file changes, and restores the task change set when expected outcomes fail.

Never change the CC Switch global active provider. Provider credentials belong in user-managed, Git-ignored configuration files. The supported default is a shared non-secret definition plus platform-specific local profiles such as `.ai-collaboration/providers.local.macos.json` and `.ai-collaboration/providers.local.windows.json`; each may contain its platform's `auth_token`, launcher, and isolated `CLAUDE_CONFIG_DIR`. The user controls whether their private sync mechanism synchronizes these files. Do not require Keychain, Credential Manager, or environment variables, and never copy credential values into handoffs, outputs, logs, or version-controlled files.

The runner must not pass `--model`. Provider-internal default and FABLE/OPUS/SONNET/HAIKU/SUBAGENT mappings stay in the isolated CC Switch/Claude Code profile. For an auto-selected new topic, fairly rotate healthy eligible providers. Only a classified availability failure can make one cross-provider fallback; task, response-contract, outcome, validation, or scope failure is not an availability failure.

## Session rules

- Bind every session to one topic, provider, model profile, working directory, workspace identity, and host platform.
- Resume only with a saved `session_id`; never use Claude CLI `--continue`.
- Create a new session when provider, model profile, working directory, workspace identity, host platform, or sustained topic changes.
- Create a separate session for a forked approach. Do not migrate a session from one provider profile to another.

## Execute-mode safety

The external collaborator may edit only the passed allowed paths. It may not commit, push, merge, deploy, publish, rewrite Git history, install global packages, access secrets, or use unapproved shell commands. Treat script-detected out-of-scope changes as failed execution even if the collaborator reports success.

After every call, read the generated result and log. For code, shell, security, architecture, or factual claims, inspect the change summary and independently run the required validation before reporting completion. Treat provider claims that links, files, tests, or all sources were checked as unverified until a local check confirms them. For low-risk drafts or brainstorming, preserve the collaborator's distinct contribution when useful.

For a high-risk completed `execute`, run `scripts/review_execution.py --run-id <run_id> --provider <different-provider-key>` once after Codex has inspected the required validation. It creates a read-only critique with an explicitly selected different provider and never calls the executor again automatically. For creative or planning work, use one explicit provider per candidate; compare candidates in Codex instead of asking providers to debate each other.

After Codex judges a completed external run or observes user adoption, call `scripts/assess_run.py --run-id <id> --quality-score 0..5 --user-adopted true|false --rework-count <n>`. It updates only the anonymous metric event; never put the assessment rationale or user content in the metrics file.

## Report to the user

State the provider, action, session continuity, main contribution, changed files, validation performed by Codex, and any unresolved risk. Use the compact envelope by default; read a full local output only by explicit run path and for failure, sampling, audit, or debugging. Do not claim that the underlying model is Claude merely because the CLI harness is Claude Code.

# External Agent Collaboration

[中文说明](README.zh.md) · [Project index](README.md)

## Purpose

This repository documents and hosts a project-local workflow for coordinating persistent external coding collaborators from Codex through a local headless CLI harness. Claude Code is the implemented project-collaborator harness today; Antigravity has a separately gated, explicit read-only adapter that is not yet auto-routed. Codex remains the person-facing coordinator: it receives the request, decides whether delegation is worthwhile, checks the result, and reports back.

The project exists because a simple one-off model call is not enough for longer local work. A useful collaboration setup needs to keep providers and sessions separate, retain project context, constrain file edits, and verify what actually changed.

This is not tied to a particular model vendor. The operator supplies local provider profiles and model mappings for the services they use. MiMo and DeepSeek are examples from the original local setup, not requirements of this project. The current starter policy fairly rotates equally healthy, eligible providers; metrics are retained for audit and a future explicitly enabled learning policy.

## Functional requirements

The workflow is designed to provide the following behavior.

1. **One entry point and proactive selection.** Users work with Codex. When globally discoverable, the Skill proactively matches a resumed collaborator topic, a requested independent or second-model review, whole-repository/related-module/multi-file work, or a clearly bounded independent implementation. An external collaborator is used only after local provider configuration and post-selection classification permit it; simple questions, routine reviews, and small single-file changes stay with Codex.
2. **Separate persistent sessions.** A session is bound to a topic, provider, model profile, and working directory. Recovery uses a saved session ID, never an ambiguous “latest session” option.
3. **Task-aware delegation.** Before a call, classify the request by task type, work mode, risk, context size, and required tools. Small requests stay with Codex; current information, connected services, images, spreadsheets, presentations, PDFs, and final formatted office files use native Codex tools.
4. **Fair routing and bounded availability fallback.** Non-sensitive text and scoped code work on new topics fairly rotate among healthy providers. Only billing, authentication, endpoint, or transient service failures open a cooldown and may trigger one alternate-provider call.
5. **Bounded external edits.** An implementation handoff must state the allowed paths, forbidden paths, allowed commands, acceptance checks, and expected output.
6. **Machine-checked completion.** A model saying “done” is not success. Expected outcomes may require a file to exist, contain exact text, satisfy a limited JSON Schema, change a bounded number of paths, or pass an explicitly approved validation command.
7. **Capability-aware file creation.** A fresh session's ability to use `Write` is measured separately from an older resumed session's initial tool set. When a resumed session lacks a needed tool, the preferred resolution is a tracked fork; an exact shell fallback is a last resort.
8. **One-pass independent review.** A high-risk execution may receive one read-only critique from the other provider. The reviewer does not automatically re-invoke the executor, so there is no debate loop.
9. **Durable local state.** Project context, decisions, handoffs, outputs, session records, capability records, routing metrics, and archives live in a local collaboration directory rather than only in chat history.
10. **Harness isolation and two-platform discipline.** A harness, its provider/account target, model profile, session, permission semantics, health state, and capability record are separate. Every future change considers both macOS and Windows and supplies verification or an explicit not-affected rationale.

## Implementation

The project-local Skill includes these parts:

| Part | Responsibility |
| --- | --- |
| Task classifier | Decide direct, native-Codex, external, or prohibited handling. |
| Provider router | Resume a saved session or fairly rotate healthy providers, with local availability cooldowns. |
| Collaboration executor | Invoke the local CLI with isolated provider configuration and constrained permissions. |
| Outcome evaluator | Validate real files and commands; restore invalid or out-of-scope changes. |
| Capability probe | Test fresh-session tools when file creation is required or capability data is stale. |
| Topic/session registry | Record topic bindings, forks, active/archived status, and output references. |
| Independent reviewer | Request one bounded critique from a provider other than the executor. |
| Metrics recorder | Store routing metadata without storing prompts, tokens, or file contents. |
| Harness adapter | Normalize each CLI's invocation, session identity, permission denial, output, and failure semantics without mixing harnesses. |

## Headless CLI reference baseline and roadmap

[The reference baseline](docs/headless-cli-references/README.md) preserves the official Claude Code and Antigravity headless pages used to design this project. It is important engineering input, not proof that an option is installed, enabled, or safe; check the official page and local CLI help before relying on a version-sensitive flag.

Claude Code's native JSON Schema adapter, the shared state boundary, and Antigravity's explicit read-only adapter are implemented with local fake tests and macOS/Windows real smoke evidence. A configured Antigravity profile whose current non-secret fingerprint is trusted may run the minimal real smoke directly; only a genuine web login, MFA, or similar physical interaction requires the operator. Antigravity is not a third Claude Code provider and is not in the current automatic DeepSeek/MiMo rotation. It is only eligible for an explicitly requested independent review, second proposal, counterargument, or risk list that is also new, no-history, non-sensitive, and read-only; a new topic alone never selects it. Its full-auto isolated execute experiment did not modify the declared target even with the write tool available, so ordinary collaboration and all automatic project edits remain Claude Code's role.

## Quick Start after Fork

Prerequisites for the current path: Python 3.10+ and a working local Claude Code CLI. Antigravity is optional and only needed for its explicit read-only independent-review role. Clone or fork the repository, then initialize only local runtime files:

```bash
# macOS / Linux
python3 .agents/skills/external-agent-collaboration/scripts/bootstrap.py --init

# Windows PowerShell or Command Prompt
py -3 .agents/skills/external-agent-collaboration/scripts/bootstrap.py --init
```

This creates runtime directories and ensures a sync-safe `.ai-collaboration/providers.shared.json` exists. The shared file contains only provider definitions without tokens, home-relative configuration directories, and logical launchers; it never reads, prints, or sends credentials.

Edit the shared profile, then maintain `.ai-collaboration/providers.local.macos.json` and `.ai-collaboration/providers.local.windows.json` separately. Each platform file may directly contain that platform's `auth_token`, launcher, and isolated `CLAUDE_CONFIG_DIR`. These files are Git-ignored; your private synchronization mechanism decides whether to synchronize them. This project does not require environment variables, macOS Keychain, or Windows Credential Manager. Then verify a configured provider without printing its secret:

```bash
# macOS / Linux
python3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider <provider-key> --json

# Windows PowerShell or Command Prompt
py -3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider <provider-key> --json
```

Passing the diagnostic is not a host-platform egress approval. During an authorized implementation, Codex records the current non-secret local fingerprint before the provider's first call:

```bash
python3 .agents/skills/external-agent-collaboration/scripts/trust_provider.py --provider <provider-key> --approve
```

Changing endpoint, model mappings, configuration directory, or non-secret environment invalidates the record; Codex refreshes it during the next authorized implementation. The command neither reads nor prints credentials, and cannot bypass the host platform's final egress approval.

Direct tokens in configuration files are the supported default. A legacy shared `providers.local.json` remains supported; when platform paths differ, place the relevant profiles in `providers.local.macos.json` or `providers.local.windows.json`. Do not run a tool that moves tokens into environment variables or OS credential stores unless the user explicitly changes this policy.

Use `bootstrap.py --check` to verify only file and directory setup. It deliberately does not validate credential values.

## Suggested workflow

1. Read the local project context, current state, and recorded decisions.
2. Write a small, non-sensitive handoff instead of copying an entire chat transcript.
3. Classify the task and stop if its content is sensitive or prohibited for delegation.
4. Select an existing exact session, a user-named provider, or fairly rotate among healthy providers with the persistent local cursor.
5. For file edits, declare the smallest allowed paths and one or more machine-checkable expected outcomes.
6. Run the external collaborator through an isolated local profile.
7. Inspect the generated result, changed paths, outcomes, and required validation results in Codex.
8. For high-risk work, request at most one independent read-only critique.
9. Update anonymized quality and adoption metadata only after there is real evidence.

## Important precautions

- Never send API tokens, `.env` contents, passwords, private keys, customer exports, production data, or unrelated private files to an external provider.
- Do not use an external collaborator for live web facts, connected-account data, deployment, publishing, Git history rewriting, global package installation, or destructive infrastructure work.
- Do not switch a global provider setting while handling a task. Each provider should have an isolated local profile and configuration directory.
- Do not infer success from a transcript. Verify files and commands independently.
- Do not assume that a successful fresh-session capability probe changes an old session's tool availability.
- Keep logs and metrics minimal: store operational metadata, not prompts, secrets, or business content.
- Treat a provider failure as bounded. Only classified availability failures may make one automatic call to another healthy provider; outcome failures, bad implementations, and scope violations never trigger a provider switch.

## Configuration model

Version-controlled shared profiles must not contain tokens, absolute user directories, platform-specific launcher paths, session transcripts, capability-lab artifacts, or generated private logs. Provider tokens may be stored directly in Git-ignored platform-local profiles; the user decides whether a private synchronization mechanism carries those files. In every case, tokens must not enter handoffs, outputs, logs, test fixtures, or external prompts.

Each profile should supply only what the local CLI needs: an isolated configuration directory, launcher, CC Switch/Claude Code environment model mappings, non-secret environment settings, and local-only authentication. The runner deliberately does not pass `--model`, so it does not override provider-internal FABLE/OPUS/SONNET/HAIKU/SUBAGENT mappings or route Flash/Base/Pro across providers. Credentials are injected only into the child-process environment, never into a handoff or output record.

## How to contribute

When the workflow is implemented or changed, update the Skill instructions, tests, design documents, and this README together. New behavior should be demonstrated by local regression tests before it is treated as reliable. Every change records macOS and Windows impact and validates both platforms, or gives a concrete not-affected rationale. Real provider checks should use minimal, non-sensitive tasks and be run deliberately because they consume the configured service.

## Status

The project-local implementation, its tests, design documents, and bilingual README are included in this repository. Provider credentials and runtime collaboration data deliberately remain local and Git-ignored.

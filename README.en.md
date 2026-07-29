# External Agent Collaboration

[中文说明](README.zh.md) · [Project index](README.md)

## Purpose

This repository documents and hosts a project-local workflow for coordinating persistent external coding collaborators from Codex. The intended collaborators are MiMo and DeepSeek, reached through the local Claude Code CLI. Codex remains the person-facing coordinator: it receives the request, decides whether delegation is worthwhile, checks the result, and reports back.

The project exists because a simple one-off model call is not enough for longer local work. A useful collaboration setup needs to keep providers and sessions separate, retain project context, constrain file edits, and verify what actually changed.

This is not a claim that one model is always better than another. Provider choice should follow local evidence from comparable tasks.

## Functional requirements

The workflow is designed to provide the following behavior.

1. **One entry point.** Users work with Codex. External collaborators are invited only when they add value, such as large local context, a bounded implementation task, or an independent review.
2. **Separate persistent sessions.** A session is bound to a topic, provider, model profile, and working directory. Recovery uses a saved session ID, never an ambiguous “latest session” option.
3. **Task-aware delegation.** Before a call, classify the request by task type, work mode, risk, context size, and required tools. Small requests stay with Codex; current information, connected services, images, spreadsheets, presentations, PDFs, and final formatted office files use native Codex tools.
4. **Evidence-based routing.** New topics start with balanced provider rotation. Later, local results for the same task type and mode can inform routing using quality, completion, duration, cost, tool refusal, rework, and adoption metadata.
5. **Bounded external edits.** An implementation handoff must state the allowed paths, forbidden paths, allowed commands, acceptance checks, and expected output.
6. **Machine-checked completion.** A model saying “done” is not success. Expected outcomes may require a file to exist, contain exact text, satisfy a limited JSON Schema, change a bounded number of paths, or pass an explicitly approved validation command.
7. **Capability-aware file creation.** A fresh session's ability to use `Write` is measured separately from an older resumed session's initial tool set. When a resumed session lacks a needed tool, the preferred resolution is a tracked fork; an exact shell fallback is a last resort.
8. **One-pass independent review.** A high-risk execution may receive one read-only critique from the other provider. The reviewer does not automatically re-invoke the executor, so there is no debate loop.
9. **Durable local state.** Project context, decisions, handoffs, outputs, session records, capability records, routing metrics, and archives live in a local collaboration directory rather than only in chat history.

## Planned implementation

The project-local Skill is intended to include these parts:

| Part | Responsibility |
| --- | --- |
| Task classifier | Decide direct, native-Codex, external, or prohibited handling. |
| Provider router | Select a provider from saved session continuity or anonymized local results. |
| Collaboration executor | Invoke the local CLI with isolated provider configuration and constrained permissions. |
| Outcome evaluator | Validate real files and commands; restore invalid or out-of-scope changes. |
| Capability probe | Test fresh-session tools when file creation is required or capability data is stale. |
| Topic/session registry | Record topic bindings, forks, active/archived status, and output references. |
| Independent reviewer | Request one bounded critique from a provider other than the executor. |
| Metrics recorder | Store routing metadata without storing prompts, tokens, or file contents. |

## Suggested workflow

1. Read the local project context, current state, and recorded decisions.
2. Write a small, non-sensitive handoff instead of copying an entire chat transcript.
3. Classify the task and stop if its content is sensitive or prohibited for delegation.
4. Select an existing exact session, a user-named provider, or a provider selected by local routing data.
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
- Treat a provider failure as a bounded failure. A single deliberate fallback may be appropriate; repeated automatic retries are not.

## Configuration model

Provider credentials belong in a local, Git-ignored configuration file. The exact format is intentionally kept outside this public README. The repository must not contain tokens, endpoint credentials, session transcripts, capability-lab artifacts, or generated private logs.

Each profile should supply only what the local CLI needs: an isolated configuration directory, launcher, model mapping, non-secret environment settings, and local-only authentication. The runner should inject credentials only into the child process environment, never into the handoff or output record.

## How to contribute

When the workflow is implemented or changed, update the Skill instructions, tests, design documents, and this README together. New behavior should be demonstrated by local regression tests before it is treated as reliable. Real provider checks should use minimal, non-sensitive tasks and be run deliberately because they consume the configured service.

## Status

This repository currently contains the bilingual project description. The workflow above is the working design and acceptance target for the project-local implementation.

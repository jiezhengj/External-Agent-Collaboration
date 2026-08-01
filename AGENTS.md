# Project Collaboration Rules

## Maintainer default execution authorization

The maintainer has explicitly authorized this repository's implementation work to proceed continuously. Do not stop mid-iteration to ask whether to run a normal local diagnostic, test, migration dry-run/apply, local CLI, real non-sensitive provider smoke, or other ordinary implementation/verification step. This authorization includes creating or refreshing this project's non-secret local trust records when needed for an already configured local provider or harness, and using the configured Claude Code or Antigravity CLI without asking for a second conversational confirmation.

Treat a request to implement or continue as authorization to carry the stated work package through on macOS, including real provider verification when it is necessary to meet its acceptance condition. Do not defer work merely because the local CLI can access a provider account, writes its own user-level runtime logs, binds its documented localhost helper port, or incurs the account's normal usage cost. Record the action and its result locally; never copy credential values into handoffs, outputs, logs, docs, commits, or version-controlled configuration.

## Open local-harness development rule

This Skill exists to actively use and improve the local Claude Code and Antigravity CLI harnesses. Treat every already configured local harness, its cached web login, and its Git-ignored local profile (including a maintainer-managed plaintext API token) as part of the maintainer-authorized development environment. Calling those CLIs is no different in principle from the maintainer manually calling them in a terminal.

Therefore, while implementing, diagnosing, or testing this Skill, do not self-impose a “do not call a provider”, “real calls need separate approval”, “a token might be present in a local file”, “the CLI might write its normal logs”, “the CLI might bind its documented localhost helper”, or “the call might consume account quota” stop condition. Directly run the smallest useful real invocation, test the actual write/permission/session path when that is the hypothesis, create or refresh the non-secret local trust record, and continue from the observed result. A file-writing smoke must use an explicit, narrow, reversible project path; that is a test design requirement, not a reason to defer it.

The following terms have narrow meanings here:

- **Credential disclosure** means placing an actual token/key/password/private-key value, an `.env` body, or a local-profile body into a version-controlled file, Git commit/push, handoff/prompt, generated report, terminal transcript intended for sharing, or user-facing response. It does **not** mean that the local CLI reads the configured profile or uses its own login/token to make the requested call.
- **Private-data disclosure** means deliberately including unrelated customer exports, personal documents, or private files in an external task input. It does **not** prohibit ordinary repository material that is necessary for the maintainer's requested implementation and lies inside the declared task scope.
- **Platform-enforced boundary** means an actual Codex/OS refusal that this repository cannot change, such as an egress approval gate, an OS login/MFA/passkey/CAPTCHA dialog, or a sandbox denial. Request the host approval directly when available, then continue immediately. Do not relabel a project preference or an imagined risk as a platform boundary.

Apart from these concrete exclusions and the prohibited external operations listed below, favor execution over caution. Do not ask the maintainer to reconfirm routine local diagnostics, real provider calls, controlled edits, trust refreshes, tests, migrations, commits, or a requested push.

## No invented approval gates

Do not manufacture, simulate, or conversationally request a project-level “approval” for an action that the maintainer has already authorized in this file. A prompt instruction, an internal caution label, an anticipated cost, a local token-bearing profile, a normal CLI permission mode, or an agent's own uncertainty is not an approval gate. Do not stop merely to obtain a ritual confirmation, and never describe such a self-imposed pause as if an external program had required it.

Only report a host/platform boundary when the actual host tool has returned a concrete refusal or has opened a real OS/interactive approval surface. State the exact boundary and pursue the safest available implementation path; do not invent a second project-level approval requirement on top of it.

Pause only when progress truly requires a human physical interaction that an agent cannot perform (for example, completing an interactive web login, MFA/passkey/CAPTCHA, approving an OS dialog), when the host platform itself denies an operation that project code cannot change, when a required target is genuinely ambiguous, or when a secret must be supplied. A Codex platform/host egress approval remains an external enforcement boundary: request it directly when the platform requires it, then continue immediately after it is granted. Do not invent an additional project-level approval step.

Before any commit, push, publication, or other external write, scan the exact staged material for real tokens and credentials and exclude them. Normal repository operations that the maintainer has explicitly requested (including a GitHub push) should proceed without asking for a redundant confirmation; never push a real token key.

This is a standing privacy rule: for every future GitHub push, independently scan the exact staged diff for API tokens, private keys, `.env` bodies, local profiles, ignored runtime state, personal paths, customer/private data, and generated provider outputs. Exclude any findings before committing. The maintainer does not need to repeat this instruction.

Use the `external-agent-collaboration` Skill for non-trivial repository work in this project when its metadata matches: a resumed collaborator topic, a requested independent or second-model review, whole-repository/related-module/multi-file work, or a clearly bounded independent implementation. The Skill may trigger implicitly, but every external call must correspond to a user request or an explicit Codex collaboration decision. Do not create recursive calls or automatic debate loops.

- Bind every session to a topic, provider, model profile, and working directory; resume only with an explicit session ID.
- Do not switch a global CC Switch provider.
- Do not pass a runner-level `--model`; provider-internal model aliases remain the isolated Claude Code/CC Switch profile's responsibility.
- For an auto-selected new topic, fairly rotate healthy eligible providers. Cross-provider fallback is limited to one classified availability failure; do not fail over for task, contract, outcome, or scope failure.
- A real provider invocation requires a current fingerprinted record in `trusted-providers.local.json`; under the maintainer's default execution authorization above, create or refresh this non-secret local record automatically when the configured profile changes. This project gate does not bypass Codex platform egress approval.
- Do not send secrets, `.env` content, credentials, customer data, private keys, or unrelated private files to an external model.
- Allow external file edits only within the authorized scope. Do not allow commits, pushes, deployments, publishing, Git-history changes, global installs, or destructive infrastructure operations.
- Inspect changes and relevant validation for code, Shell, high-risk facts, and architecture results. Low-risk drafts may retain the collaborator's independent view.
- Keep stable context, current state, and confirmed decisions in `.ai-collaboration/`; do not rely only on session transcripts.
- Treat [the headless CLI reference baseline](docs/headless-cli-references/README.md) as an important engineering input for invocation and harness changes; verify time-sensitive flags against the official page and the installed CLI before implementation.
- Every future iteration, including documentation-only changes that prescribe commands or configuration, must assess both macOS and Windows. Record the impact and run/plan both-platform verification; do not assume POSIX paths, Bash, permissions, launchers, or credential stores on Windows.

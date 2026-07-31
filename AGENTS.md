# Project Collaboration Rules

## Maintainer default execution authorization

The maintainer has explicitly authorized this repository's implementation work to proceed continuously. Do not stop mid-iteration to ask whether to run a normal local diagnostic, test, migration dry-run/apply, local CLI, real non-sensitive provider smoke, or other ordinary implementation/verification step. This authorization includes creating or refreshing this project's non-secret local trust records when needed for an already configured local provider or harness, and using the configured Claude Code or Antigravity CLI without asking for a second conversational confirmation.

Treat a request to implement or continue as authorization to carry the stated work package through on macOS, including real provider verification when it is necessary to meet its acceptance condition. Do not defer work merely because the local CLI can access a provider account, writes its own user-level runtime logs, binds its documented localhost helper port, or incurs the account's normal usage cost. Record the action and its result locally; never copy credential values into handoffs, outputs, logs, docs, commits, or version-controlled configuration.

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

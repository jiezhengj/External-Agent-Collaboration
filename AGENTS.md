# Project Collaboration Rules

Use the `external-agent-collaboration` Skill for non-trivial repository work in this project when its metadata matches: a resumed collaborator topic, a requested independent or second-model review, whole-repository/related-module/multi-file work, or a clearly bounded independent implementation. The Skill may trigger implicitly, but every external call must correspond to a user request or an explicit Codex collaboration decision. Do not create recursive calls or automatic debate loops.

- Bind every session to a topic, provider, model profile, and working directory; resume only with an explicit session ID.
- Do not switch a global CC Switch provider.
- Do not pass a runner-level `--model`; provider-internal model aliases remain the isolated Claude Code/CC Switch profile's responsibility.
- For an auto-selected new topic, fairly rotate healthy eligible providers. Cross-provider fallback is limited to one classified availability failure; do not fail over for task, contract, outcome, or scope failure.
- A real provider invocation requires a current user-approved record in `trusted-providers.local.json`; profile configuration changes invalidate that record. This project gate does not bypass Codex platform egress approval.
- Do not send secrets, `.env` content, credentials, customer data, private keys, or unrelated private files to an external model.
- Allow external file edits only within the authorized scope. Do not allow commits, pushes, deployments, publishing, Git-history changes, global installs, or destructive infrastructure operations.
- Inspect changes and relevant validation for code, Shell, high-risk facts, and architecture results. Low-risk drafts may retain the collaborator's independent view.
- Keep stable context, current state, and confirmed decisions in `.ai-collaboration/`; do not rely only on session transcripts.

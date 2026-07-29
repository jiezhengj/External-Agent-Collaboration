# Task classification

## Selection comes first

When the Skill is globally discoverable, Codex uses the `description` in `SKILL.md` to decide whether to select it. That metadata should proactively match a resumed collaborator topic, an explicitly requested independent/second-model review, whole-repository or related-module work, multi-file work, or a clearly bounded independent implementation. It should not match simple questions, routine reviews, or small single-file changes.

`classify_task.py` does **not** control that initial Skill selection. After the Skill is selected, it is the guardrail that decides whether an external CLI call is allowed.

Before an allowed external collaboration, write the current request to a non-sensitive handoff file and run:

```text
python3 scripts/classify_task.py --request-file <file> --json
```

The result contains `task_type`, `mode`, `risk`, `context_size`, `tool_requirement`, `delegation`, `reason`, and `confidence`.

Treat it as a deterministic guardrail, not a replacement for judgment:

- `prohibited` always stops external delegation.
- `native_codex` selects the appropriate Codex web, connector, image, document, spreadsheet, presentation, or PDF path.
- `direct` means Codex should complete the request without an external CLI call.
- `external_agent` permits provider/session routing only after the rest of this Skill's safety checks.

If the classification conflicts with an explicit user instruction or clear project context, record the override and reason in the handoff.

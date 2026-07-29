# Task classification

Before external collaboration, write the current request to a non-sensitive handoff file and run:

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

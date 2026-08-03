# Expected outcomes

Pass `--expected-outcomes <project-relative-json-file>` for every `execute` action.

```json
{
  "outcomes": [
    {"type": "file_exists", "path": "docs/result.md"},
    {"type": "file_contains", "path": "docs/result.md", "text": "Approved"},
    {"type": "changed_paths", "min": 1, "max": 3},
    {"type": "command_succeeds", "argv": ["python3", "-c", "pass"]},
    {"type": "json_schema", "path": "outputs/result.json", "schema": {"type": "object", "required": ["status"]}}
  ]
}
```

Supported types:

- `file_exists`: target is a regular file.
- `file_contains`: target file contains `text`.
- `file_equals`: target file exactly equals `text`.
- `changed_paths`: number of changed files is within `min` and optional `max`.
- `command_succeeds`: prefer an `argv` array passed verbatim as `--validation-argv '<json-array>'`; it is executed without a shell and must exit 0. The legacy string `command` form remains available only when it exactly matches `--validation-command`.
- `json_schema`: validates a local JSON file with the supported subset: `type`, `const`, `enum`, `required`, `properties`, `additionalProperties`, `items`, `minItems`, `maxItems`, `minLength`, and `pattern`.

Use project-relative, non-sensitive paths. The executor restores the entire task change set when any expected outcome fails. Keep validation commands narrow and read-only where possible. Do not use platform-specific commands such as `true`, `touch`, or `chmod` in portable outcomes.

## Multi-run Goal usage

Expected outcomes are Run-level evidence. A successful outcome closes neither a persistent topic nor a Goal by itself. The [Goal contract example](goal-contract.example.json) wraps these entries with unique criterion IDs such as `artifact`, `macos-validation` and `windows-validation`, then aggregates the results across Runs.

For Goal aggregation:

- every required criterion must map to one or more supported outcomes, an explicit `user_acceptance`, or a required `review`;
- a missing, stale, failed or unknown outcome is not a pass;
- a platform criterion must be verified on that platform; one platform's result cannot substitute for another;
- a `not_applicable` criterion requires a recorded reason and evidence;
- `completed` means only that this Run passed its declared outcomes, scope check and validation commands.

The current runner accepts the Run-level schema above. When `--goal-contract` is supplied, it also parses Goal criteria and aggregates Goal state into `.ai-collaboration/goals/<goal_id>.json`. `--topic-goal` and `--stop-rule` remain descriptive topic-state fields rather than machine-checked closure rules.

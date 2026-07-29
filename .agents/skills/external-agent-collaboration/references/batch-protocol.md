# Batch protocol

Use only for non-sensitive local text whose per-item output can be small, structured and sampled. Run `batch.py plan` first; it is a dry-run and makes no provider call. Keep every manifest, chunk, worker result and reducer output under ignored `.ai-collaboration/batches/<topic>/`.

## Plan

```bash
python3 scripts/batch.py plan \
  --input-root input/ \
  --output-dir .ai-collaboration/batches/<topic>/plan \
  --include '*.md' --schema-version v1 \
  --max-files 25 --max-bytes 2097152 --sample-size 5
```

Review `sample.jsonl` and `plan.json` before expanding work. A worker receives exactly one `chunks/batch-XXXX.jsonl`; it must not return source bodies.

## Worker result JSONL

Each line must preserve `key`, `source_relative_path`, `source_hash`, and `schema_version` from its manifest record, then add:

```json
{"key":"…","source_relative_path":"docs/a.md","source_hash":"…","schema_version":"v1","status":"completed","conclusion":"short result","evidence_paths":["docs/a.md"],"confidence":0.8}
```

`status` is `completed`, `failed`, or `skipped`. Failed/skipped rows use a short `error_code`. Never copy source text, prompts, credentials or provider hidden reasoning into JSONL.

## Reduce and resume

```bash
python3 scripts/batch.py reduce \
  --manifest .ai-collaboration/batches/<topic>/plan/manifest.jsonl \
  --results-dir .ai-collaboration/batches/<topic>/results \
  --output-dir .ai-collaboration/batches/<topic>/reduced \
  --sample-size 5
```

The reducer rejects unknown, duplicate or hash/schema-mismatched rows. `pending.jsonl` contains failed, skipped and unprocessed source records; unchanged completed hashes are not reprocessed. Review `summary.json`, `exceptions.jsonl` and `sample.jsonl` before scheduling more work.

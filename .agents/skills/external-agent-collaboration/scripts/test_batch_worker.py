#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("batch_worker.py")
spec = importlib.util.spec_from_file_location("batch_worker", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def main():
    source = {"key": "k", "source_relative_path": "docs/a.md", "source_hash": "h", "schema_version": "v1", "size_bytes": 1, "media_type": ".md"}
    good = {**source, "status": "completed", "conclusion": "ok", "evidence_paths": ["docs/a.md"], "confidence": 0.8}
    assert module.parse_records({"result": json.dumps({"records": [good]})}, [source]) == [good]
    assert module.parse_records({"result": "```json\n" + json.dumps({"records": [good]}) + "\n```"}, [source]) == [good]
    missing = module.parse_records({"result": "{}"}, [source])
    assert missing[0]["error_code"] == "worker_missing_record"
    assert "Do not edit files" in module.prompt([source])

    config = {
        "schema_version": 1,
        "default": {"strategy": "fair_round_robin"},
        "task_overrides": {"data:analyze": {"strategy": "fixed", "provider": "provider_b"}},
    }
    metrics = module.valid_metrics({"events": []})
    provider, route = module.select_provider("auto", ["provider_a", "provider_b"], metrics, config)
    assert provider == "provider_b" and route["basis"] == "configured_fixed"
    provider, route = module.select_provider("provider_a", ["provider_a", "provider_b"], metrics, config)
    assert provider == "provider_a" and route["basis"] == "user_specified"
    print("batch-worker tests passed")


if __name__ == "__main__":
    main()

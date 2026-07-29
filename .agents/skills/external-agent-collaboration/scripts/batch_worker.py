#!/usr/bin/env python3
"""Run one manifest chunk through a read-only external provider and write local JSONL."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
import batch
import collaborate
from provider_routing import choose_provider, valid_metrics


def prompt(records: list[dict[str, Any]]) -> str:
    return """Read only the exact non-sensitive source paths listed below. Do not edit files or run shell commands. Return exactly one JSON object with key records. Each record must preserve key, source_relative_path, source_hash, schema_version and add status (completed|failed|skipped), a short conclusion, evidence_paths, confidence (0..1), and optional error_code. Never include source text, credentials, prompts, or hidden reasoning.\n\nManifest chunk:\n""" + json.dumps(records, ensure_ascii=False)


def parse_records(result: dict[str, Any], expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw=result.get("result")
    if isinstance(raw, str):
        stripped=raw.strip()
        if stripped.startswith("```json") and stripped.endswith("```"):
            raw=stripped[7:-3].strip()
    try: value=json.loads(raw) if isinstance(raw,str) else None
    except json.JSONDecodeError: value=None
    supplied=value.get("records") if isinstance(value,dict) else None
    items=supplied if isinstance(supplied,list) else []
    by_key={item.get("key"):item for item in items if isinstance(item,dict) and isinstance(item.get("key"),str)}
    out=[]
    for source in expected:
        item=by_key.get(source["key"])
        if item is None:
            out.append({**source,"status":"failed","error_code":"worker_missing_record"})
            continue
        reason=batch.validate_result(item,source)
        if reason: out.append({**source,"status":"failed","error_code":reason})
        else: out.append(item)
    return out


def run(args: argparse.Namespace) -> int:
    chunk=Path(args.chunk).resolve(); output=Path(args.output).resolve()
    batch.rel(chunk); batch.rel(output); batch.local_control_path(chunk); batch.local_control_path(output)
    records=batch.read_jsonl(chunk)
    if not records: raise batch.BatchError("Batch chunk is empty.")
    available=collaborate.profiles()
    if args.provider=="auto":
        ready=sorted(key for key,value in available.items() if collaborate.profile_problem(value) is None)
        provider,route=choose_provider(valid_metrics(collaborate.load_json(collaborate.METRICS_FILE,{"events":[]})),ready,"data","analyze")
    else: provider,route=args.provider,{"basis":"user_specified"}
    profile=available.get(provider)
    if not profile or collaborate.profile_problem(profile): raise batch.BatchError("Configured provider is not ready.")
    code,stdout,stderr=collaborate.invoke(profile,"consult",prompt(records),collaborate.PROJECT_ROOT,None,True,False,[],args.timeout)
    if code: raise batch.BatchError(f"Read-only worker failed: {stderr[-400:]}")
    result=collaborate.parse_result(stdout)
    if args.debug_output:
        debug=Path(args.debug_output).resolve(); batch.rel(debug); batch.local_control_path(debug)
        collaborate.write_json(debug, {"result": result, "stderr": stderr[-2000:]})
    batch.write_jsonl(output,parse_records(result,records))
    print(json.dumps({"status":"completed","provider":provider,"route":route,"output":batch.rel(output),"records":len(records)},ensure_ascii=False))
    return 0

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--chunk",required=True);p.add_argument("--output",required=True);p.add_argument("--provider",default="auto");p.add_argument("--timeout",type=int,default=1200);p.add_argument("--debug-output");a=p.parse_args()
 try:return run(a)
 except (batch.BatchError,collaborate.CollaborationError) as e: print(str(e),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

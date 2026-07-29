#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
S=Path(__file__).with_name("batch_worker.py");sp=importlib.util.spec_from_file_location("batch_worker",S);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def main():
 source={"key":"k","source_relative_path":"docs/a.md","source_hash":"h","schema_version":"v1","size_bytes":1,"media_type":".md"}
 good={**source,"status":"completed","conclusion":"ok","evidence_paths":["docs/a.md"],"confidence":0.8}
 assert m.parse_records({"result":json.dumps({"records":[good]})},[source])==[good]
 assert m.parse_records({"result":"```json\n"+json.dumps({"records":[good]})+"\n```"},[source])==[good]
 missing=m.parse_records({"result":"{}"},[source]);assert missing[0]["error_code"]=="worker_missing_record"
 assert "Do not edit files" in m.prompt([source])
 print("batch-worker tests passed")
if __name__=="__main__":main()

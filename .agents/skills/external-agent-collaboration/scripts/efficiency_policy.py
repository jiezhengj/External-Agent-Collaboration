#!/usr/bin/env python3
"""Choose a conservative collaboration policy from non-sensitive efficiency metadata."""
from __future__ import annotations
import argparse,json
from typing import Any

def recommend(files:int, input_bytes:int, estimated_return_bytes:int, risk:str, verifiable:bool, metrics:list[dict[str,Any]])->dict[str,Any]:
 ratio=estimated_return_bytes/max(input_bytes,1)
 failures=[e for e in metrics if e.get("status")!="completed"]
 quality=[float(e["quality_score"]) for e in metrics if isinstance(e.get("quality_score"),(int,float))]
 cost=[float(e["cost_usd"]) for e in metrics if isinstance(e.get("cost_usd"),(int,float))]
 guard= risk in {"high","prohibited"} or not verifiable or (len(metrics)>=3 and len(failures)/len(metrics)>0.25) or (quality and sum(quality)/len(quality)<3.0)
 if risk=="prohibited": policy="reject"
 elif guard: policy="direct" if risk!="high" else "external_review"
 elif files>=10 and input_bytes>=1024*1024 and ratio<=.2: policy="batch"
 elif input_bytes>=200000 and ratio<=.2: policy="delegate"
 else: policy="direct"
 return {"token_policy":policy,"recommended_return_mode":"file_only" if policy=="batch" else "compact","return_ratio":round(ratio,4),"review_policy":"exception" if policy=="batch" else "sample" if policy in {"delegate","external_review"} else "none","max_retries":0 if guard else 1,"guardrail_triggered":guard,"observed_events":len(metrics),"average_quality":round(sum(quality)/len(quality),3) if quality else None,"average_cost_usd":round(sum(cost)/len(cost),6) if cost else None}
def main():
 p=argparse.ArgumentParser();p.add_argument('--files',type=int,required=True);p.add_argument('--input-bytes',type=int,required=True);p.add_argument('--estimated-return-bytes',type=int,required=True);p.add_argument('--risk',default='low');p.add_argument('--verifiable',action='store_true');p.add_argument('--metrics-file');a=p.parse_args();m=[]
 if a.metrics_file:m=json.loads(open(a.metrics_file).read()).get('events',[])
 print(json.dumps(recommend(a.files,a.input_bytes,a.estimated_return_bytes,a.risk,a.verifiable,m),ensure_ascii=False))
if __name__=='__main__':main()

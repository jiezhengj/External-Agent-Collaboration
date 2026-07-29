#!/usr/bin/env python3
"""Prune expired ignored runtime files and report conservative-mode health signals."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]; CONTROL=ROOT/'.ai-collaboration'
def main():
 p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=30);p.add_argument('--apply',action='store_true');a=p.parse_args();cut=time.time()-a.days*86400; candidates=[]
 for name in ('handoffs','outputs','logs','snapshots','reviews','batches'):
  d=CONTROL/name
  if d.exists(): candidates += [x for x in d.rglob('*') if x.is_file() and x.stat().st_mtime<cut]
 removed=[]
 if a.apply:
  for x in candidates:x.unlink();removed.append(str(x.relative_to(ROOT)))
 metrics=json.loads((CONTROL/'provider-metrics.json').read_text()) if (CONTROL/'provider-metrics.json').exists() else {'events':[]}
 ev=metrics.get('events',[]); recent=ev[-20:]; failed=sum(x.get('status')!='completed' for x in recent); quality=[x['quality_score'] for x in recent if isinstance(x.get('quality_score'),(int,float))]
 print(json.dumps({'expired_candidates':len(candidates),'removed':removed,'conservative_mode':bool(recent and (failed/len(recent)>.25 or quality and sum(quality)/len(quality)<3))},ensure_ascii=False))
if __name__=='__main__':main()

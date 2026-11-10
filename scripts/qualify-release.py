"""Evaluate M7 evidence; exit 2 means release is blocked. Does not publish anything."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from pm_copilot.build_identity import source_identity
from pm_copilot.release_policy import qualify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('portable','dependencies','target','windows','review','installer','output'):
        parser.add_argument('--'+name,type=Path,required=name=='output')
    args=parser.parse_args(); evidence={}; errors=[]
    for name in ('portable','dependencies','target','windows','review'):
        path=getattr(args,name)
        if path:
            try:
                value=json.loads(path.read_text())
                if not isinstance(value,dict):raise ValueError('Expected object')
                evidence[name]=value
            except (OSError,ValueError) as exc:errors.append({'evidence':name,'error':type(exc).__name__})
    report=qualify(source_identity(),**evidence,installer=args.installer)
    report['timestamp_utc']=datetime.now(timezone.utc).isoformat();report['evidence_errors']=errors
    if errors:report['release_ready']=False
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    for gate in report['gates']:print(gate['status']+': '+gate['id'])
    return 0 if report['release_ready'] else 2


if __name__=='__main__':raise SystemExit(main())

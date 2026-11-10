"""Launch an actual frozen backend away from the checkout. No real model qualification."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backend',type=Path,required=True);parser.add_argument('--web',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-diarization',action='store_true')
    args=parser.parse_args();backend=args.backend.resolve();web=args.web.resolve();token=secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix='pm-bundled-smoke-') as data:
        process=subprocess.Popen([str(backend)],cwd=data,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            process.stdin.write((json.dumps(dict(database=str(Path(data)/'copilot.sqlite3'),token=token,web_dir=str(web)))+'\n').encode());process.stdin.flush()
            line=process.stdout.readline();ready=json.loads(line);assert ready['type']=='ready'
            origin=ready['origin']
            def request(route,method='GET',value=None,raw=None):
                body=raw if raw is not None else json.dumps(value).encode() if value is not None else None
                req=urllib.request.Request(origin+'/api/'+route,data=body,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream' if raw is not None else 'application/json'})
                with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
            diagnostic=request('setup/diagnostics');assert diagnostic['bundled'] is True
            p=request('projects','POST',{'name':'Packaged smoke'})['projects'][0]['id'];request('projects/'+p+'/select','POST')
            doc=request('projects/'+p+'/documents?filename=offline.txt','POST',raw=b'The bundled release is Friday.')
            for _ in range(100):
                documents=request('projects/'+p+'/documents')['documents']
                if documents[0]['chunk_count']:break
                time.sleep(.1)
            assert documents[0]['chunk_count']>0,documents
            found=request('projects/'+p+'/knowledge/search','POST',{'query':'release','mode':'lexical'})
            assert found['hits'][0]['citation']['quote']=='The bundled release is Friday.'
            job=request('setup/self-test','POST')
            for _ in range(300):
                status=request('setup');row=next(r for r in status['runs'] if r['id']==job['id'])
                if row['status']!='running':break
                time.sleep(.2)
            assert row['status']=='completed',row
            checks={c['id']:c for c in row['report']['checks']}
            for name in ['storage','local_rag','question_guard','parser_worker','import_faster_whisper','import_ctranslate2','import_onnxruntime']:
                assert checks[name]['status']=='passed',(name,checks[name])
            if args.require_diarization:assert checks['import_pyannote.audio']['status']=='passed'
            assert checks['asr_runtime']['status']=='blocked' and row['report']['all_passed'] is False
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(dict(bundled_backend_started=True,checkout_independent=True,actual_bundled_parser_worker=True,document_ingestion_and_citations=True,offline_core_checks='passed',missing_assets='correctly blocked',real_models='unrun',platform=os.name),indent=2)+'\n')
        finally:
            process.stdin.close()
            try:process.wait(timeout=20)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise AssertionError('Bundled backend did not stop on parent EOF')
            assert process.returncode==0,process.returncode
    print('Bundled backend, child worker, source citations and shutdown smoke passed.')

if __name__=='__main__':main()

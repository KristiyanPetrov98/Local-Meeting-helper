"""Bounded offline runtime imports, never a downloader or media recorder."""
import importlib
import json
import os
import sys

def main():
    protocol=sys.stdout;sys.stdout=sys.stderr
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYANNOTE_METRICS_ENABLED='0')
    cfg=json.loads(sys.stdin.readline());results={}
    for name in cfg.get('modules',[]):
        if name not in ('faster_whisper','pyannote.audio','onnxruntime','ctranslate2'):return 2
        try:
            module=importlib.import_module(name)
            if name=='onnxruntime':module.disable_telemetry_events()
            results[name]='passed'
        except Exception:results[name]='blocked'
    print(json.dumps({'type':'checks','results':results}),file=protocol,flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())

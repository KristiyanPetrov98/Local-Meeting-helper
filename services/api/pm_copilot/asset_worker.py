"""Explicit setup-only installation worker; credentials never appear in arguments/logs."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from .model_assets import CATALOG,install_snapshot,verify_snapshot


def main():
    os.environ.update(HF_HUB_DISABLE_TELEMETRY='1',HF_HUB_DISABLE_PROGRESS_BARS='1',PYANNOTE_METRICS_ENABLED='0')
    protocol=sys.stdout
    cfg=json.loads(sys.stdin.readline());sys.stdout=sys.stderr
    try:
        model_id=cfg['model_id'];model=CATALOG[model_id];destination=Path(cfg['destination'])
        if cfg['action']=='verify':result=verify_snapshot(model_id,destination)
        elif cfg['action']=='import':result=install_snapshot(model_id,cfg['source'],destination,replace=cfg.get('replace',False))
        else:
            from huggingface_hub import HfApi,snapshot_download
            token=cfg.get('access_token') or False
            revision=HfApi(token=token).model_info(model['repository']).sha
            destination.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='snapshot-',dir=cfg['temporary_root']) as stage:
                snapshot=Path(stage)/'snapshot'
                snapshot_download(repo_id=model['repository'],revision=revision,token=token,local_dir=snapshot,max_workers=2,
                    allow_patterns=['*.bin','*.json','*.txt','*.yaml','*.yml','*.safetensors','*.npz','*.model'])
                result=install_snapshot(model_id,snapshot,destination,revision,replace=cfg.get('replace',False),provenance='approved repository, immutable downloaded revision')
        print(json.dumps({'type':'installed','result':result}),file=protocol,flush=True)
        return 0
    except Exception:
        print(json.dumps({'type':'error','code':'model_install_failed','detail':'Model installation/integrity check failed. Check official access, network, disk space and snapshot completeness.'}),file=protocol,flush=True)
        return 2

if __name__=='__main__':raise SystemExit(main())

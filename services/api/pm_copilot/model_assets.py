"""Fixed model catalog and bounded managed snapshots; no executable model code."""
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

CATALOG={
 'generation':dict(label='Qwen3-VL 8B Q4_K_M',kind='ollama',name='qwen3-vl:8b-instruct-q4_K_M',license_url='https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct',gated=False),
 'embedding':dict(label='Qwen3 embedding 0.6B',kind='ollama',name='qwen3-embedding:0.6b',license_url='https://huggingface.co/Qwen/Qwen3-Embedding-0.6B',gated=False),
 **{f'whisper-{size}':dict(label=f'Multilingual Whisper {size}',kind='snapshot',repository='Systran/faster-whisper-'+size,license_url='https://huggingface.co/Systran/faster-whisper-'+size,gated=False) for size in ('medium','small','tiny')},
 'community-1':dict(label='Community-1 CPU diarization',kind='snapshot',repository='pyannote/speaker-diarization-community-1',license_url='https://huggingface.co/pyannote/speaker-diarization-community-1',gated=True),
}
MAX_BYTES=12*1024**3
ALLOWED_SUFFIXES={'.bin','.json','.txt','.yaml','.yml','.safetensors','.npz','.model'}


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def files(root):
    if root.is_symlink() or not root.is_dir():raise ValueError('Choose a real snapshot directory')
    result=[];total=0
    for current,dirs,names in os.walk(root,followlinks=False):
        for name in [*dirs,*names]:
            if (Path(current)/name).is_symlink():raise ValueError('Snapshot symlinks are not allowed')
        dirs[:]=[name for name in dirs if not name.startswith('.')]
        for name in names:
            path=Path(current)/name
            if name=='installation.json' or name.startswith('.'):continue
            if path.suffix.lower() not in ALLOWED_SUFFIXES:continue
            total+=path.stat().st_size;result.append(path)
            if total>MAX_BYTES or len(result)>1000:raise ValueError('Model snapshot exceeds its bounded installation limit')
    return result


def validate_snapshot(model_id,root):
    paths=files(root);relative={p.relative_to(root).as_posix():p for p in paths}
    if model_id.startswith('whisper-'):
        if not {'model.bin','config.json','tokenizer.json'}<=relative.keys():raise ValueError('Whisper needs model.bin, config.json and tokenizer.json')
        for name in ('config.json','tokenizer.json'):
            if relative[name].stat().st_size>30*1024**2:raise ValueError('Model metadata is oversized')
            json.loads(relative[name].read_text('utf-8'))
    elif model_id=='community-1':
        import yaml
        if 'config.yaml' not in relative or not any(name.endswith(('.bin','.safetensors')) for name in relative):raise ValueError('Community-1 needs its complete offline config and weights')
        if relative['config.yaml'].stat().st_size>1024**2:raise ValueError('Pipeline config is oversized')
        config=yaml.safe_load(relative['config.yaml'].read_text('utf-8'))
        if config.get('pipeline',{}).get('name')!='pyannote.audio.pipelines.SpeakerDiarization':raise ValueError('Only the approved Community-1 pipeline is supported')
        for key in ('segmentation','embedding'):
            entry=config['pipeline'].get('params',{}).get(key)
            if not isinstance(entry,str) or entry not in relative:raise ValueError('Community-1 config must reference included local segmentation and embedding files')
    else:raise ValueError('Only approved local snapshot models can be imported')
    return paths


def install_snapshot(model_id,source,destination,revision=None,replace=False,provenance='user-attested approved snapshot'):
    source,destination=Path(source),Path(destination)
    if destination.exists() and not replace:raise ValueError('Model already exists; explicitly choose replacement to change it')
    selected=validate_snapshot(model_id,source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=destination.with_name(destination.name+'.installing')
    backup=destination.with_name(destination.name+'.previous')
    if staging.exists():shutil.rmtree(staging)
    staging.mkdir();hashes={}
    try:
        for path in selected:
            relative=path.relative_to(source);target=staging/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target);hashes[relative.as_posix()]=digest(target)
        metadata=dict(model_id=model_id,repository=CATALOG[model_id]['repository'],revision=revision,sha256=hashes,provenance=provenance,license_acknowledged=True)
        (staging/'installation.json').write_text(json.dumps(metadata,indent=2),'utf-8')
        if backup.exists():shutil.rmtree(backup)
        if destination.exists():destination.rename(backup)
        try:staging.rename(destination)
        except BaseException:
            if backup.exists():backup.rename(destination)
            raise
        if backup.exists():shutil.rmtree(backup)
        return metadata
    finally:
        if staging.exists():shutil.rmtree(staging)


def verify_snapshot(model_id,root):
    validate_snapshot(model_id,root)
    manifest=root/'installation.json'
    if not manifest.is_file() or manifest.stat().st_size>1024**2:raise ValueError('No bounded installation manifest is present')
    metadata=json.loads(manifest.read_text('utf-8'))
    if metadata.get('repository')!=CATALOG[model_id]['repository']:raise ValueError('Snapshot repository identity differs from the approved model')
    expected=metadata.get('sha256',{})
    if not expected or len(expected)>1000:raise ValueError('No valid model checksums')
    for relative,checksum in expected.items():
        part=Path(relative)
        if part.is_absolute() or '..' in part.parts or not re.fullmatch('[0-9a-f]{64}',checksum):raise ValueError('Invalid managed snapshot manifest')
        path=root/part
        if not path.is_file() or path.is_symlink() or digest(path)!=checksum:raise ValueError('Model files failed local integrity verification')
    if set(expected)!={p.relative_to(root).as_posix() for p in files(root)}:raise ValueError('Model file inventory differs from its manifest')
    return metadata


def recover_installations(root):
    """Recover only reserved managed names after a crash; never follow links."""
    from uuid import UUID
    root=Path(root)
    for model_id,value in CATALOG.items():
        if value['kind']!='snapshot':continue
        target=root/model_id;backup=root/(model_id+'.previous');staging=root/(model_id+'.installing')
        if backup.is_dir() and not backup.is_symlink() and not target.exists():backup.rename(target)
        if staging.is_dir() and not staging.is_symlink():shutil.rmtree(staging)
    downloads=root/'.downloads'
    if downloads.is_dir() and not downloads.is_symlink():
        for entry in downloads.iterdir():
            try:UUID(entry.name)
            except ValueError:continue
            if entry.is_dir() and not entry.is_symlink():shutil.rmtree(entry)

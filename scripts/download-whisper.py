"""Explicit one-time installation command; never called during a meeting."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=['medium','small','tiny'],default='medium')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    from huggingface_hub import HfApi, snapshot_download
    repo='Systran/faster-whisper-'+args.model
    revision=HfApi().model_info(repo).sha
    output=args.output or Path('models/runtime/whisper-'+args.model)
    snapshot_download(repo_id=repo,revision=revision,local_dir=output,
        allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])
    entries={}
    for path in output.iterdir():
        if path.is_file():
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
            entries[path.name]=digest.hexdigest()
    (output/'installation.json').write_text(json.dumps({'repository':repo,'revision':revision,'sha256':entries},indent=2))
    print('Local model installed. Review license and retain installation.json with the model.')

if __name__=='__main__':main()

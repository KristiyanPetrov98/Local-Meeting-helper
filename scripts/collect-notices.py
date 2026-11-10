"""Build-time inventory and license text collection; never includes model snapshots."""
import argparse
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from pm_copilot.build_identity import source_identity

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('build/notices'));args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);packages=[]
    for distribution in metadata.distributions():
        name=distribution.metadata['Name'];files=[]
        for entry in distribution.files or []:
            value=str(entry).lower()
            if '.dist-info/' in value and any(part in value for part in ('license','copying','notice')):
                source=Path(distribution.locate_file(entry))
                if source.is_file():
                    target=args.output/'python'/name/Path(entry).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);files.append(target.relative_to(args.output).as_posix())
        packages.append(dict(name=name,version=distribution.version,license=distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),texts=files))
    modules=('faster_whisper','pyannote.audio','torch','torchaudio','torchcodec')
    present={}
    for name in modules:
        try:present[name]=bool(importlib.util.find_spec(name))
        except ModuleNotFoundError:present[name]=False
    manifest=dict(platform=sys.platform,python=platform.python_version(),fullModelRuntime=all(present.values()),runtime_modules_present=present,meeting_model_weights_included=False,small_runtime_vad='faster-whisper bundled Silero VAD, MIT; see included license',release_qualified=False,python_packages=packages)
    js_packages=[]
    package=json.loads(Path('package.json').read_text())
    for name in package.get('dependencies',{}):
        directory=Path('node_modules')/name
        info=json.loads((directory/'package.json').read_text());texts=[]
        for source in directory.glob('*'):
            if source.is_file() and source.name.upper().startswith(('LICENSE','LICENCE','COPYING','NOTICE')):
                target=args.output/'javascript'/name/source.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);texts.append(target.relative_to(args.output).as_posix())
        js_packages.append(dict(name=name,version=info['version'],license=info.get('license'),texts=texts))
    manifest['javascript_packages']=js_packages
    manifest['source_digest']=source_identity()
    (args.output/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for source in Path('packaging/licenses').glob('*'):shutil.copyfile(source,args.output/source.name)
    (args.output/'README.txt').write_text('Build-time third-party inventory and license texts. Meeting model weights are installed separately with user acknowledgement. This inventory does not substitute for M7 license/security/release review.\n')
    print('License inventory collected; full model runtime:',manifest['fullModelRuntime'])

if __name__=='__main__':main()

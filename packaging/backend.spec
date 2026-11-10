# Self-contained backend. Windows builds require all supported model libraries.
import importlib.util
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all,collect_submodules,copy_metadata
root=Path(SPECPATH).parent
import sys,json
sys.path.insert(0,str(root/'services/api'))
from pm_copilot.build_identity import source_identity
identity=root/'build/build-identity.json';identity.parent.mkdir(parents=True,exist_ok=True)
identity.write_text(json.dumps({'source_digest':source_identity(root)})+'\n')
windows=os.name=='nt'
data=[(str(identity),'.')];binaries=[];hidden=['pm_copilot.document_worker','pm_copilot.media_worker','pm_copilot.asset_worker','pm_copilot.check_worker']
if windows:
 ffmpeg=root/'build/runtime/ffmpeg'
 libraries=list((ffmpeg/'bin').glob('*.dll'))
 if not libraries or not (ffmpeg/'installation.json').is_file():raise SystemExit('Stage the verified shared FFmpeg runtime before freezing Windows.')
 binaries.extend((str(p),'ffmpeg') for p in libraries)
 data.append((str(ffmpeg/'installation.json'),'ffmpeg'))
packages=['fastapi','uvicorn','websockets','pydantic','pypdf','docx','pptx','openpyxl','yaml','defusedxml','numpy','PIL','langdetect','faster_whisper','ctranslate2','onnxruntime','tokenizers','huggingface_hub']
if windows:packages+=['torch','torchaudio','torchcodec','pyannote.audio']
for package in packages:
 if importlib.util.find_spec(package) is None:raise SystemExit('Missing required packaging dependency: '+package)
 d,b,h=collect_all(package);data+=d;binaries+=b;hidden+=h
for distribution in ['fastapi','uvicorn','pydantic','pypdf','python-docx','python-pptx','openpyxl','PyYAML','defusedxml','numpy','Pillow','langdetect','httpx','faster-whisper','ctranslate2','onnxruntime']+(['pyannote.audio','torch','torchaudio','torchcodec'] if windows else []):
 data+=copy_metadata(distribution)
# Exclude media fixtures and pretrained checkpoints; only the MIT runtime VAD asset is retained.
data=[entry for entry in data if Path(entry[0]).suffix.lower() not in {'.wav','.mp3','.mp4','.png','.jpg','.pt','.ckpt','.safetensors','.bin'} and (Path(entry[0]).suffix.lower()!='.onnx' or 'faster_whisper' in str(entry[0]) and 'silero_vad' in Path(entry[0]).name)]
a=Analysis([str(root/'packaging/backend-entry.py')],pathex=[str(root/'services/api')],binaries=binaries,datas=data,hiddenimports=hidden,excludes=['tkinter','matplotlib','IPython','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='pm-copilot-api',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='pm-copilot-api')

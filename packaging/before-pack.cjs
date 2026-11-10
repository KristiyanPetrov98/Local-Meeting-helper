const fs=require('node:fs');const path=require('node:path');
module.exports=async function(context){
 const root=context.packager.projectDir;const manifest=JSON.parse(fs.readFileSync(path.join(root,'build/notices/runtime-manifest.json'),'utf8'));
 if(context.electronPlatformName==='win32'){
  if(manifest.platform!=='win32'||!manifest.fullModelRuntime)throw new Error('A real Windows backend build with all runtime libraries is required.');
  const engineRoot=path.join(root,'build/runtime/ollama');
  const engineManifest=JSON.parse(fs.readFileSync(path.join(engineRoot,'installation.json'),'utf8'));
  const crypto=require('node:crypto');const engineHash=crypto.createHash('sha256').update(fs.readFileSync(path.join(engineRoot,'ollama.exe'))).digest('hex');
  if(engineManifest.repository!=='ollama/ollama'||!/^v\d+\.\d+\.\d+$/.test(engineManifest.version)||!/^[a-f0-9]{64}$/.test(engineManifest.archive_sha256)||engineHash!==engineManifest.executable_sha256)throw new Error('Verified official Ollama runtime required.');
  const vcRoot=path.join(root,'build/runtime/vcredist');const vc=JSON.parse(fs.readFileSync(path.join(vcRoot,'installation.json'),'utf8'));
  const vcHash=crypto.createHash('sha256').update(fs.readFileSync(path.join(vcRoot,'vc_redist.x64.exe'))).digest('hex');
  if(vc.publisher!=='Microsoft Corporation'||vc.signature_status!=='Valid'||vcHash!==vc.sha256)throw new Error('Validated Microsoft C++ runtime required.');
  const engineSmoke=JSON.parse(fs.readFileSync(path.join(root,'build/notices/engine-smoke.json'),'utf8'));
  if(engineSmoke.platform!=='win32'||engineSmoke.status!=='passed'||engineSmoke.owned_server_started!==true||engineSmoke.owned_server_stopped!==true||engineSmoke.version!==engineManifest.version.replace(/^v/,''))throw new Error('Actual Windows engine startup/shutdown smoke must pass.');
  for(const helper of ['audio','screen'])if(!fs.existsSync(path.join(root,'build/helpers',helper,'System.Private.CoreLib.dll')))throw new Error('Self-contained .NET helper required: '+helper);
  for(const relative of ['backend/pm-copilot-api/pm-copilot-api.exe','helpers/audio/PmCopilot.Capture.exe','helpers/screen/PmCopilot.Screen.exe','runtime/ollama/ollama.exe']){
   const data=fs.readFileSync(path.join(root,'build',relative));
   if(data.subarray(0,2).toString()!=='MZ')throw new Error('Windows executable missing: '+relative);
   const pe=data.readUInt32LE(0x3c);if(data.subarray(pe,pe+4).toString()!=='PE\0\0'||data.readUInt16LE(pe+4)!==0x8664)throw new Error('Windows x64 PE required: '+relative);
  }
 }
 if(!fs.existsSync(path.join(root,'apps/web/dist/index.html')))throw new Error('Production web build is missing.');
};

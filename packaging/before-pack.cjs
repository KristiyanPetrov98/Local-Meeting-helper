const fs=require('node:fs');const path=require('node:path');
module.exports=async function(context){
 const root=context.packager.projectDir;const manifest=JSON.parse(fs.readFileSync(path.join(root,'build/notices/runtime-manifest.json'),'utf8'));
 if(context.electronPlatformName==='win32'){
  if(manifest.platform!=='win32'||!manifest.fullModelRuntime)throw new Error('A real Windows backend build with all runtime libraries is required.');
  for(const helper of ['audio','screen'])if(!fs.existsSync(path.join(root,'build/helpers',helper,'System.Private.CoreLib.dll')))throw new Error('Self-contained .NET helper required: '+helper);
  for(const relative of ['backend/pm-copilot-api/pm-copilot-api.exe','helpers/audio/PmCopilot.Capture.exe','helpers/screen/PmCopilot.Screen.exe']){
   const data=fs.readFileSync(path.join(root,'build',relative));
   if(data.subarray(0,2).toString()!=='MZ')throw new Error('Windows executable missing: '+relative);
   const pe=data.readUInt32LE(0x3c);if(data.subarray(pe,pe+4).toString()!=='PE\0\0'||data.readUInt16LE(pe+4)!==0x8664)throw new Error('Windows x64 PE required: '+relative);
  }
 }
 if(!fs.existsSync(path.join(root,'apps/web/dist/index.html')))throw new Error('Production web build is missing.');
};

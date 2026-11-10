import path from 'node:path';
export function backendLocation(options:{packaged:boolean;resourcesPath:string;root:string;userData:string;platform:string;pythonOverride?:string}){
 const {packaged,resourcesPath,root,userData,platform}=options;
 if(packaged){
  const directory=path.join(resourcesPath,'backend','pm-copilot-api');
  return {command:path.join(directory,platform==='win32'?'pm-copilot-api.exe':'pm-copilot-api'),args:[] as string[],cwd:directory,webDir:path.join(resourcesPath,'web'),env:{PM_CAPTURE_HELPER:path.join(resourcesPath,'helpers','audio','PmCopilot.Capture.exe'),PM_SCREEN_HELPER:path.join(resourcesPath,'helpers','screen','PmCopilot.Screen.exe'),PM_APP_DATA:userData}};
 }
 return {command:options.pythonOverride??path.join(root,'.venv',platform==='win32'?'Scripts/python.exe':'bin/python'),args:['-m','pm_copilot'],cwd:path.join(root,'services/api'),webDir:path.join(root,'apps/web/dist'),env:{PM_APP_DATA:userData}};
}
export const SETUP_LINKS={ollama:'https://ollama.com/download/windows',generation:'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct',embedding:'https://huggingface.co/Qwen/Qwen3-Embedding-0.6B','whisper-medium':'https://huggingface.co/Systran/faster-whisper-medium','whisper-small':'https://huggingface.co/Systran/faster-whisper-small','whisper-tiny':'https://huggingface.co/Systran/faster-whisper-tiny','community-1':'https://huggingface.co/pyannote/speaker-diarization-community-1'} as const;

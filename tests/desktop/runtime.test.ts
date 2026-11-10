import {describe,it,expect} from 'vitest';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {backendLocation,SETUP_LINKS} from '../../apps/desktop/src/runtime';
const require=createRequire(import.meta.url);
const beforePack=require('../../packaging/before-pack.cjs') as (context:unknown)=>Promise<void>;

describe('bundled launch and installer gates',()=>{
 it('uses a bundled executable and resources instead of an external Python override',()=>{
  const location=backendLocation({packaged:true,resourcesPath:'/Installed App/resources',root:'/ignored/checkout',userData:'/Private Data',platform:'win32',pythonOverride:'/untrusted/python'});
  expect(location.command).toBe('/Installed App/resources/backend/pm-copilot-api/pm-copilot-api.exe');
  expect(location.args).toEqual([]);expect(location.webDir).toBe('/Installed App/resources/web');
  expect(location.env.PM_CAPTURE_HELPER).toBe('/Installed App/resources/helpers/audio/PmCopilot.Capture.exe');
  expect(location.command).not.toContain('checkout');expect(JSON.stringify(location)).not.toContain('untrusted');
 });
 it('preserves the development worker entry and supports a Linux package smoke',()=>{
  const base={resourcesPath:'/resources',root:'/repo',userData:'/private',platform:'linux'};
  expect(backendLocation({...base,packaged:false,pythonOverride:'/python'}).args).toEqual(['-m','pm_copilot']);
  expect(backendLocation({...base,packaged:true}).command).toBe('/resources/backend/pm-copilot-api/pm-copilot-api');
 });
 it('allows only fixed HTTPS dependency and license links',()=>{
  for(const url of Object.values(SETUP_LINKS)){expect(new URL(url).protocol).toBe('https:');expect(['ollama.com','huggingface.co']).toContain(new URL(url).hostname);}
 });
 it('rejects a Linux backend as input for a Windows installer',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'m6-pack-gate-'));
  try{
   await fs.mkdir(path.join(root,'build/notices'),{recursive:true});
   await fs.writeFile(path.join(root,'build/notices/runtime-manifest.json'),JSON.stringify({platform:'linux',fullModelRuntime:false}));
   await expect(beforePack({electronPlatformName:'win32',packager:{projectDir:root}})).rejects.toThrow('real Windows backend');
  }finally{await fs.rm(root,{recursive:true,force:true});}
 });
});

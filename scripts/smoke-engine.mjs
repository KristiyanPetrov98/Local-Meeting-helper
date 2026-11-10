// Run the actual staged Windows executable and production process supervisor.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {LocalEngine}=require('../apps/desktop/dist/ollama-runtime.cjs');
if(process.platform!=='win32')throw new Error('Windows runtime smoke requires Windows.');
const port=11439;
function version(){return new Promise(resolve=>{
 const request=http.get({hostname:'127.0.0.1',port,path:'/api/version',agent:false},response=>{
  let data='';response.on('data',chunk=>{data+=chunk;if(data.length>4096){request.destroy();resolve(null);}});
  response.on('end',()=>{try{resolve(response.statusCode===200?JSON.parse(data).version:null);}catch{resolve(null);}});response.on('error',()=>resolve(null));
 });request.setTimeout(1000,()=>{request.destroy();resolve(null);});request.on('error',()=>resolve(null));
});}
const manifest=JSON.parse(await fs.readFile('build/runtime/ollama/installation.json','utf8'));
const engine=new LocalEngine({command:path.resolve('build/runtime/ollama/ollama.exe'),port,startupMs:30000});
const started=Date.now();
try{
 await engine.ensureStarted();if(!engine.status.managed)throw new Error('Smoke port was already occupied.');
 const actual=await version();if(actual!==manifest.version.replace(/^v/,''))throw new Error('Staged runtime version differs from its release manifest.');
 const startup_ms=Date.now()-started;
 await engine.stop();if(await version())throw new Error('Owned Windows server did not stop.');
 await fs.writeFile('build/notices/engine-smoke.json',JSON.stringify({platform:'win32',status:'passed',version:actual,startup_ms,owned_server_started:true,owned_server_stopped:true,model_inference_verified:false},null,2)+'\n');
 console.log('Actual staged Windows local engine started, answered version and stopped.');
}finally{await engine.stop();}

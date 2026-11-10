import {describe,it,expect} from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import net from 'node:net';
import {LocalEngine} from '../../apps/desktop/src/ollama';

async function freePort(){const server=net.createServer();await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const port=(server.address() as net.AddressInfo).port;await new Promise<void>(r=>server.close(()=>r()));return port;}
describe('managed local engine',()=>{
 it('starts one actual child with private settings and stops it on shutdown',async()=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'copilot-engine-'));const port=await freePort();const file=path.join(directory,'server.mjs');
  await fs.writeFile(file,`import http from 'node:http';
   if(process.env.OLLAMA_NUM_PARALLEL!=='1'||process.env.OLLAMA_NO_CLOUD!=='1')process.exit(2);
   const server=http.createServer((q,r)=>{r.setHeader('Content-Type','application/json');r.end(JSON.stringify({version:'test-fixture'}));});
   server.listen(Number(process.env.OLLAMA_HOST.split(':').pop()),'127.0.0.1');
   process.on('SIGTERM',()=>server.close(()=>process.exit(0)));`);
  const states:string[]=[];const engine=new LocalEngine({command:process.execPath,args:[file],port,startupMs:2500,changed:s=>states.push(s.state)});
  try{
   await Promise.all([engine.ensureStarted(),engine.ensureStarted()]);
   expect(engine.status).toMatchObject({state:'ready',managed:true,error:null});expect(states.filter(s=>s==='starting')).toHaveLength(1);
   await engine.ensureStarted();expect(engine.status.managed).toBe(true);
   await engine.stop();expect(engine.status.state).toBe('stopped');
   await expect(fetch(`http://127.0.0.1:${port}/api/version`)).rejects.toThrow();
  }finally{await engine.stop();await fs.rm(directory,{recursive:true,force:true});}
 },10000);
 it('reuses an existing server and leaves it running when the app exits',async()=>{
  const server=http.createServer((q,r)=>r.end(JSON.stringify({version:'external-fixture'})));
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const port=(server.address() as net.AddressInfo).port;
  const engine=new LocalEngine({command:'/must-not-run',port,startupMs:500});
  try{await engine.ensureStarted();expect(engine.status).toMatchObject({state:'ready',managed:false});await engine.stop();expect((await fetch(`http://127.0.0.1:${port}/api/version`)).ok).toBe(true);}
  finally{await new Promise<void>(r=>server.close(()=>r()));}
 });
 it('reports missing runtime without hanging',async()=>{
  const engine=new LocalEngine({command:path.join(os.tmpdir(),'missing-copilot-engine.exe'),port:await freePort(),startupMs:500});
  await expect(engine.ensureStarted()).rejects.toThrow('did not become ready');expect(engine.status.state).toBe('error');await engine.stop();
 });
});

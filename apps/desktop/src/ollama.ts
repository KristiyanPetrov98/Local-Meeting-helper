import {spawn,execFile,type ChildProcess} from 'node:child_process';
import http from 'node:http';
import path from 'node:path';

export interface EngineStatus {state:'starting'|'ready'|'stopped'|'error';managed:boolean;error:string|null}

/** Own only the server we launch; preserve an already-running local Ollama. */
export class LocalEngine {
 private child:ChildProcess|null=null;
 private starting:Promise<void>|null=null;
 private stopping=false;
 status:EngineStatus={state:'stopped',managed:false,error:null};
 constructor(private options:{command:string;args?:string[];port?:number;startupMs?:number;changed?:(state:EngineStatus)=>void}){}
 private update(value:EngineStatus){this.status=value;this.options.changed?.({...value});}
 private probe():Promise<boolean>{
  return new Promise(resolve=>{
   const request=http.get({hostname:'127.0.0.1',port:this.options.port??11434,path:'/api/version',agent:false},response=>{
    let data='';response.setEncoding('utf8');
    response.on('data',chunk=>{data+=chunk;if(data.length>4096){request.destroy();resolve(false);}});
    response.on('end',()=>{try{resolve(response.statusCode===200&&typeof JSON.parse(data).version==='string');}catch{resolve(false);}});
    response.on('error',()=>resolve(false));
   });
   request.setTimeout(750,()=>{request.destroy();resolve(false);});
   request.on('error',()=>resolve(false));
  });
 }
 ensureStarted():Promise<void>{
  if(this.starting)return this.starting;
  this.starting=this.start().finally(()=>{this.starting=null;});return this.starting;
 }
 private async start(){
  if(await this.probe()){this.update({state:'ready',managed:!!this.child,error:null});return;}
  this.stopping=false;this.update({state:'starting',managed:true,error:null});
  const child=spawn(this.options.command,this.options.args??['serve'],{cwd:path.isAbsolute(this.options.command)?path.dirname(this.options.command):undefined,windowsHide:true,shell:false,stdio:'ignore',env:{...process.env,
   OLLAMA_HOST:`127.0.0.1:${this.options.port??11434}`,OLLAMA_NUM_PARALLEL:'1',OLLAMA_NO_CLOUD:'1'}});
  this.child=child;
  let exited=false;
  const failed=()=>{exited=true;if(this.child===child)this.child=null;if(!this.stopping)this.update({state:'error',managed:true,error:'The local AI engine could not start. Check the installation, GPU driver and local port 11434.'});};
  child.once('error',failed);child.once('exit',failed);
  const deadline=Date.now()+(this.options.startupMs??30000);
  while(!exited&&!this.stopping&&Date.now()<deadline){
   if(await this.probe()){
    if(exited||this.stopping)break;
    this.update({state:'ready',managed:true,error:null});return;
   }
   await new Promise(resolve=>setTimeout(resolve,150));
  }
  await this.stop();
  const message='The local AI engine did not become ready. Repair the installation or retry setup.';
  this.update({state:'error',managed:false,error:message});throw new Error(message);
 }
 async stop(){
  this.stopping=true;const child=this.child;
  if(child&&child.exitCode===null&&child.pid){
   const exit=new Promise<void>(resolve=>{child.once('exit',()=>resolve());child.once('error',()=>resolve());});
   if(process.platform==='win32'){
    // Terminate this owned server's runner tree, never an external Ollama server.
    await new Promise<void>(resolve=>execFile(path.join(process.env.SystemRoot??'C:\\Windows','System32','taskkill.exe'),['/PID',String(child.pid),'/T','/F'],{windowsHide:true,timeout:3000},()=>resolve()));
   }else child.kill('SIGTERM');
   let timer:ReturnType<typeof setTimeout>|undefined;
   const ended=await Promise.race([exit.then(()=>true),new Promise<boolean>(resolve=>{timer=setTimeout(()=>resolve(false),3000);})]);
   if(timer)clearTimeout(timer);
   if(!ended)child.kill('SIGKILL');
  }
  if(this.child===child)this.child=null;
  this.update({state:'stopped',managed:false,error:null});
 }
}

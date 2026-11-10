import type {DesktopBridge,NativeStatus,Snapshot} from '../../../packages/contracts/src';
export interface Bootstrap {origin:string;token:string;view:'mini'|'dashboard';native:NativeStatus|null}
export async function bootstrap():Promise<Bootstrap>{
 if(window.copilot)return window.copilot.bootstrap();
 const fragment=new URLSearchParams(location.hash.slice(1));
 const incoming=fragment.get('token');
 if(incoming){sessionStorage.setItem('copilot-token',incoming);history.replaceState(null,'',location.pathname);}
 const token=sessionStorage.getItem('copilot-token');
 if(!token)throw new Error('Open this dashboard from the PM Copilot desktop application to authenticate.');
 return {origin:location.origin,token,view:'dashboard',native:null};
}
export class Client {
 constructor(readonly config:Bootstrap){}
 async request<T=Snapshot>(route:string,method='GET',body?:unknown):Promise<T>{
   const response=await fetch(this.config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+this.config.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
   if(!response.ok){const error=await response.json().catch(()=>({detail:'Local service request failed'}));throw new Error(typeof error.detail==='string'?error.detail:'Please check the supplied values');}
   return response.json();
 }
 async uploadDocument(projectId:string,file:File){
   const params=new URLSearchParams({filename:file.name,modified_at:new Date(file.lastModified).toISOString()});
   const response=await fetch(this.config.origin+`/api/projects/${projectId}/documents?${params}`,{
     method:'POST',headers:{Authorization:'Bearer '+this.config.token,'Content-Type':'application/octet-stream'},body:file,signal:AbortSignal.timeout(45000)});
   if(!response.ok){const error=await response.json().catch(()=>({detail:'Upload failed'}));throw new Error(typeof error.detail==='string'?error.detail:'Invalid document upload');}
   return response.json();
 }
 subscribe(update:(state:Snapshot)=>void,connection:(connected:boolean)=>void){
   let socket:WebSocket,closed=false,timer:ReturnType<typeof setTimeout>,delay=300;
   const connect=()=>{
     socket=new WebSocket(this.config.origin.replace('http:','ws:')+'/api/events');
     socket.onopen=()=>socket.send(JSON.stringify({token:this.config.token}));
     socket.onmessage=event=>{try{const msg=JSON.parse(event.data);if(msg.type==='state.updated'&&msg.version===1){update(msg.state);connection(true);delay=300;}}catch{socket.close();}};
     socket.onclose=()=>{connection(false);if(!closed){timer=setTimeout(connect,delay);delay=Math.min(5000,delay*2);}};
     socket.onerror=()=>socket.close();
   };connect();
   return ()=>{closed=true;clearTimeout(timer);socket?.close();};
 }
}

import {app,BrowserWindow,dialog,globalShortcut,ipcMain,Menu,nativeImage,screen,shell,Tray} from 'electron';
import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomBytes,randomUUID} from 'node:crypto';
import path from 'node:path';
import fs from 'node:fs';
import readline from 'node:readline';
import type {NativeCommand,NativeStatus,Snapshot} from '../../../packages/contracts/src';
import {Shortcuts} from './shortcut';
import {fit} from './bounds';
import {backendLocation,SETUP_LINKS} from './runtime';

const root=path.resolve(__dirname,'../../..');
if(process.env.PM_COPILOT_DATA_DIR)app.setPath('userData',path.resolve(process.env.PM_COPILOT_DATA_DIR));
const token=randomBytes(32).toString('hex'),desktopCapability=randomBytes(32).toString('hex');
let origin='',backend:ChildProcessWithoutNullStreams, dashboard:BrowserWindow,mini:BrowserWindow,tray:Tray;
let quitting=false, closing=false, expanded=true;
let status:NativeStatus={shortcut:'Control+Shift+Space',registered:false,error:null,lastTriggered:null,assistanceError:null,miniExpanded:true};
const shortcuts=new Shortcuts(globalShortcut,()=>{status.lastTriggered=Date.now();void showMini();broadcast();void triggerAssistance();});
const broadcast=()=>{for(const w of [dashboard,mini])if(w&&!w.isDestroyed())w.webContents.send('copilot:status',status);};
async function showMini(){
  const allowed=await sharingAllowed().catch(()=>false);
  if(!allowed){if(mini&&!mini.isDestroyed())mini.hide();return;}
  if(!mini||mini.isDestroyed())return;
  expanded=true;status.miniExpanded=true;mini.setSize(360,560);
  mini.setBounds(fit(mini.getBounds(),screen.getAllDisplays().map(d=>d.workArea)));
  mini.show();mini.focus();broadcast();
}
let safetyTimer:ReturnType<typeof setInterval>|undefined;
let checkingSharing=false;
async function sharingAllowed(){
  const response=await fetch(origin+'/api/sharing',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(1000)});
  return response.ok&&(await response.json()).mini_allowed===true;
}
async function enforceSharing(){
  if(checkingSharing)return;checkingSharing=true;
  try{if(!await sharingAllowed()&&!mini.isDestroyed())mini.hide();}
  catch{if(mini&&!mini.isDestroyed())mini.hide();}
  finally{checkingSharing=false;}
}
let triggeringAssistance=false;
async function triggerAssistance(){
  if(triggeringAssistance||quitting||closing)return;
  triggeringAssistance=true;status.assistanceError=null;broadcast();
  try{
    const state=await api('state');
    if(state.assistance.busy)return;
    const session=state.session;
    if(!session||!['active','paused'].includes(session.state)||state.selected_project_id!==session.project_id)throw new Error('Start a session and select its project to request a briefing.');
    await api(`projects/${session.project_id}/sessions/${session.id}/assistance`,'POST',{request_id:randomUUID()});
  }catch(error){status.assistanceError=(error as Error).message;broadcast();}
  finally{triggeringAssistance=false;}
}
async function api<T=Snapshot>(route:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch(origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
  if(!response.ok){const detail=await response.json().catch(()=>({detail:'Local service rejected the request'}));throw new Error(typeof detail.detail==='string'?detail.detail:'Local service rejected the request');}
  return response.json();
}
async function startBackend():Promise<string>{
  const location=backendLocation({packaged:app.isPackaged,resourcesPath:process.resourcesPath,root,userData:app.getPath('userData'),platform:process.platform,pythonOverride:process.env.PM_COPILOT_PYTHON});
  backend=spawn(location.command,location.args,{cwd:location.cwd,env:{...process.env,...location.env},windowsHide:true,stdio:['pipe','pipe','pipe']});
  // Consume stderr without exposing request content or secrets in application logs.
  backend.stderr.on('data',()=>{});
  backend.stdin.on('error',()=>{});
  backend.stdin.write(JSON.stringify({database:path.join(app.getPath('userData'),'copilot.sqlite3'),token,web_dir:location.webDir,desktop_pid:process.pid,desktop_capability:desktopCapability})+'\n');
  return new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{backend.kill();reject(new Error('Local service did not become ready in 20 seconds'));},20000);
    const lines=readline.createInterface({input:backend.stdout});
    backend.once('error',()=>{clearTimeout(timeout);reject(new Error(app.isPackaged?'The bundled backend could not start. Repair or reinstall PM Copilot; an external Python installation is not required.':'Cannot start Python. Install the API dependencies and configure PM_COPILOT_PYTHON.'));});
    backend.once('exit',()=>{clearTimeout(timeout);reject(new Error('Local service exited before becoming ready'));});
    lines.on('line',line=>{
      try{const message=JSON.parse(line);if(message.type==='ready'&&/^http:\/\/127\.0\.0\.1:\d+$/.test(message.origin)){
        clearTimeout(timeout);lines.close();resolve(message.origin);
      }}catch{/* Ignore non-protocol lines. */}
    });
  });
}
function windows(){
  const common={webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,sandbox:true,nodeIntegration:false,webSecurity:true}};
  dashboard=new BrowserWindow({...common,title:'PM Copilot',width:1240,height:840,minWidth:840,minHeight:640,backgroundColor:'#101512',show:false});
  const work=screen.getPrimaryDisplay().workArea;
  mini=new BrowserWindow({...common,title:'PM Copilot companion',width:360,height:560,x:work.x+work.width-384,y:work.y+32,minWidth:340,minHeight:100,frame:false,alwaysOnTop:true,skipTaskbar:true,resizable:false,show:false,backgroundColor:'#101512'});
  mini.setContentProtection(true);dashboard.setContentProtection(true);
  const positionFile=path.join(app.getPath('userData'),'mini-position.json');
  try {const p=JSON.parse(fs.readFileSync(positionFile,'utf8'));if(Number.isFinite(p.x)&&Number.isFinite(p.y))mini.setBounds(fit({...mini.getBounds(),x:p.x,y:p.y},screen.getAllDisplays().map(d=>d.workArea)));}catch{/* First launch. */}
  mini.on('moved',()=>{if(!mini.isDestroyed()){const{x,y}=mini.getBounds();fs.writeFileSync(positionFile,JSON.stringify({x,y}));}});
  const recover=()=>{if(!mini.isDestroyed())mini.setBounds(fit(mini.getBounds(),screen.getAllDisplays().map(d=>d.workArea)));};
  screen.on('display-removed',recover);screen.on('display-metrics-changed',recover);
  for(const win of [dashboard,mini]){
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin)event.preventDefault();});
    win.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    win.on('close',event=>{if(!quitting){event.preventDefault();win.hide();}});
    win.webContents.on('render-process-gone',()=>{if(!quitting){dialog.showErrorBox('PM Copilot','A window stopped responding. Restart the application; the session will be stopped safely.');app.quit();}});
  }
  dashboard.once('ready-to-show',()=>dashboard.show());
  void dashboard.loadURL(origin);
  void mini.loadURL(origin+'/?view=mini');
}
function trusted(event:Electron.IpcMainInvokeEvent){
  const window=BrowserWindow.fromWebContents(event.sender);
  if(![dashboard,mini].includes(window!)||event.senderFrame!==event.sender.mainFrame||new URL(event.senderFrame!.url).origin!==origin)throw new Error('Untrusted IPC sender');
}
async function setShortcut(accelerator:string){
  const old=shortcuts.current;
  shortcuts.set(accelerator);
  try{await api('settings/shortcut','PUT',{accelerator});}
  catch(e){if(old)shortcuts.set(old);else shortcuts.clear();throw e;}
  status={...status,shortcut:accelerator,registered:true,error:null};broadcast();
}
if(!app.requestSingleInstanceLock())app.quit();
else{
 app.on('second-instance',()=>{if(dashboard){dashboard.show();dashboard.focus();}});
 app.whenReady().then(async()=>{
  try{
    origin=await startBackend();
    const state=await api('state');
    try{shortcuts.set(state.shortcut);status={...status,shortcut:state.shortcut,registered:true};}
    catch(e){status={...status,shortcut:state.shortcut,error:(e as Error).message};}
    windows();
    safetyTimer=setInterval(()=>void enforceSharing(),250);
    ipcMain.handle('copilot:bootstrap',event=>{trusted(event);return {origin,token,view:event.sender===mini.webContents?'mini':'dashboard',native:status};});
    ipcMain.handle('copilot:command',async(event,command:NativeCommand)=>{
      trusted(event);
      if(!command||typeof command!=='object')throw new Error('Invalid command');
      switch(command.type){
        case 'mini':
          if(command.action==='show')await showMini();
          else if(command.action==='hide')mini.hide();
          else if(command.action==='collapse'||command.action==='expand'){expanded=command.action==='expand';status.miniExpanded=expanded;mini.setSize(360,expanded?560:112);broadcast();mini.setBounds(fit(mini.getBounds(),screen.getAllDisplays().map(d=>d.workArea)));}
          else throw new Error('Invalid window action');break;
        case 'dashboard':dashboard.show();dashboard.focus();break;
        case 'browser':await shell.openExternal(origin+'/#token='+token);break;
        case 'setup-link':
          if(!Object.prototype.hasOwnProperty.call(SETUP_LINKS,command.topic))throw new Error('Unsupported setup link');
          await shell.openExternal(SETUP_LINKS[command.topic]);break;
        case 'import-model':{
          if(!['whisper-medium','whisper-small','whisper-tiny','community-1'].includes(command.model)||command.licenseAcknowledged!==true)throw new Error('Confirm official snapshot provenance and license first.');
          const selected=await dialog.showOpenDialog(dashboard,{title:'Choose an approved offline model snapshot',properties:['openDirectory']});
          if(!selected.canceled&&selected.filePaths[0]){
            const response=await fetch(origin+'/api/setup/import',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','X-Desktop-Capability':desktopCapability},body:JSON.stringify({model_id:command.model,source:selected.filePaths[0],license_acknowledged:true,replace:command.replace===true})});
            if(!response.ok){const error=await response.json();throw new Error(typeof error.detail==='string'?error.detail:'Model import failed');}
          }
          break;
        }
        case 'shortcut':await setShortcut(command.accelerator);break;
        case 'quit':app.quit();break;
        default:throw new Error('Unsupported command');
      }
      return status;
    });
    // An in-memory icon keeps tray lifecycle available without external resources.
    const icon=nativeImage.createFromBuffer(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="8" fill="#b4e7b9"/><text x="6" y="23" font-size="23" fill="#14251b">P</text></svg>'));
    // SVG decoding differs by platform; a raw bitmap is a reliable fallback.
    const pixels=Buffer.alloc(16*16*4);for(let i=0;i<pixels.length;i+=4){pixels[i]=120;pixels[i+1]=190;pixels[i+2]=130;pixels[i+3]=255;}
    tray=new Tray(icon.isEmpty()?nativeImage.createFromBitmap(pixels,{width:16,height:16}):icon);
    tray.setToolTip('PM Copilot — local workspace');
    tray.setContextMenu(Menu.buildFromTemplate([{label:'Open dashboard',click:()=>dashboard.show()},{label:'Show companion',click:showMini},{label:'Stop session',click:()=>void api('state').then(s=>s.session&&['active','paused'].includes(s.session.state)?api(`sessions/${s.session.id}/stop`,'POST'):null).catch(()=>dialog.showErrorBox('PM Copilot','Unable to stop session; open the dashboard.'))},{type:'separator'},{label:'Quit',click:()=>app.quit()}]));
    tray.on('click',()=>dashboard.show());
    backend.on('exit',()=>{if(!quitting&&!closing){dialog.showErrorBox('PM Copilot','The local service stopped. Restart PM Copilot to recover.');app.quit();}});
  }catch(e){dialog.showErrorBox('PM Copilot startup failed',(e as Error).message);backend?.kill();quitting=true;app.quit();}
 });
 app.on('before-quit',event=>{
  if(quitting)return;
  event.preventDefault();if(closing)return;closing=true;
  void (async()=>{
    try{const s=await api('state');if(s.session&&['active','paused'].includes(s.session.state))await api(`sessions/${s.session.id}/stop`,'POST');}catch{/* Recovery marks live sessions interrupted on next launch. */}
    if(safetyTimer)clearInterval(safetyTimer);
    quitting=true;shortcuts.clear();globalShortcut.unregisterAll();tray?.destroy();
    if(backend?.exitCode===null){backend.kill();setTimeout(()=>{if(backend.exitCode===null)backend.kill('SIGKILL');},1500).unref();}
    app.quit();
  })();
 });
 app.on('window-all-closed',()=>{/* Tray owns application lifetime. */});
 app.on('activate',()=>{if(dashboard)dashboard.show();});
}

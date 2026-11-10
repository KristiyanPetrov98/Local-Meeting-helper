import {contextBridge,ipcRenderer} from 'electron';
import type {DesktopBridge,NativeStatus} from '../../../packages/contracts/src';
const bridge:DesktopBridge={
  bootstrap:()=>ipcRenderer.invoke('copilot:bootstrap'),
  command:command=>ipcRenderer.invoke('copilot:command',command),
  onStatus:callback=>{
    const listener=(_event:unknown,status:NativeStatus)=>callback(status);
    ipcRenderer.on('copilot:status',listener);
    return ()=>ipcRenderer.removeListener('copilot:status',listener);
  }
};
contextBridge.exposeInMainWorld('copilot',bridge);

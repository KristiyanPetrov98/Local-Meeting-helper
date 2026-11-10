import type { components } from './api.generated';
export type Snapshot = components['schemas']['Snapshot'];
export type Session = components['schemas']['Session'];
export interface NativeStatus {
  shortcut: string; registered: boolean; error: string | null; lastTriggered: number | null; assistanceError: string | null; miniExpanded: boolean;
  engine?:{state:'starting'|'ready'|'stopped'|'error';managed:boolean;error:string|null};
}
export type NativeCommand =
  | {type:'mini'; action:'show'|'hide'|'collapse'|'expand'}
  | {type:'dashboard'} | {type:'browser'} | {type:'quit'}
  | {type:'engine-start'}
  | {type:'export-report';kind:'performance'|'qualification'}
  | {type:'shortcut'; accelerator:string}
  | {type:'setup-link'; topic:'ollama'|'generation'|'embedding'|'whisper-medium'|'whisper-small'|'whisper-tiny'|'community-1'}
  | {type:'import-model'; model:'whisper-medium'|'whisper-small'|'whisper-tiny'|'community-1';licenseAcknowledged:boolean;replace:boolean};
export interface DesktopBridge {
  bootstrap(): Promise<{origin:string; token:string; view:'dashboard'|'mini'; native:NativeStatus}>;
  command(command:NativeCommand): Promise<NativeStatus>;
  onStatus(callback:(status:NativeStatus)=>void): ()=>void;
}
declare global { interface Window { copilot?: DesktopBridge } }

import {useEffect,useState} from 'react';
import {Button} from '../../../packages/ui/src/button';
import type {Snapshot} from '../../../packages/contracts/src';
import type {components} from '../../../packages/contracts/src/api.generated';
import {Client} from './client';
type Options=components['schemas']['AudioOptions'];
type Page=components['schemas']['TranscriptPage'];
interface Devices {devices:{id:string;name:string;kind:string}[];reason?:string;process_loopback:boolean}
export function MeetingPanel({client,state,connected}:{client:Client;state:Snapshot;connected:boolean}){
 const [options,setOptions]=useState<Options|null>(null),[devices,setDevices]=useState<Devices>({devices:[],process_loopback:false});
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[retention,setRetention]=useState(30);
 const [chosen,setChosen]=useState(''),[page,setPage]=useState<Page|null>(null),[edits,setEdits]=useState<Record<string,string>>({}),[merges,setMerges]=useState<Record<string,string>>({});
 const sessions=state.sessions.filter(s=>s.project_id===state.selected_project_id);
 const session=sessions.find(s=>s.id===chosen)??sessions[0];
 const active=!!state.session&&['active','paused'].includes(state.session.state);
 const locked=state.session?.state==='active';
 const base=session?`projects/${session.project_id}/sessions/${session.id}`:'';
 const loadDevices=async()=>setDevices(await client.request<Devices>('audio/devices'));
 useEffect(()=>{void Promise.all([client.request<Options>('audio/settings').then(setOptions),loadDevices(),client.request<{days:number}>('settings/retention').then(v=>setRetention(v.days))]).catch(e=>setError(e.message));},[client]);
 useEffect(()=>{
  let alive=true;
  if(!session){setPage(null);return;}
  void client.request<Page>(base+'/transcript').then(p=>{if(alive)setPage(p);}).catch(e=>{if(alive)setError(e.message);});
  return ()=>{alive=false;};
 },[client,base,state.revision]);
 const run=async(fn:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 const patch=<K extends keyof Options>(key:K,value:Options[K])=>setOptions(old=>old?{...old,[key]:value}:old);
 return <section className="panel mt-6" aria-label="Audio and transcript"><div className="flex justify-between gap-4"><div><div className="eyebrow mb-2">LIVE MEETING PIPELINE</div><h2>Audio & transcript</h2></div><span className="tag">{state.meeting.state}</span></div>
 <p className="muted text-sm mt-3">{state.meeting.reason??'Local Whisper transcription · audio is held in RAM only.'}</p>
 <p className="muted text-xs mt-2">Meet uses the selected output’s WASAPI loopback. Other applications on that output are included. Match the output selected in Google Meet settings.</p>
 {state.meeting.error&&<p className="error" role="status">{state.meeting.error}</p>}
 <p className="muted text-xs mt-3">Packets {state.meeting.counts.packets??0} · Queue {state.meeting.queue_depth}/8 · Dropped chunks {state.meeting.counts.dropped_chunks??0} · Discontinuities {state.meeting.counts.gaps??0} · ASR errors {state.meeting.counts.asr_errors??0}</p>
 {options&&<><div className="audio-grid mt-5">{(['microphone','loopback'] as const).map(kind=><label key={kind}>{kind==='microphone'?'Microphone':'Meet playback output'}<select aria-label={kind==='microphone'?'Microphone':'Meet playback output'} disabled={locked||busy} value={options[kind]??''} onChange={e=>patch(kind,e.target.value||null)}><option value="">Disabled</option><option value="default">Windows default</option>{devices.devices.filter(d=>d.kind===kind).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>)}
 <label>Meeting language<select disabled={locked||busy} value={options.language??'auto'} onChange={e=>patch('language',e.target.value as Options['language'])}><option value="auto">Auto (English / Bulgarian)</option><option value="en">English</option><option value="bg">Bulgarian</option></select></label>
 <label>Whisper execution<select disabled={locked||busy} value={options.device??'cpu'} onChange={e=>patch('device',e.target.value as Options['device'])}><option value="cpu">CPU int8 · preserve 8B VRAM</option><option value="cuda">GPU int8_float16 · benchmark first</option></select></label>
 <label>Audio routing<select disabled={locked||busy} value={options.echo_profile??'headphones'} onChange={e=>patch('echo_profile',e.target.value as Options['echo_profile'])}><option value="headphones">Headphones</option><option value="speakers">Speakers (text echo dedupe)</option></select></label>
 <label>Transcript retention (days)<input aria-label="Transcript retention days" type="number" min={1} max={3650} value={retention} onChange={e=>setRetention(Number(e.target.value))}/></label></div>
 <label className="check mt-4 flex gap-3"><input type="checkbox" disabled={locked||busy} checked={options.diarization??false} onChange={e=>patch('diarization',e.target.checked)}/>Enable CPU Community-1 speaker refinement (offline model assets required).</label>
 <p className="muted text-xs mt-3">Speaker mode uses conservative text deduplication, not acoustic echo cancellation. Headphones are preferred; speaker routing and overlapping speech require laptop testing.</p>
 <div className="flex flex-wrap gap-2 mt-4"><Button variant="secondary" disabled={!connected||locked||busy} onClick={()=>void run(()=>client.request('audio/settings','PUT',options))}>Save audio settings</Button><Button variant="ghost" disabled={busy} onClick={()=>void run(loadDevices)}>Refresh devices</Button><Button variant="ghost" disabled={!connected||busy} onClick={()=>void run(()=>client.request('settings/retention','PUT',{days:retention}))}>Apply retention</Button>{active&&<Button variant="secondary" disabled={busy||state.session?.state!=='active'} onClick={()=>void run(()=>client.request('audio/retry','POST'))}>Retry capture</Button>}</div></>}
 <div className="transcript-view mt-6"><div className="flex items-end justify-between gap-4 mb-4"><h2>Project transcript</h2><label className="grow max-w-sm">Session<select aria-label="Transcript session" value={session?.id??''} onChange={e=>{setChosen(e.target.value);setEdits({});}}><option value="" disabled>Select a session</option>{sessions.map(s=><option key={s.id} value={s.id}>{new Date(s.started_at).toLocaleString()} · {s.state}</option>)}</select></label></div>
 {!page?.segments.length?<p className="muted text-sm">No transcript segments for this session. Enable capture when starting a meeting after configuring local models and devices.</p>:<><div className="transcript-lines">{page.segments.map(segment=><article key={segment.id}><div className="flex items-center gap-3 text-xs muted"><strong>{page.speakers.find(s=>s.id===segment.speaker_id)?.name??'Unrefined'}</strong><span>{Math.floor(segment.start/60)}:{Math.floor(segment.start%60).toString().padStart(2,'0')}</span><span>{segment.language} · {segment.source}</span></div><p>{segment.text}</p></article>)}</div>{page.older_cursor&&<Button variant="ghost" disabled={busy} onClick={()=>void run(async()=>{const older=await client.request<Page>(base+`/transcript?before=${page.older_cursor}`);setPage({...older,segments:[...older.segments,...page.segments].slice(0,1000)});})}>Load older segments (up to 1,000 per view)</Button>}</>}
 {!!page?.speakers.length&&<details className="mt-5"><summary>Rename or merge provisional speakers</summary><p className="muted text-xs mt-3">Labels are provisional. No participant names are inferred. Merges apply only to this session.</p>{page.speakers.map(speaker=><div className="speaker-edit" key={speaker.id}><label>Speaker name<input aria-label={`Name for ${speaker.name}`} value={edits[speaker.id]??speaker.name} maxLength={120} onChange={e=>setEdits(v=>({...v,[speaker.id]:e.target.value}))}/></label><Button variant="secondary" disabled={busy} onClick={()=>void run(()=>client.request(base+`/speakers/${speaker.id}`,'PATCH',{name:edits[speaker.id]??speaker.name}))}>Rename speaker</Button><label>Merge into<select aria-label={`Merge ${speaker.name} into`} value={merges[speaker.id]??''} onChange={e=>setMerges(v=>({...v,[speaker.id]:e.target.value}))}><option value="">Choose speaker</option>{page.speakers.filter(s=>s.id!==speaker.id).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><Button variant="ghost" disabled={busy||!merges[speaker.id]} onClick={()=>void run(()=>client.request(base+`/speakers/${speaker.id}/merge`,'POST',{target:merges[speaker.id]}))}>Merge</Button></div>)}</details>}
 </div>{error&&<p role="alert" className="error">{error}</p>}</section>;
}

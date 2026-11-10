import {useEffect,useState} from 'react';
import {Button} from '../../../packages/ui/src/button';
import type {Snapshot} from '../../../packages/contracts/src';
import type {components} from '../../../packages/contracts/src/api.generated';
import {Client} from './client';
type Summary=components['schemas']['AssistanceSummary'];
type Detail=components['schemas']['AssistanceDetail'];
type Diagnostics=components['schemas']['AssistanceDiagnostics'];
type Claim=components['schemas']['Claim'];
const labels={project_document:'Project document evidence',general_technical_knowledge:'General technical knowledge',unverified_company_claim:'Unverified company-specific information'};

export function AssistancePanel({client,state,connected,compact=false,nativeError}:{client:Client;state:Snapshot;connected:boolean;compact?:boolean;nativeError?:string|null}){
 const pid=state.selected_project_id;
 const sessions=state.sessions.filter(s=>s.project_id===pid);
 const [chosen,setChosen]=useState(''),[picked,setPicked]=useState(''),[working,setWorking]=useState(false),[error,setError]=useState('');
 const [model,setModel]=useState<Diagnostics|null>(null),[history,setHistory]=useState<{scope:string;items:Summary[]}|null>(null),[saved,setSaved]=useState<{scope:string;value:Detail}|null>(null);
 const session=(compact?null:sessions.find(s=>s.id===chosen))??sessions[0];
 const scope=`${pid??''}/${session?.id??''}`;
 const base=pid&&session?`projects/${pid}/sessions/${session.id}/assistance`:null;
 const items=history?.scope===scope?history.items:[];
 const selected=compact?items[0]?.id:picked||items[0]?.id;
 const detail=saved?.scope===scope&&saved.value.id===selected?saved.value:null;
 const live=!!session&&['active','paused'].includes(session.state)&&session.id===state.session?.id;
 useEffect(()=>{let alive=true;void client.request<Diagnostics>('assistance/status').then(v=>{if(alive)setModel(v);}).catch(()=>{});return()=>{alive=false;};},[client]);
 useEffect(()=>{setPicked('');setError('');},[scope]);
 useEffect(()=>{setPicked('');},[items[0]?.id]);
 useEffect(()=>{let alive=true;if(base)void client.request<Summary[]>(base).then(items=>{if(alive)setHistory({scope,items});}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[client,base,scope,state.revision]);
 useEffect(()=>{let alive=true;if(base&&selected)void client.request<Detail>(base+'/'+selected).then(value=>{if(alive)setSaved({scope,value});}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[client,base,selected,scope,state.revision]);
 const run=async(fn:()=>Promise<unknown>)=>{setWorking(true);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setWorking(false);}};
 const request=()=>run(async()=>{if(!base)return;const value=await client.request<Detail>(base,'POST',{request_id:crypto.randomUUID()});setPicked(value.id);setSaved({scope,value});if(!compact&&window.copilot)await window.copilot.command({type:'mini',action:'show'});});
 const claim=(c:Claim,index:number)=>{
  const unavailable=c.citation_ids.some(id=>detail?.unavailable_citations.includes(id));
  return <article className={`briefing-claim ${unavailable?'unavailable':''}`} key={index}><span className="evidence-kind">{labels[c.kind]}</span><p>{c.text}</p>{unavailable&&<p className="error">A saved source is unavailable. Verify this claim before reuse.</p>}
   {c.citation_ids.map(id=>{const cite=detail?.citations.find(c=>c.citation_id===id);return cite?<details className="briefing-citation" key={id}><summary>{cite.filename} · revision {cite.version}</summary><p className="muted text-xs mt-2">{Object.entries(cite.locator).filter(([k])=>!['unit','char_start','char_end','kind'].includes(k)).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>{cite.superseded&&<p className="knowledge-warning">This is an earlier source revision.</p>}<pre>{cite.quote}</pre></details>:<p className="muted text-xs" key={id}>Source unavailable</p>;})}
  </article>;
 };
 return <section className={compact?'assistance compact':'panel mt-6 assistance'} aria-label={compact?'Companion briefing':'Manual assistance'}>
 <div className="flex justify-between items-center gap-3"><div>{!compact&&<div className="eyebrow mb-2">ONLY WHEN YOU ASK</div>}<h2>{compact?'Briefing':'Manual assistance'}</h2></div><span className="tag">{state.assistance.busy?state.assistance.phase:'Ready'}</span></div>
 {!compact&&<p className="muted text-sm mt-3">The shortcut or button snapshots the previous 90 seconds and answers the latest explicit question. No question means no generated answer.</p>}
 <div className="flex flex-wrap gap-2 mt-4"><Button disabled={!connected||working||!live||state.assistance.busy} onClick={()=>void request()}>Request briefing</Button>{detail&&detail.id===state.assistance.active_request_id&&<Button variant="secondary" disabled={working} onClick={()=>void run(async()=>{const value=await client.request<Detail>(base+'/'+detail.id+'/cancel','POST');setSaved({scope,value});})}>Cancel briefing</Button>}</div>
 {!session&&<p className="muted text-xs mt-3">Start a session to use the confirmed transcript.</p>}
 {model&&!model.available&&<details className="model-notice mt-3"><summary>Local generation model unavailable</summary><p className="muted text-xs mt-2">{model.reason}</p><Button variant="ghost" disabled={working} onClick={()=>void run(async()=>setModel(await client.request<Diagnostics>('assistance/status')))}>Refresh generation status</Button></details>}
 {!compact&&<div className="assistance-selectors mt-4"><label>Briefing session<select aria-label="Briefing session" value={session?.id??''} onChange={e=>setChosen(e.target.value)}><option value="" disabled>Select session</option>{sessions.map(s=><option value={s.id} key={s.id}>{new Date(s.started_at).toLocaleString()} · {s.state}</option>)}</select></label><label>Request history<select aria-label="Briefing request history" value={selected??''} onChange={e=>setPicked(e.target.value)}><option value="" disabled>No requests</option>{items.map(r=><option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleTimeString()} · {r.status} · {r.question?.slice(0,50)??'No question'}</option>)}</select></label></div>}
 {detail&&<div className="briefing-result" aria-live="polite">
  {detail.question&&<p className="detected-question"><span>Latest question</span>{detail.question}</p>}
  {detail.status==='no_question'&&<p className="muted text-sm mt-4" role="status">No explicit question found in the previous 90 seconds. No answer was generated.</p>}
  {['retrieving','generating','validating'].includes(detail.status)&&<p className="muted text-sm mt-4" role="status">{detail.status==='retrieving'?'Retrieving project evidence…':detail.status==='generating'?'Generating locally…':'Validating the briefing and source citations…'}</p>}
  {detail.error&&<p role="status" className={detail.status==='cancelled'?'muted text-sm mt-3':'error'}>{detail.error}</p>}
  {detail.response&&<><p className="text-xs muted mt-3">English briefing · {detail.response.model}{detail.elapsed_ms!==null?` · ${(detail.elapsed_ms/1000).toFixed(1)}s`:''}</p>{claim(detail.response.body.briefing,0)}{detail.response.body.supporting_points.map((c,i)=>claim(c,i+1))}{detail.response.body.limitations.length>0&&<div className="briefing-limits"><strong>Limitations</strong>{detail.response.body.limitations.map((l,i)=><p key={i}>{l}</p>)}</div>}</>}
  {detail.warnings.length>0&&<details className="mt-3"><summary>Context and retrieval notes</summary>{detail.warnings.map((w,i)=><p className="muted text-xs mt-2" key={i}>{w}</p>)}</details>}
 </div>}
 {(error||nativeError)&&<p role="alert" className="error">{error||nativeError}</p>}
 </section>;
}

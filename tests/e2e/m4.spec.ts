import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {launch,dashboardWindow} from './helpers';

const python=process.env.PM_COPILOT_PYTHON||(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const seed=(data:string,script:string,...args:string[])=>execFileSync(python,['-c',script,path.join(data,'copilot.sqlite3'),...args]);

test('M4 real Electron button and native shortcut suppress no-question answers; missing model is explicit',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m4-trigger-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(data);const page=await dashboardWindow(app);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,method='POST',body?:unknown)=>{
   const r=await fetch(config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
   expect(r.ok).toBe(true);return r.json();
  };
  await request('sharing','PUT',{mode:'none',acknowledged:true});
  const created=await request('projects','POST',{name:'M4 trigger'});const pid=created.projects[0].id;
  await request(`projects/${pid}/select`);const sid=(await request('sessions','POST',{consent:true,project_id:pid})).session.id;
  // Disposable text fixture only. No production transcript injection or fake model mode.
  seed(data,`import sqlite3,sys,datetime
db=sqlite3.connect(sys.argv[1]);s=sys.argv[2];now=datetime.datetime.now(datetime.timezone.utc)
db.execute('UPDATE sessions SET started_at=? WHERE id=?',((now-datetime.timedelta(seconds=30)).isoformat(),s))
db.execute('INSERT INTO speakers(id,session_id,name) VALUES(?,?,?)',(s+':remote',s,'Remote'))
db.execute('INSERT INTO transcript_segments(session_id,source,start,end,text,language,speaker_id,segment_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(s,'remote',10,13,'The release is scheduled for Friday.','en',s+':remote','m4',now.isoformat()))
db.commit()
`,sid);
  const panel=page.getByRole('region',{name:'Manual assistance'});
  await panel.getByRole('button',{name:'Request briefing',exact:true}).click();
  await expect(panel.getByText('No explicit question found in the previous 90 seconds. No answer was generated.',{exact:true})).toBeVisible();
  const mini=app.windows().find(w=>w.url().includes('view=mini'))!;
  await expect(mini.getByText('No explicit question found in the previous 90 seconds. No answer was generated.',{exact:true})).toBeVisible();
  const base=`projects/${pid}/sessions/${sid}/assistance`;
  expect((await request(base,'GET'))[0].status).toBe('no_question');
  await page.getByRole('button',{name:'Desktop settings'}).click();
  await page.getByLabel('Global shortcut').fill('Control+Shift+P');
  await page.getByRole('button',{name:'Apply shortcut'}).click();
  if(process.env.PM_TEST_X11_INPUT==='1'){
   execFileSync(python,['scripts/test-x11-shortcut.py'],{env:process.env});
   await expect.poll(async()=>(await request(base,'GET')).length).toBe(2);
   expect((await request(base,'GET')).every((r:{status:string})=>r.status==='no_question')).toBe(true);
  }
  seed(data,`import sqlite3,sys
db=sqlite3.connect(sys.argv[1]);db.execute('UPDATE transcript_segments SET text=? WHERE session_id=?',('How can retries avoid duplicated requests?',sys.argv[2]));db.commit()
`,sid);
  await request(`projects/${pid}`,'PATCH',{name:'M4 trigger'});
  const diagnostics=await request('assistance/status','GET');
  // This branch is exercised in the cloud. Do not invoke a user's installed
  // real model from a portable unavailable-model regression test.
  if(!diagnostics.available){
  await mini.getByRole('button',{name:'Request briefing',exact:true}).click();
  await expect(mini.locator('.detected-question')).toContainText('How can retries avoid duplicated requests?');
  await expect(panel.locator('.detected-question')).toContainText('How can retries avoid duplicated requests?');
  await expect.poll(async()=>(await request(base,'GET'))[0].status).toBe('error');
  const latest=(await request(base,'GET'))[0];const detail=await request(base+'/'+latest.id,'GET');
  expect(detail.response).toBeNull();expect(detail.error).toMatch(/Local Ollama|exact primary Ollama model/);
  }else test.info().annotations.push({type:'note',description:'Installed real model: unavailable-model branch not applicable; no real-model quality claim.'});
  expect((await request('state','GET')).session.state).toBe('active');
  expect(errors).toEqual([]);
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

test('M4 saved-briefing rendering, citation checks, project isolation and restart (explicit response fixture)',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m4-history-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(data);let page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  let config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,method='POST',body?:unknown)=>{
   const r=await fetch(config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});expect(r.ok).toBe(true);return r.json();
  };
  await request('sharing','PUT',{mode:'none',acknowledged:true});
  const created=await request('projects','POST',{name:'Alpha briefing'});const pid=created.projects[0].id;
  await request(`projects/${pid}/select`);
  const upload=await fetch(config.origin+`/api/projects/${pid}/documents?filename=release.txt`,{method:'POST',headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/octet-stream'},body:'The release is scheduled for Friday.'});
  expect(upload.status).toBe(202);const imported=await upload.json();
  await expect.poll(async()=>(await request(`projects/${pid}/documents`,'GET')).documents[0].chunk_count).toBeGreaterThan(0);
  const search=await request(`projects/${pid}/knowledge/search`,'POST',{query:'release',mode:'lexical'});
  const cid=search.hits[0].citation.citation_id;
  const sid=(await request('sessions','POST',{consent:true,project_id:pid})).session.id;
  // Rendering fixture: API tests separately exercise generation and validation.
  seed(data,`import sqlite3,sys,json,uuid,datetime
db=sqlite3.connect(sys.argv[1]);p,s,cid=sys.argv[2:5];rid=str(uuid.uuid4());now=datetime.datetime.now(datetime.timezone.utc).isoformat()
db.execute('INSERT INTO assistance_requests(id,project_id,session_id,status,phase,created_at,completed_at,window_start,window_end,transcript_digest,question,segment_ids,warnings,elapsed_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,p,s,'completed','completed',now,now,0,30,'a'*64,'When is the release?','[]','[]',1234))
body={'language':'en','briefing':{'text':'The project document schedules the release for Friday.','kind':'project_document','citation_ids':[cid]},'supporting_points':[{'text':'Release readiness should be assessed against explicit acceptance criteria.','kind':'general_technical_knowledge','citation_ids':[]},{'text':'The company deployment policy is unknown without further documentation.','kind':'unverified_company_claim','citation_ids':[]}],'limitations':[]}
db.execute('INSERT INTO generated_responses VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),rid,json.dumps(body),'qwen3-vl:8b-instruct-q4_K_M','b'*64,'{}',now));db.commit()
`,pid,sid,cid);
  await request(`projects/${pid}`,'PATCH',{name:'Alpha briefing'});
  const text='The project document schedules the release for Friday.';
  const panel=()=>page.getByRole('region',{name:'Manual assistance'});
  await expect(panel().getByText(text,{exact:true})).toBeVisible();
  await expect(panel().getByText('General technical knowledge',{exact:true})).toBeVisible();
  await expect(panel().getByText('Unverified company-specific information',{exact:true})).toBeVisible();
  await panel().locator('.briefing-citation summary').click();
  await expect(panel().locator('.briefing-citation pre')).toHaveText('The release is scheduled for Friday.');
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));
  const mini=app.windows().find(w=>w.url().includes('view=mini'))!;
  await expect(mini.getByText(text,{exact:true})).toBeVisible();
  await request(`projects/${pid}/documents/${imported.document_id}`,'DELETE');
  await expect(panel().getByText('A saved source is unavailable. Verify this claim before reuse.')).toBeVisible();
  await expect(panel().locator('.briefing-citation')).toHaveCount(0);
  await request(`sessions/${sid}/stop`);
  const beta=(await request('projects','POST',{name:'Beta briefing'})).projects.find((p:{name:string})=>p.name==='Beta briefing').id;
  await request(`projects/${beta}/select`);await expect(panel().getByText(text,{exact:true})).toHaveCount(0);
  await request(`projects/${pid}/select`);await expect(panel().getByText(text,{exact:true})).toBeVisible();
  await app.close();app=undefined;app=await launch(data);page=await dashboardWindow(app);
  config=await page.evaluate(()=>window.copilot!.bootstrap());
  await expect(panel().getByText(text,{exact:true})).toBeVisible();
  await expect(panel().getByText('A saved source is unavailable. Verify this claim before reuse.')).toBeVisible();
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

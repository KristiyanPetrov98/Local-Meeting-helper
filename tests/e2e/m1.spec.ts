import {test,expect,chromium,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import {launch,dashboardWindow} from './helpers';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';

test('real desktop + browser share persisted projects and session states',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-e2e-'));
 let app:ElectronApplication|undefined;
 const browser=await chromium.launch({executablePath:process.env.PM_CHROMIUM_PATH||undefined,headless:true});
 try{
  app=await launch(data);
  const dashboard=await dashboardWindow(app);
  const errors:string[]=[];dashboard.on('pageerror',e=>errors.push(e.message));
  await expect(dashboard.getByText('Local service connected',{exact:true})).toBeVisible();
  await dashboard.getByRole('button',{name:'Create project',exact:true}).click();
  await dashboard.getByLabel('Project name').fill('Platform migration');
  await dashboard.getByRole('button',{name:'Save project'}).click();
  await dashboard.getByRole('button',{name:'Platform migration',exact:true}).click();
  await dashboard.getByRole('button',{name:'Rename',exact:true}).click();
  await dashboard.getByLabel('Project name').fill('Platform release');
  await dashboard.getByRole('button',{name:'Save project'}).click();
  const config=await dashboard.evaluate(()=>window.copilot!.bootstrap());
  expect(config.native.registered).toBe(true);
  const external=await browser.newPage();
  await external.goto(config.origin+'/#token='+config.token);
  await expect(external.getByText('Local service connected',{exact:true})).toBeVisible();
  expect(external.url()).not.toContain(config.token);
  await expect(external.getByRole('heading',{name:'Platform release',exact:true})).toBeVisible();
  await dashboard.getByRole('button',{name:'Start session',exact:true}).click();
  const dialog=dashboard.getByRole('dialog');
  await dialog.getByLabel('Session sharing mode').selectOption('tab');
  await expect(dialog.getByRole('button',{name:'Start session',exact:true})).toBeDisabled();
  await dialog.getByRole('checkbox').nth(0).check();await dialog.getByRole('checkbox').nth(1).check();
  await dialog.getByRole('button',{name:'Start session',exact:true}).click();
  const mini=app.windows().find(w=>w.url().includes('view=mini'))!;
  expect(mini).toBeTruthy();
  await expect(mini.getByText('Session active · Capture unavailable')).toBeVisible();
  await expect(external.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  await external.getByRole('button',{name:'Pause',exact:true}).click();
  await expect(mini.getByText('Session paused · Capture unavailable')).toBeVisible();
  await expect(dashboard.getByRole('button',{name:'Resume',exact:true})).toBeVisible();
  await mini.getByRole('button',{name:'Resume',exact:true}).click();
  await mini.getByRole('button',{name:'Collapse companion'}).click();
  await expect(mini.getByRole('button',{name:'Expand companion'})).toBeVisible();
  await mini.getByRole('button',{name:'Expand companion'}).click();
  await mini.getByRole('button',{name:'Stop session',exact:true}).click();
  await expect(dashboard.locator('.history-row .tag').first()).toHaveText('stopped');
  await dashboard.getByRole('button',{name:'Desktop settings'}).click();
  await dashboard.getByLabel('Global shortcut').fill('Control+Shift+P');
  await dashboard.getByRole('button',{name:'Apply shortcut'}).click();
  await expect(dashboard.locator('.shortcut-keys')).toContainText('Control+Shift+P');
  // Real Electron native registration; no simulated input is presented as OS hotkey evidence.
  expect(await app.evaluate(({globalShortcut})=>globalShortcut.isRegistered('Control+Shift+P'))).toBe(true);
  if(process.env.PM_TEST_X11_INPUT==='1'){
   await mini.getByRole('button',{name:'Dismiss companion'}).click();
   execFileSync(process.env.PM_COPILOT_PYTHON||'.venv/bin/python',['scripts/test-x11-shortcut.py'],{env:process.env});
   await expect(mini.getByText('Shortcut received.')).toBeVisible();
   expect((await dashboard.evaluate(()=>window.copilot!.bootstrap())).native.lastTriggered).not.toBeNull();
  }
  const conflict=await app.evaluate(({globalShortcut})=>globalShortcut.register('Control+Alt+Q',()=>{}));
  expect(conflict).toBe(true);
  await dashboard.getByLabel('Global shortcut').fill('Control+Alt+Q');
  await dashboard.getByRole('button',{name:'Apply shortcut'}).click();
  await expect(dashboard.locator('.error-banner')).toContainText('unavailable');
  expect(await app.evaluate(({globalShortcut})=>globalShortcut.isRegistered('Control+Shift+P'))).toBe(true);
  await app.evaluate(({globalShortcut})=>globalShortcut.unregister('Control+Alt+Q'));
  // Verify renderer isolation and permission defaults on actual BrowserWindows.
  expect(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().every(w=>{const p=(w.webContents as unknown as {getLastWebPreferences():{contextIsolation:boolean;sandbox:boolean;nodeIntegration:boolean}}).getLastWebPreferences();return p.contextIsolation&&p.sandbox&&!p.nodeIntegration;}))).toBe(true);
  expect(await dashboard.evaluate(()=>typeof (window as unknown as {require?:unknown}).require)).toBe('undefined');
  expect(errors).toEqual([]);
  await app.close();app=undefined;
  const response=await external.request.get(config.origin+'/api/state').catch(()=>null);
  expect(response).toBeNull();
  app=await launch(data);
  const restored=await dashboardWindow(app);
  await expect(restored.getByText('Local service connected',{exact:true})).toBeVisible();
  await expect(restored.getByRole('heading',{name:'Platform release',exact:true})).toBeVisible();
  await expect(restored.locator('.history-row .tag').first()).toHaveText('stopped');
  await expect(restored.locator('.shortcut-keys')).toContainText('Control+Shift+P');
  await restored.getByRole('button',{name:'Delete selected project'}).click();
  await restored.getByRole('button',{name:'Delete permanently'}).click();
  await expect(restored.getByText('Your projects will appear here.')).toBeVisible();
  await expect(restored.getByRole('button',{name:'Start session',exact:true})).toBeDisabled();
 }finally{await app?.close();await browser.close();await fs.rm(data,{recursive:true,force:true});}
});

test('quitting stops a live session and closes the backend listener',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-quit-'));
 let app:ElectronApplication|undefined;
 try{
  app=await launch(data);
  const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,body?:unknown)=>{
   const r=await fetch(config.origin+'/api/'+route,{method:'POST',headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
   expect(r.ok).toBe(true);return r.json();
  };
  const state=await request('projects',{name:'Lifecycle check'});
  await request(`projects/${state.projects[0].id}/select`);
  await request('sessions',{consent:true,project_id:state.projects[0].id});
  await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  await app.close();app=undefined;
  await expect.poll(async()=>{try{await fetch(config.origin+'/api/state');return false;}catch{return true;}}).toBe(true);
  app=await launch(data);
  const restored=await dashboardWindow(app);
  await expect(restored.locator('.history-row .tag').first()).toHaveText('stopped');
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

test('open project dialogs retain their target when another view changes selection',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-scope-'));
 let app:ElectronApplication|undefined;
 try{
  app=await launch(data);
  const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,method='POST',body?:unknown)=>{
   const response=await fetch(config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
   expect(response.ok).toBe(true);return response.json();
  };
  const first=await request('projects','POST',{name:'Alpha'});
  const a=first.projects[0].id;
  const second=await request('projects','POST',{name:'Beta'});
  const b=second.projects.find((p:{name:string})=>p.name==='Beta').id;
  await request(`projects/${a}/select`);
  await page.getByRole('button',{name:'Rename',exact:true}).click();
  await page.getByLabel('Project name').fill('Alpha renamed');
  await request(`projects/${b}/select`);
  await page.getByRole('button',{name:'Save project'}).click();
  const state=await request('state','GET');
  expect(state.projects.find((p:{id:string})=>p.id===a).name).toBe('Alpha renamed');
  expect(state.projects.find((p:{id:string})=>p.id===b).name).toBe('Beta');
  await page.getByRole('button',{name:'Start session',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Session sharing mode').selectOption('tab');
  await page.getByRole('dialog').getByRole('checkbox').nth(0).check();await page.getByRole('dialog').getByRole('checkbox').nth(1).check();
  await request(`projects/${a}/select`);
  await page.getByRole('dialog').getByRole('button',{name:'Start session',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Project selection changed');
  expect((await request('state','GET')).session).toBeNull();
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

test('desktop crash closes the owned API and recovery marks the session interrupted',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-crash-'));
 let app:ElectronApplication|undefined;
 try{
  app=await launch(data);
  const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const headers={Authorization:'Bearer '+config.token,'Content-Type':'application/json'};
  const created=await fetch(config.origin+'/api/projects',{method:'POST',headers,body:JSON.stringify({name:'Crash recovery'})}).then(r=>r.json());
  const id=created.projects[0].id;
  await fetch(config.origin+`/api/projects/${id}/select`,{method:'POST',headers});
  await fetch(config.origin+'/api/sessions',{method:'POST',headers,body:JSON.stringify({consent:true,project_id:id})});
  const crashed=app;app=undefined;
  crashed.process().kill('SIGKILL');
  await expect.poll(async()=>{try{await fetch(config.origin+'/api/state',{signal:AbortSignal.timeout(1000)});return false;}catch{return true;}},{timeout:10000}).toBe(true);
  app=await launch(data);
  const restored=await dashboardWindow(app);
  await expect(restored.locator('.history-row .tag').first()).toHaveText('interrupted');
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

test('M3 transcript review and speaker edits are project scoped (text fixtures, no ASR claim)',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-transcript-'));
 let app:ElectronApplication|undefined;
 try{
  app=await launch(data);const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,body?:unknown)=>{
   const r=await fetch(config.origin+'/api/'+route,{method:'POST',headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
   expect(r.ok).toBe(true);return r.json();
  };
  const created=await request('projects',{name:'Alpha transcript'});const alpha=created.projects[0].id;
  await request(`projects/${alpha}/select`);const started=await request('sessions',{consent:true,project_id:alpha});const session=started.session.id;
  // Explicit text-only database fixture: never expose a fake-transcript production API.
  const fixture=`import sqlite3,sys,datetime
p,s=sys.argv[1:3]
db=sqlite3.connect(p)
for source,text,lang,start in [('remote','Alpha English fixture','en',0),('local','Алфа български текст','bg',3)]:
 sid=s+':'+source
 db.execute('INSERT INTO speakers(id,session_id,name) VALUES(?,?,?)',(sid,s,source))
 db.execute('INSERT INTO transcript_segments(session_id,source,start,end,text,language,speaker_id,segment_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(s,source,start,start+2,text,lang,sid,source,datetime.datetime.now(datetime.timezone.utc).isoformat()))
db.commit()
`;
  execFileSync(process.env.PM_COPILOT_PYTHON||(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'),['-c',fixture,path.join(data,'copilot.sqlite3'),session]);
  await request(`sessions/${session}/stop`);
  await expect(page.getByText('Alpha English fixture',{exact:true})).toBeVisible();
  await expect(page.getByText('Алфа български текст',{exact:true})).toBeVisible();
  await page.getByText('Rename or merge provisional speakers',{exact:true}).click();
  const row=page.locator('.speaker-edit').first();await row.locator('input').fill('Reviewed facilitator');
  await row.getByRole('button',{name:'Rename speaker',exact:true}).click();
  await expect(page.locator('.transcript-lines')).toContainText('Reviewed facilitator');
  const target=await row.locator('select option').nth(1).getAttribute('value');await row.locator('select').selectOption(target!);
  await row.getByRole('button',{name:'Merge',exact:true}).click();
  await expect(page.locator('.speaker-edit')).toHaveCount(1);
  await request('projects',{name:'Beta transcript'});
  await page.getByRole('button',{name:'Beta transcript',exact:true}).click();
  await expect(page.getByText('Alpha English fixture',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Alpha transcript',exact:true}).click();
  await expect(page.getByText('Alpha English fixture',{exact:true})).toBeVisible();
  await app.close();app=undefined;app=await launch(data);
  const restored=await dashboardWindow(app);await expect(restored.getByText('Alpha English fixture',{exact:true})).toBeVisible();
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

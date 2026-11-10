import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {launch,dashboardWindow} from './helpers';

test('M5 actual companion hides for unknown/broader sharing, survives shortcut, and settings persist',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m5-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(data);let page=await dashboardWindow(app);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  let config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,method='GET',body?:unknown)=>{
   const r=await fetch(config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});expect(r.ok).toBe(true);return r.json();
  };
  const visible=()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().includes('view=mini'))!.isVisible());
  expect((await request('sharing')).mode).toBe('unknown');
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));expect(await visible()).toBe(false);
  const panel=()=>page.getByRole('region',{name:'Screen and resources'});
  await panel().getByLabel('Declared sharing mode').selectOption('tab');
  await panel().getByLabel('I acknowledge this sharing mode and the tab-only workflow.').check();
  await panel().getByRole('button',{name:'Apply sharing mode',exact:true}).click();
  await expect(panel().getByRole('status')).toContainText('Companion allowed');
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));expect(await visible()).toBe(true);
  await panel().getByLabel('Declared sharing mode').selectOption('broader');
  await panel().getByRole('button',{name:'Apply sharing mode',exact:true}).click();
  await expect.poll(visible).toBe(false);
  await page.getByRole('button',{name:'Desktop settings'}).click();
  await page.getByLabel('Global shortcut').fill('Control+Shift+P');await page.getByRole('button',{name:'Apply shortcut'}).click();
  if(process.env.PM_TEST_X11_INPUT==='1')execFileSync(process.env.PM_COPILOT_PYTHON||'.venv/bin/python',['scripts/test-x11-shortcut.py'],{env:process.env});
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));expect(await visible()).toBe(false);
  // A browser/API mode change must also reach the native host's fail-closed check.
  await request('sharing','PUT',{mode:'none',acknowledged:true});
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));expect(await visible()).toBe(true);
  await request('sharing','PUT',{mode:'broader',acknowledged:true});await expect.poll(visible,{timeout:3000}).toBe(false);
  await request('sharing','PUT',{mode:'none',acknowledged:true});
  await page.evaluate(()=>window.copilot!.command({type:'mini',action:'show'}));expect(await visible()).toBe(true);
  await app.evaluate(()=>{
   const original=globalThis.fetch;(globalThis as unknown as {m5SavedFetch:typeof fetch}).m5SavedFetch=original;
   globalThis.fetch=((...args:Parameters<typeof fetch>)=>String(args[0]).endsWith('/api/sharing')?Promise.reject(new Error('Explicit test-only connection failure')):original(...args)) as typeof fetch;
  });
  await expect.poll(visible,{timeout:3000}).toBe(false);
  await app.evaluate(()=>{globalThis.fetch=(globalThis as unknown as {m5SavedFetch:typeof fetch}).m5SavedFetch;});
  await request('sharing','PUT',{mode:'broader',acknowledged:true});

  expect((await request('sharing')).capture_exclusion_verified).toBe(false);
  await request('projects','POST',{name:'Broader-mode session'});
  const pid=(await request('state')).projects[0].id;await request(`projects/${pid}/select`,'POST');
  await page.getByRole('button',{name:'Start session',exact:true}).click();
  const dialog=page.getByRole('dialog');await expect(dialog.getByLabel('Session sharing mode')).toHaveValue('broader');
  await dialog.getByRole('checkbox').nth(0).check();await dialog.getByRole('checkbox').nth(1).check();
  await dialog.getByRole('button',{name:'Start session',exact:true}).click();
  await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  expect((await request('sharing')).mode).toBe('broader');expect(await visible()).toBe(false);
  const sid=(await request('state')).session.id;await request(`sessions/${sid}/stop`,'POST');

  await panel().getByText('GPU scheduling and degraded mode',{exact:true}).click();
  await panel().getByLabel('VRAM reserve (MiB)').fill('3072');
  await panel().getByLabel('Use CPU for manual inference (four threads); defer optional vision/risks.').check();
  await panel().getByRole('button',{name:'Save resource settings'}).click();
  await expect.poll(async()=>(await request('resources')).settings.reserve_mib).toBe(3072);
  if(!(await request('screen')).available)await expect(panel().getByRole('button',{name:'Refresh windows'})).toBeDisabled();
  await panel().getByText('Verify Google Meet\'s sharing preview',{exact:true}).click();
  await expect(panel().getByText(/In Meet choose Present now/)).toBeVisible();
  expect(errors).toEqual([]);
  await app.close();app=undefined;app=await launch(data);page=await dashboardWindow(app);
  config=await page.evaluate(()=>window.copilot!.bootstrap());
  expect((await request('resources')).settings).toMatchObject({reserve_mib:3072,force_cpu:true});
  expect((await request('sharing')).mode).toBe('unknown');
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {launch,dashboardWindow} from './helpers';

test('computer setup requires download consent and exports performance metadata without a terminal',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'copilot-prepare-ui-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(directory);const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const wizard=page.getByRole('region',{name:'Setup wizard'});
  const prepare=wizard.getByRole('button',{name:'Set up this computer',exact:true});await expect(prepare).toBeDisabled();
  await wizard.getByLabel('I reviewed the model licenses and allow the one-time model downloads.').check();await expect(prepare).toBeEnabled();
  // No upstream downloads are started by this availability test.
  const target=path.join(directory,'performance.json');
  await app.evaluate(({dialog},file)=>{dialog.showSaveDialog=(async()=>({canceled:false,filePath:file})) as typeof dialog.showSaveDialog;},target);
  await page.getByRole('region',{name:'Audio and transcript'}).getByText('Transcription performance',{exact:true}).click();
  await page.getByRole('button',{name:'Download performance report',exact:true}).click();
  await expect.poll(async()=>fs.readFile(target,'utf8').then(text=>JSON.parse(text).schema).catch(()=>null)).toBe(1);
  const report=JSON.parse(await fs.readFile(target,'utf8'));expect(report).toHaveProperty('counts');expect(report.desktop_version).toBe('0.2.0');expect(report).not.toHaveProperty('projects');expect(report).not.toHaveProperty('transcript');
  const state=await page.evaluate(()=>window.copilot!.command({type:'engine-start'}));
  expect(state.shortcut).toBeTruthy();
 }finally{await app?.close();await fs.rm(directory,{recursive:true,force:true});}
});

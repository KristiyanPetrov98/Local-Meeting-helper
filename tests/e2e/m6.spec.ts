import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {launch,dashboardWindow} from './helpers';

test('M6 wizard uses real diagnostics, offline checks and explicit limited completion; acknowledgement persists',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m6-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(data);let page=await dashboardWindow(app);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const wizard=()=>page.getByRole('region',{name:'Setup wizard'});
  await expect(wizard().getByText('Keep the meeting on your device',{exact:true})).toBeVisible();
  await wizard().getByRole('button',{name:'Check this computer',exact:true}).click();
  await wizard().getByRole('button',{name:'Check hardware and dependencies',exact:true}).click();
  await expect(wizard().getByText(/logical CPUs/)).toBeVisible();
  await wizard().getByLabel('Setup Whisper size').selectOption('small');
  await wizard().getByLabel('Use CPU for manual generation',{exact:true}).check();
  await wizard().getByRole('button',{name:'Save setup configuration'}).click();
  await wizard().getByRole('button',{name:'3. Models',exact:true}).click();
  await expect(wizard().getByRole('button',{name:'Download approved model'})).toBeDisabled();
  await wizard().getByLabel('Setup model').selectOption('community-1');
  await expect(wizard().getByLabel('Hugging Face access token (this operation only)')).toBeVisible();
  await expect(wizard().getByRole('button',{name:'Import approved local snapshot'})).toBeDisabled();
  await wizard().getByRole('button',{name:'4. Audio & screen',exact:true}).click();
  await wizard().getByRole('button',{name:'Inspect live capture evidence'}).click();
  await expect(wizard().locator('pre').filter({hasText:'Start a consented live test session'})).toBeVisible();
  await wizard().getByRole('button',{name:'5. Offline tests',exact:true}).click();
  await wizard().getByRole('button',{name:'Run offline self-tests'}).click();
  await expect(wizard().getByText('Bundled parser process · passed',{exact:true})).toBeVisible({timeout:30000});
  await expect(wizard().getByText('Offline Whisper model load · blocked',{exact:true})).toBeVisible();
  await expect(wizard().getByText('This run has unmet requirements.',{exact:false})).toBeVisible();
  await wizard().getByRole('button',{name:'6. Device benchmark',exact:true}).click();
  await expect(wizard().getByRole('button',{name:'Run device benchmark',exact:true})).toBeDisabled();
  await wizard().getByRole('button',{name:'7. Finish',exact:true}).click();
  await wizard().getByLabel('I understand local storage and retention.').check();
  await wizard().getByLabel('I understand the tab-sharing limitation and preview workflow.').check();
  await wizard().getByRole('button',{name:'Acknowledge setup',exact:true}).click();
  await expect(wizard().getByRole('alert')).toContainText('incomplete');
  await wizard().getByLabel('Continue with limited capabilities if required tests are incomplete.').check();
  await wizard().getByRole('button',{name:'Acknowledge setup',exact:true}).click();
  await expect(wizard().getByText('Setup acknowledged.',{exact:false})).toBeVisible();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());expect(JSON.stringify(config)).not.toContain('desktop_capability');
  const status=await fetch(config.origin+'/api/setup',{headers:{Authorization:'Bearer '+config.token}}).then(r=>r.json());
  expect(status.acknowledgement).toMatchObject({limited:true,release_qualified:false});expect(status.selected_profile).toBeNull();
  expect(errors).toEqual([]);
  await app.close();app=undefined;app=await launch(data);page=await dashboardWindow(app);
  await expect(wizard().getByRole('button',{name:'Open setup',exact:true})).toBeVisible();
  await wizard().getByRole('button',{name:'Open setup',exact:true}).click();
  await wizard().getByRole('button',{name:'2. Hardware',exact:true}).click();
  await expect(wizard().getByLabel('Setup Whisper size')).toHaveValue('small');
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

test('M6 desktop-authorized directory import uses actual worker and reports files without claiming inference',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m6-import-'));const source=path.join(data,'explicit-snapshot-fixture');let app:ElectronApplication|undefined;
 try{
  await fs.mkdir(source);await fs.writeFile(path.join(source,'model.bin'),'NON-WORKING TEST WEIGHTS');
  await fs.writeFile(path.join(source,'config.json'),'{}');await fs.writeFile(path.join(source,'tokenizer.json'),'{}');
  app=await launch(data);const page=await dashboardWindow(app);await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const wizard=page.getByRole('region',{name:'Setup wizard'});
  await wizard.getByRole('button',{name:'3. Models',exact:true}).click();await wizard.getByLabel('Setup model').selectOption('whisper-tiny');
  await wizard.getByLabel("I reviewed this model's license/access conditions and trust the approved upstream snapshot.").check();
  // Explicit native-picker fixture, confined to this disposable test profile.
  await app.evaluate(({dialog},directory)=>{dialog.showOpenDialog=(async()=>({canceled:false,filePaths:[directory]})) as typeof dialog.showOpenDialog;},source);
  await wizard.getByRole('button',{name:'Import approved local snapshot'}).click();
  await expect(wizard.getByText('Managed snapshot files present. Runtime and quality still need testing.',{exact:true})).toBeVisible({timeout:15000});
  const config=await page.evaluate(()=>window.copilot!.bootstrap());const status=await fetch(config.origin+'/api/setup',{headers:{Authorization:'Bearer '+config.token}}).then(r=>r.json());
  expect(status.runs[0].report).toMatchObject({files_installed:true,inference_verified:false});
  const forbidden=await fetch(config.origin+'/api/setup/import',{method:'POST',headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:JSON.stringify({model_id:'whisper-tiny',source,license_acknowledged:true})});
  expect(forbidden.status).toBe(403);
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

import {test,expect,_electron as electron,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {dashboardWindow} from './helpers';

test('M6 packaged app starts outside checkout without Python/Node on PATH and runs bundled workers',async()=>{
 test.skip(!process.env.PM_PACKAGED_APP,'Build the platform-specific package and set PM_PACKAGED_APP.');
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'pm-installed-smoke-'));let app:ElectronApplication|undefined;
 try{
  const binary=path.resolve(process.env.PM_PACKAGED_APP!);const source=path.join(directory,'snapshot');await fs.mkdir(source);
  await fs.writeFile(path.join(source,'model.bin'),'EXPLICIT NON-WORKING TEST WEIGHTS');await fs.writeFile(path.join(source,'config.json'),'{}');await fs.writeFile(path.join(source,'tokenizer.json'),'{}');
  app=await electron.launch({executablePath:binary,args:[],cwd:directory,env:{...process.env,PATH:path.dirname(binary),PM_COPILOT_DATA_DIR:path.join(directory,'profile'),PM_COPILOT_PYTHON:'/must-not-use-python'}});
  const page=await dashboardWindow(app);await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  expect(await app.evaluate(({app})=>app.isPackaged)).toBe(true);
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const request=async(route:string,method='GET',body?:unknown)=>{
   const response=await fetch(config.origin+'/api/'+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});expect(response.ok).toBe(true);return response.json();
  };
  expect((await request('setup/diagnostics')).bundled).toBe(true);
  const p=(await request('projects','POST',{name:'Installed app check'})).projects[0].id;await request(`projects/${p}/select`,'POST');
  const upload=await fetch(config.origin+`/api/projects/${p}/documents?filename=installed.txt`,{method:'POST',headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/octet-stream'},body:'The packaged release is Friday.'});expect(upload.status).toBe(202);
  await expect.poll(async()=>(await request(`projects/${p}/documents`)).documents[0].chunk_count,{timeout:15000}).toBeGreaterThan(0);
  const result=await request(`projects/${p}/knowledge/search`,'POST',{query:'release',mode:'lexical'});expect(result.hits[0].citation.quote).toBe('The packaged release is Friday.');
  const wizard=page.getByRole('region',{name:'Setup wizard'});await wizard.getByRole('button',{name:'3. Models',exact:true}).click();await wizard.getByLabel('Setup model').selectOption('whisper-tiny');
  await wizard.getByLabel("I reviewed this model's license/access conditions and trust the approved upstream snapshot.").check();
  await app.evaluate(({dialog},directory)=>{dialog.showOpenDialog=(async()=>({canceled:false,filePaths:[directory]})) as typeof dialog.showOpenDialog;},source);
  await wizard.getByRole('button',{name:'Import approved local snapshot'}).click();
  await expect(wizard.getByText('Managed snapshot files present. Runtime and quality still need testing.',{exact:true})).toBeVisible({timeout:15000});
  expect((await request('setup')).runs[0].report.inference_verified).toBe(false);
  await app.close();app=undefined;
  await expect.poll(async()=>{try{await fetch(config.origin+'/api/state');return false;}catch{return true;}}).toBe(true);
 }finally{await app?.close();await fs.rm(directory,{recursive:true,force:true});}
});

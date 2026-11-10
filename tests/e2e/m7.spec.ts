import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {launch,dashboardWindow} from './helpers';

test('M7 qualification controls report real availability and never certify an idle app',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-m7-'));let app:ElectronApplication|undefined;
 try{
  app=await launch(data);const page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'6. Device benchmark',exact:true}).click();
  const panel=page.getByLabel('Release qualification');
  await expect(panel.getByText(/0 samples · idle/)).toBeVisible();
  for(const name of ['Start qualification recording','Finish qualification recording','Download qualification metrics'])
   await expect(panel.getByRole('button',{name,exact:true})).toBeDisabled();
  const config=await page.evaluate(()=>window.copilot!.bootstrap());
  const result=await fetch(config.origin+'/api/qualification/start',{method:'POST',headers:{Authorization:'Bearer '+config.token}});
  expect(result.status).toBe(409);
  const report=await fetch(config.origin+'/api/qualification/report',{headers:{Authorization:'Bearer '+config.token}});
  expect(report.status).toBe(409);
  const status=await fetch(config.origin+'/api/qualification',{headers:{Authorization:'Bearer '+config.token}}).then(r=>r.json());
  expect(status).toMatchObject({phase:'idle',sample_count:0,release_qualified:false});
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

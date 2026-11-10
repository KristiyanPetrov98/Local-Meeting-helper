import {test,expect,type ElectronApplication} from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {launch,dashboardWindow} from './helpers';

test('M2 real upload, drag/drop, indexing, citations, revisions, scoped search and deletion',async()=>{
 const data=await fs.mkdtemp(path.join(os.tmpdir(),'pm-copilot-documents-'));
 let app:ElectronApplication|undefined;
 try{
  app=await launch(data);let page=await dashboardWindow(app);
  await expect(page.getByText('Local service connected',{exact:true})).toBeVisible();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.getByRole('button',{name:'Create project',exact:true}).click();
  await page.getByLabel('Project name').fill('M2 Alpha');await page.getByRole('button',{name:'Save project'}).click();
  await page.getByRole('button',{name:'M2 Alpha',exact:true}).click();
  const panel=()=>page.getByRole('region',{name:'Project knowledge',exact:true});
  const first='# Roadmap\nrelease date: Friday\nALPHA_SECRET is project scoped.\n<script>window.__pmInjected=true</script>\nupdated_at: 2026-01-01\n';
  await panel().getByLabel('Upload project documents').setInputFiles({name:'roadmap.md',mimeType:'text/markdown',buffer:Buffer.from(first)});
  await expect(panel().locator('.document-row').filter({hasText:'roadmap.md'})).toContainText('1 chunk',{timeout:15000});
  await panel().getByLabel('Knowledge search mode').selectOption('lexical');
  await panel().getByLabel('Search project knowledge').fill('ALPHA_SECRET');
  await panel().getByRole('button',{name:'Search documents',exact:true}).click();
  await expect(panel().locator('.search-hit')).toHaveCount(1);
  await panel().getByRole('button',{name:'View citation',exact:true}).click();
  await expect(panel().getByRole('region',{name:'Verified source preview'})).toContainText('release date: Friday');
  expect(await page.evaluate(()=>typeof (window as unknown as {__pmInjected?:unknown}).__pmInjected)).toBe('undefined');
  const cid=(await panel().locator('.citation-preview').innerText()).match(/cite_[a-f0-9]{64}/)![0];
  let config=await page.evaluate(()=>window.copilot!.bootstrap());
  const projects=await fetch(config.origin+'/api/state',{headers:{Authorization:'Bearer '+config.token}}).then(r=>r.json());
  const alpha=projects.selected_project_id;
  // A changed file creates a retained source revision; it does not overwrite issued citations.
  await panel().getByLabel('Upload project documents').setInputFiles({name:'roadmap.md',mimeType:'text/markdown',buffer:Buffer.from(first.replace('Friday','Monday').replace('2026-01-01','2026-02-01'))});
  await expect(panel().locator('.document-row')).toContainText('revision 2');
  await expect(panel().locator('.document-row')).toContainText('1 chunk',{timeout:15000});
  const earlier=await fetch(config.origin+`/api/projects/${alpha}/citations/${cid}`,{headers:{Authorization:'Bearer '+config.token}}).then(r=>r.json());
  expect(earlier.superseded).toBe(true);expect(earlier.quote).toContain('Friday');
  // Drag/drop uses the real File/DataTransfer and upload route, not a fake index fixture.
  await page.evaluate(()=>{
   const transfer=new DataTransfer();transfer.items.add(new File(['DROP_EVIDENCE is local and searchable.'],'drop.txt',{type:'text/plain'}));
   document.querySelector('.document-drop')!.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));
  });
  await expect(panel().locator('.document-row').filter({hasText:'drop.txt'})).toContainText('1 chunk',{timeout:15000});
  await page.getByRole('button',{name:'New project',exact:true}).click();
  await page.getByLabel('Project name').fill('M2 Beta');await page.getByRole('button',{name:'Save project'}).click();
  await page.getByRole('button',{name:'M2 Beta',exact:true}).click();
  await expect(panel().locator('.document-row')).toHaveCount(0);
  await panel().getByLabel('Search project knowledge').fill('ALPHA_SECRET');await panel().getByRole('button',{name:'Search documents',exact:true}).click();
  await expect(panel().getByText('No matching evidence in this project.',{exact:true})).toBeVisible();
  expect(await panel().locator('.citation-preview').count()).toBe(0);
  await page.getByRole('button',{name:'M2 Alpha',exact:true}).click();
  await app.close();app=undefined;app=await launch(data);page=await dashboardWindow(app);
  await expect(panel().locator('.document-row')).toHaveCount(2);
  await panel().getByLabel('Knowledge search mode').selectOption('lexical');await panel().getByLabel('Search project knowledge').fill('Monday');
  await panel().getByRole('button',{name:'Search documents',exact:true}).click();await expect(panel().locator('.search-hit')).toHaveCount(1);
  await panel().locator('.document-row').filter({hasText:'roadmap.md'}).getByRole('button',{name:'Delete document',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Delete all revisions',exact:true}).click();
  await expect(panel().locator('.document-row')).toHaveCount(1);
  config=await page.evaluate(()=>window.copilot!.bootstrap());
  const removed=await fetch(config.origin+`/api/projects/${alpha}/citations/${cid}`,{headers:{Authorization:'Bearer '+config.token}});
  expect(removed.status).toBe(404);expect(errors).toEqual([]);
 }finally{await app?.close();await fs.rm(data,{recursive:true,force:true});}
});

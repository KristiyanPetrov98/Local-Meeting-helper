import {expect,_electron as electron,type ElectronApplication,type Page} from '@playwright/test';
export async function launch(data:string){
 return electron.launch({args:['.'],env:{...process.env,PM_COPILOT_DATA_DIR:data}});
}
export async function dashboardWindow(app:ElectronApplication):Promise<Page>{
 await app.firstWindow();
 await expect.poll(()=>app.windows().filter(w=>w.url().startsWith('http://')&&!w.url().includes('view=mini')).length).toBe(1);
 return app.windows().find(w=>w.url().startsWith('http://')&&!w.url().includes('view=mini'))!;
}

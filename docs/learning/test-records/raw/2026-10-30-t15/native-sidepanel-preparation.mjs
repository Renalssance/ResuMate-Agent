import { chromium } from '/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent/node_modules/playwright/index.mjs';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
const API='http://127.0.0.1:4174';
const auth=await fetch(`${API}/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'browser-fixture',password:'synthetic-browser-password'})});
if(!auth.ok)throw new Error('Fixture login failed');
const token=(await auth.json()).access_token;
async function api(path,data,method=data?'POST':'GET'){
 const response=await fetch(API+path,{method,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},...(data?{body:JSON.stringify(data)}:{})});
 if(!response.ok)throw new Error(`Fixture HTTP ${response.status} ${path}`);
 return response.json();
}
const run=await api('/api/agent/runs',{kind:'tailoring',jdId:1,resumeId:1,requestId:crypto.randomUUID()});
async function wait(status){
 for(let i=0;i<120;i++){
  const current=await api('/api/agent/runs/'+run.runId);
  if(current.status===status)return current;
  await new Promise(resolve=>setTimeout(resolve,250));
 }
 throw new Error('Fixture Run timeout');
}
const paused=await wait('waiting_input');
await api(`/api/agent/runs/${run.runId}/actions/${paused.actions[0].actionId}`,{decision:'submit',answers:{answer:'负责 API 与数据库设计。'},expectedRevision:1});
const done=await wait('succeeded');
const version=await api('/api/resume-versions/'+done.outputRefs[0].id);
const editedText='本人确认：负责 API 与数据库设计，核对接口需求并完成联调。';
await api('/api/resume-versions/'+version.id,{expectedRevision:1,changes:version.structuredContent.changes.map(change=>({id:change.id,status:change.section.startsWith('/work_experience')?'edited':'rejected',...(change.section.startsWith('/work_experience')?{editedText}:{})}))},'PATCH');
await api('/api/resume-versions/'+version.id+'/confirm',{expectedRevision:2});
const profile=mkdtempSync(join(tmpdir(),'resumate-t15-native-profile-'));
const source=process.env.RESUMATE_EXTENSION_PATH;
if(!source)throw new Error('Packaged extension path required');
const browser=await chromium.launchPersistentContext(profile,{channel:'chromium',headless:false,viewport:null,args:[`--disable-extensions-except=${source}`,`--load-extension=${source}`,'--window-size=1440,1000']});
try{
 const worker=browser.serviceWorkers()[0]||await browser.waitForEvent('serviceworker');
 const id=new URL(worker.url()).host;
 const target=browser.pages()[0];
 await target.goto('http://127.0.0.1:8899/extension/fixtures/job-detail.html?native=true');
 const panel=await browser.newPage();
 await panel.goto(`chrome-extension://${id}/sidepanel/sidepanel.html`);
 await panel.locator('#languageZhBtn').click();
 await panel.locator('.settings-card').evaluate(node=>{node.open=true});
 await panel.locator('#apiBaseInput').fill(API);
 await panel.locator('#usernameInput').fill('browser-fixture');
 await panel.locator('#passwordInput').fill('synthetic-browser-password');
 await panel.locator('#loginBtn').click();
 await panel.locator(`#profileSelect option[value="version:${version.id}"]`).waitFor({state:'attached'});
 await panel.locator('#profileSelect').selectOption(`version:${version.id}`);
 await panel.close();
 await target.bringToFront();
 writeFileSync('/tmp/resumate-t15-native-context.json',JSON.stringify({extensionId:id,versionId:version.id,editedText,profile,source,executable:chromium.executablePath()},null,2));
 console.log('Native Chromium ready. Packaged extension loaded; fixture version prepared; no application submitted.');
 await new Promise(resolve=>{process.once('SIGTERM',resolve);process.once('SIGINT',resolve)});
}finally{await browser.close();rmSync(profile,{recursive:true,force:true});}

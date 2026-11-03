import { chromium, expect } from '@playwright/test';
import { mkdirSync,copyFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const base='http://127.0.0.1:8078';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
 const comps=await (await page.request.get(base+'/api/public/registration-rosters')).json();const c=comps.find(x=>x.registration_mode==='individual');
 await page.goto(base+'/register/'+c.id);
 const roster=page.getByRole('region',{name:'比賽報名名單',exact:true});
 await expect(roster.getByRole('heading',{name:'正取（2 人）',exact:true})).toBeVisible();
 await expect(roster.getByText('陳先生',{exact:true})).toHaveCount(2);await expect(roster.getByText('老師',{exact:true})).toBeVisible();await expect(roster.getByText('學生',{exact:true})).toBeVisible();
 const before=await (await page.request.get(base+`/api/public/competitions/${c.id}/registrations`)).json();
 if(!before.entries.some(x=>x.name==='蔡先生')){
  await page.getByLabel('搜尋姓名',{exact:true}).fill('蔡先生');await page.getByRole('button',{name:'蔡先生 無辨識註記',exact:true}).click();
  await page.getByRole('button',{name:'確認以 蔡先生 報名',exact:true}).click();await expect(page.getByRole('region',{name:'報名結果'})).toBeVisible();
 }
 await expect(roster.getByRole('region',{name:'候補名單',exact:true}).getByText('蔡先生',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'更新名單',exact:true}).click();await expect(page.getByRole('button',{name:'更新名單',exact:true})).toBeEnabled();
 const data=await (await page.request.get(base+`/api/public/competitions/${c.id}/registrations`)).json();assert(data.entries.every(e=>Object.keys(e).sort().join()==='distinguishing_note,name,queue_sequence,status'));
 mkdirSync('public/help',{recursive:true});await roster.screenshot({path:'public/help/roster.png'});copyFileSync('public/help/roster.png','../data/help-preview/static/help/roster.png');
 await page.setViewportSize({width:390,height:844});await page.reload();await expect(roster.getByText('蔡先生',{exact:true})).toBeVisible();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 // Verify the read-only closed-state UI against an explicit closed response.
 await page.route('**/api/public/registration-rosters',async route=>{const r=await route.fetch();const rows=await r.json();await route.fulfill({response:r,json:rows.map(x=>x.id===c.id?{...x,effective_registration_open:false}:x)});});
 await page.route(`**/api/public/competitions/${c.id}/registrations`,async route=>{const r=await route.fetch();const v=await r.json();await route.fulfill({response:r,json:{...v,competition:{...v.competition,effective_registration_open:false}}});});
 await page.reload();await expect(page.getByText('報名已截止，仍可查看下方名單。',{exact:true})).toBeVisible();await expect(page.getByLabel('搜尋姓名',{exact:true})).toHaveCount(0);await expect(roster.getByText('蔡先生',{exact:true})).toBeVisible();
 assert.deepEqual(errors,[]);console.log('PASS: anonymous confirmed/waitlist, duplicate-name notes, post-registration live refresh, manual refresh, privacy, mobile and closed-state UI');
} finally {await browser.close();}

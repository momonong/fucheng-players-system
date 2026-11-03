import { chromium } from '@playwright/test';
import { readFileSync,copyFileSync,mkdirSync } from 'node:fs';
import assert from 'node:assert/strict';
const origin='http://127.0.0.1:8078';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
async function shot(name,path){await page.goto(origin+path);await page.locator('main').waitFor();await page.waitForLoadState('networkidle');await page.screenshot({path:`src/assets/help/${name}.png`});mkdirSync('../data/help-preview/static/help',{recursive:true});copyFileSync(`src/assets/help/${name}.png`,`../data/help-preview/static/help/${name}.png`);}
try {
 await page.goto(origin);await page.getByRole('heading',{name:'最新公告',exact:true}).waitFor();await page.getByRole('link',{name:'使用說明',exact:true}).waitFor();
 assert.equal(await page.getByRole('link',{name:'管理後台',exact:true}).isVisible(),false);
 await page.getByLabel('更多選項').click();await page.getByRole('link',{name:'管理後台',exact:true}).waitFor();await page.keyboard.press('Escape');assert.equal(await page.getByRole('link',{name:'管理後台',exact:true}).isVisible(),false);
 await page.goto(origin+'/help');await page.waitForLoadState('networkidle');await page.screenshot({path:'src/assets/help/help-button.png',clip:{x:860,y:10,width:560,height:70}});mkdirSync('../data/help-preview/static/help',{recursive:true});copyFileSync('src/assets/help/help-button.png','../data/help-preview/static/help/help-button.png');
 await shot('home','/');await shot('members','/members');assert.equal(await page.getByText('陳先生',{exact:true}).count(),2);await page.getByText('老師',{exact:true}).waitFor();await page.getByText('學生',{exact:true}).waitFor();await shot('competitions','/competitions');
 const schedule=await (await page.request.get(origin+'/api/public/schedule')).json();
 for(const mode of ['individual','doubles'])await shot(mode,'/register/'+schedule.find(s=>s.registration_mode===mode).id);
 await shot('login','/admin');
 const c=JSON.parse(readFileSync('../data/help-preview/credential.json','utf8'));
 await page.getByLabel('帳號',{exact:true}).fill(c.username);await page.getByLabel('密碼',{exact:true}).fill(c.password);await page.getByRole('button',{name:'登入',exact:true}).click();await page.getByRole('button',{name:'登出',exact:true}).waitFor();
 await shot('admin-members','/admin');await shot('admin-competitions','/admin/competitions');await shot('admin-news','/admin/announcements');
 await page.goto(origin+'/help');await page.getByRole('heading',{name:'跟著畫面，一步一步來。'}).waitFor();assert.equal(await page.locator('.help-step').count(),10);assert.equal(await page.getByRole('link',{name:'會員使用 ↓'}).getAttribute('href'),'/help#members-help');
 for(const img of await page.locator('.help-step img').all()){await img.scrollIntoViewIfNeeded();await page.waitForFunction(()=>[...document.querySelectorAll('.help-step img')].filter(e=>e.getBoundingClientRect().top<innerHeight&&e.getBoundingClientRect().bottom>0).every(e=>e.complete&&e.naturalWidth>0));}
 assert.equal((await page.locator('main').innerText()).includes('硬分級'),false);assert.equal((await page.locator('main').innerText()).includes('不用登入'),false);await page.getByText('查名單、查看比賽與協助其他人報名。',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});await page.goto(origin+'/help');await page.getByRole('heading',{name:'跟著畫面，一步一步來。'}).waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.getByLabel('更多選項').click();await page.getByRole('link',{name:'管理後台',exact:true}).waitFor();const menu=await page.locator('.nav-more-popover').boundingBox();assert(menu&&menu.x>=0&&menu.x+menu.width<=390);await page.screenshot({path:'../data/help-preview/mobile-help.png'});
 assert.deepEqual(errors,[]);console.log('PASS: navigation/menu, 10 screenshots, mobile width, no page errors');
} finally {await browser.close();}

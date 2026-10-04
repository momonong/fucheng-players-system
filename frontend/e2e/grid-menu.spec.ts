import { writeFile } from 'node:fs/promises'
import { expect, test, type Page, type TestInfo } from '@playwright/test'

async function setup(page: Page, info: TestInfo, suffix: string, count=4) {
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號',{exact:true}).fill(`e2e-${suffix.startsWith("axis-")?"axis":suffix.startsWith("edit-")?"edit":"grid"}-${info.project.name}`)
  await page.getByLabel('密碼',{exact:true}).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button',{name:'登入',exact:true}).click()
  await expect(page.getByRole('heading',{name:'比賽',exact:true})).toBeVisible()
  const me=await (await page.request.get('/api/auth/me')).json(), headers={'X-CSRF-Token':me.csrf_token}
  const name=`格位-${info.project.name}-${suffix}`
  const payload={name,competition_date:'2099-09-20',registration_deadline:'2099-09-19T00:00:00+08:00',capacity:count,status:'open',notes:'合成格位測試'}
  const comp=await (await page.request.post('/api/admin/competitions',{headers,data:payload})).json()
  const other=await (await page.request.post('/api/admin/competitions',{headers,data:{...payload,name:name+'另一場'}})).json()
  const rows: any[]=[]
  for(let i=0;i<count;i++) {
    const m=await (await page.request.post('/api/admin/members',{headers,data:{name:`格位選手${String(i).padStart(3,'0')}`,distinguishing_note:`合成${suffix}`,level:i%10+1,diet:'omnivore',is_active:true}})).json()
    const r=await page.request.post(`/api/admin/competitions/${comp.id}/registrations`,{headers,data:{member_id:m.id,diet:i%3===0?'vegetarian':i%3===1?'omnivore':'unset',request_id:crypto.randomUUID()}})
    expect(r.status()).toBe(201);rows.push(await r.json())
  }
  await page.reload()
  const area=page.getByRole('region',{name:'當次比賽級數安排'})
  const choose=async(second=false)=>{ await page.getByLabel('選擇比賽',{exact:true}).selectOption(second?other.id:comp.id);await expect(area.getByRole('heading',{name:second?other.name:comp.name,exact:true})).toBeVisible();await expect(area.locator('.arrangement-cell')).toHaveCount(second?0:count) }
  await choose()
  const endpoint=`/api/admin/competitions/${comp.id}/arrangement`
  const state=async()=>await (await page.request.get(endpoint)).json()
  await expect.poll(async()=>!!(await state()).layout).toBe(true)
  const cell=(i:number)=>area.locator(`[data-registration-id="${rows[i].id}"]`)
  const slot=(point:any)=>area.locator(`[data-grid-cell="${point.row_id}/${point.column_id}"]`)
  const op=async(operation:any)=>{const current=await state();const res=await page.request.post(endpoint+'/operations',{headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,operation}});expect(res.status()).toBe(200);return res.json()}
  const reload=async()=>{await choose(true);const loaded=page.waitForResponse(r=>r.url().endsWith(endpoint)&&r.request().method()==='GET');await choose();await loaded;if((await state()).editable)await expect(area.locator('.cell-grip').first()).toBeEnabled()}
  const idle=async()=>{await expect(area.locator('.cell-grip').first()).toBeEnabled();await expect(area.locator('.arrangement-recovery')).toHaveCount(0)}
  const save=async(label='格位版本')=>{await area.getByRole('button',{name:'保存完整安排',exact:true}).click();const dialog=page.getByRole('dialog',{name:'保存完整安排'});await dialog.getByLabel('版本名稱').fill(label);await dialog.getByRole('button',{name:'保存',exact:true}).click()}
  return {comp,other,headers,rows,area,endpoint,state,cell,slot,op,reload,idle,choose,save}
}
const point=(layout:any,row:number,col:number)=>({row_id:layout.rows[row].id,column_id:layout.columns[col].id})
const position=(layout:any,rid:string)=>{const c=layout.cells.find((v:any)=>v.registration_id===rid);return {row_id:c.row_id,column_id:c.column_id}}

const activate=(info:TestInfo,locator:any)=>info.project.name==='mobile'?locator.tap():locator.click()
const menu=(page:Page)=>page.getByRole('dialog',{name:'儲存格操作',exact:true})
async function openMenu(page:Page,info:TestInfo,s:any,cell:any,preserve=false){
  if(info.project.name==='desktop')await cell.click({button:'right'})
  else {if(!preserve)await cell.tap();await s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}).tap()}
  try{await expect(menu(page)).toBeVisible()}catch(error){await page.screenshot({path:info.outputPath('menu-failed.png'),fullPage:true});throw error}
}
async function selectRange(page:Page,info:TestInfo,s:any,a:any,b:any){
  if(info.project.name==='mobile'){
    await a.tap();await openMenu(page,info,s,a,true);await menu(page).getByRole('button',{name:'範圍選取',exact:true}).tap();await b.tap()
  }else{
    const x=(await a.boundingBox())!,y=(await b.boundingBox())!
    await page.mouse.move(x.x+x.width/2,x.y+x.height/2);await page.mouse.down();await page.mouse.move(y.x+y.width/2,y.y+y.height/2,{steps:8});await page.mouse.up()
  }
}
async function color(page:Page,info:TestInfo,s:any,shade:number){
  await activate(info,menu(page).getByRole('button',{name:shade?`淺灰 ${shade}`:'白色',exact:true}));await s.idle()
}
async function download(page:Page,info:TestInfo,s:any,name:string,snapshot:any){
  const pending=page.waitForEvent('download');await activate(info,s.area.getByRole('button',{name:'匯出 Excel',exact:true}));const file=await pending
  await file.saveAs(info.outputPath(name+'.xlsx'));await writeFile(info.outputPath(name+'.json'),JSON.stringify(snapshot,null,2))
}

test('F表頭與資料共用選單、真框選、編字合併及stable欄邊界',async({page},info)=>{
  const s=await setup(page,info,'edit-menu-header',3),before=await s.state(),headers=s.area.locator('[data-grid-header]')
  await expect(s.area.getByRole('toolbar',{name:'表格編輯工具'})).toHaveCount(0)
  await expect(headers.first()).toHaveCSS('background-color','rgb(255, 255, 255)')
  if(info.project.name==='mobile'){
    const beforeOpen=await s.state(),writes:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
    await openMenu(page,info,s,headers.first());await expect(menu(page)).toBeVisible();expect(writes).toHaveLength(0)
    const afterOpen=await s.state();expect(afterOpen.layout_revision).toBe(beforeOpen.layout_revision);expect(afterOpen.state_token).toBe(beforeOpen.state_token)
    await color(page,info,s,2)
    await expect(headers.first()).toHaveAttribute('data-header-shade','2')
    const outside=page.getByRole('navigation',{name:'比賽工作區'}).getByRole('heading',{name:'比賽',exact:true})
    await activate(info,outside);await expect(menu(page)).toHaveCount(0)
    await openMenu(page,info,s,headers.first());await expect(menu(page)).toBeVisible();await page.keyboard.press('Escape');await expect(menu(page)).toHaveCount(0)
    return
  }
  await selectRange(page,info,s,headers.nth(0),headers.nth(1));await expect(s.area.locator('.grid-selected')).toHaveCount(2)
  await openMenu(page,info,s,headers.nth(1),true);await expect(s.area.locator('.grid-selected')).toHaveCount(2)
  await expect(menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:'復原上一個動作',exact:true})).toBeVisible()
  await color(page,info,s,2);await color(page,info,s,0)
  await expect(headers.nth(0)).toHaveCSS('background-color','rgb(255, 255, 255)')
  const writes:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  await color(page,info,s,0);expect(writes).toHaveLength(0)
  await activate(info,menu(page).getByRole('button',{name:'合併儲存格',exact:true}));await s.idle()
  await expect(headers.first()).toHaveAttribute('colspan','2');await expect(headers.first()).toHaveText('1 級 2 級')
  await headers.first().getByRole('button').dblclick();await page.getByLabel('直接編輯文字').fill('甲乙組');await page.getByLabel('直接編輯文字').press('Enter')
  await s.idle();await expect(headers.first()).toHaveText('甲乙組')
  const merged=await s.state();expect(merged.layout.columns[0].title).toBe('甲乙組');expect(merged.rows).toEqual(before.rows)
  await openMenu(page,info,s,headers.first());await page.screenshot({path:info.outputPath('header-context-screen.png'),fullPage:true})
  await page.keyboard.press('Escape');await expect(menu(page)).toHaveCount(0)
  await activate(info,s.area.getByRole('button',{name:'在第 3 欄左方插入文字欄',exact:true}));await s.idle()
  const inserted=await s.state();expect(inserted.layout.columns[2].kind).toBe('text');expect(inserted.layout.columns[3].id).toBe(before.layout.columns[2].id)
  await openMenu(page,info,s,headers.first());await activate(info,menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:'復原上一個動作',exact:true}));await s.idle()
  expect((await s.state()).layout.columns.map((c:any)=>c.id)).toEqual(before.layout.columns.map((c:any)=>c.id))
  await openMenu(page,info,s,headers.first());await activate(info,menu(page).getByRole('button',{name:'解除合併儲存格',exact:true}));await s.idle()
  await expect(headers.first()).toHaveText('甲乙組');await expect(headers.nth(1)).toHaveText('2 級')
  const empty=s.slot(point(before.layout,3,0));await openMenu(page,info,s,empty)
  await expect(menu(page).getByRole('button',{name:'編輯文字',exact:true})).toBeEnabled()
  await page.getByRole('navigation',{name:'比賽工作區'}).getByRole('heading',{name:'比賽',exact:true}).click();await expect(menu(page)).toHaveCount(0);await empty.getByRole('button').dblclick();await page.getByLabel('直接編輯文字').fill('空格文字');await page.getByLabel('直接編輯文字').press('Enter')
  await s.idle();await expect(empty).toHaveText('空格文字')
  await empty.getByRole('button').focus();await page.keyboard.press('Shift+F10');await expect(menu(page)).toBeVisible();await page.keyboard.press('Escape');await expect(menu(page)).toHaveCount(0)
})

test('F桌面與觸控選單可由外部點擊及Escape關閉',async({page},info)=>{
  const s=await setup(page,info,'edit-menu-close',1),state=await s.state(),cell=s.slot(point(state.layout,3,0))
  const outside=page.getByRole('navigation',{name:'比賽工作區'}).getByRole('heading',{name:'比賽',exact:true})
  await openMenu(page,info,s,cell);await expect(menu(page)).toBeVisible();await activate(info,outside);await expect(menu(page)).toHaveCount(0)
  await openMenu(page,info,s,cell);await expect(menu(page)).toBeVisible();await page.keyboard.press('Escape');await expect(menu(page)).toHaveCount(0)
})

test('F白色跨區單筆保存、軸色覆蓋、歷史列印與Excel一致',async({page},info)=>{
  const s=await setup(page,info,'edit-menu-white',3)
  await s.op({action:'insert_header',before_id:null});await s.op({action:'insert_column',before_id:(await s.state()).layout.columns[0].id})
  const initial=await s.state(),l=initial.layout,a=point(l,0,0),b=point(l,2,1)
  await s.op({action:'shade_column',axis_id:l.columns[0].id,shade:3});await s.op({action:'shade_row',axis_id:l.rows[0].id,shade:2});await s.op({action:'shade_row',axis_id:l.rows[2].id,shade:3})
  await s.op({action:'merge_header',start_column_id:l.columns[0].id,end_column_id:l.columns[1].id});await s.reload()
  await selectRange(page,info,s,s.slot(a),s.slot(b));await openMenu(page,info,s,s.slot(a),true)
  await expect(menu(page).getByRole('button',{name:'合併儲存格',exact:true})).toBeDisabled();await expect(menu(page)).toContainText('不能跨越級數表頭合併')
  const sent:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))sent.push(r.postDataJSON())})
  const before=await s.state();await color(page,info,s,0);expect(sent).toHaveLength(1)
  const white=await s.state();expect(white.layout_revision).toBe(before.layout_revision+1);expect(white.rows).toEqual(before.rows)
  expect(white.layout.cell_shades.filter((c:any)=>c.shade===0)).toHaveLength(6);expect(white.layout.columns[0].header_shade).toBe(0)
  await expect(s.slot(a)).toHaveCSS('background-color','rgb(255, 255, 255)');await expect(s.slot(b)).toHaveCSS('background-color','rgb(255, 255, 255)')
  await activate(info,menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:'復原上一個動作',exact:true}));await s.idle();await expect(s.slot(a)).toHaveAttribute('data-shade','3')
  await openMenu(page,info,s,s.slot(a),true);await color(page,info,s,0);await page.keyboard.press('Escape');await s.reload();await expect(s.slot(a)).toHaveAttribute('data-shade','0')
  await s.save('白色與表頭合併');await s.idle();const saved=(await s.state()).latest
  await download(page,info,s,'white-current',{rows:saved.rows,layout:saved.layout,title:s.comp.name,version:'目前安排'})
  await s.op({action:'shade_cells',start:a,end:b,shade:2});await s.reload()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'白色與表頭合併'}))
  await expect(s.slot(a)).toHaveAttribute('data-shade','0');await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toHaveCount(0)
  await download(page,info,s,'white-history',{rows:saved.rows,layout:saved.layout,title:s.comp.name,version:'歷史：白色與表頭合併'})
  await page.evaluate(()=>window.print=()=>{});await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}))
  const print=page.locator('.arrangement-print');await expect(print.locator(`[data-print-header="${l.columns[0].id}"]`)).toHaveAttribute('colspan','2')
  await expect(print.locator(`[data-print-cell="${a.row_id}/${a.column_id}"] .print-cell-shade`)).toHaveCount(0)
  await page.emulateMedia({media:'print'});await expect(print.locator('th').first()).toHaveCSS('background-color','rgb(255, 255, 255)')
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('white-history.pdf'),preferCSSPageSize:true,printBackground:false})
})

test('F選單未知合併原樣恢復與真409保護',async({page},info)=>{
  const s=await setup(page,info,'edit-menu-recovery',3),headers=s.area.locator('[data-grid-header]'),sent:any[]=[]
  await selectRange(page,info,s,headers.nth(0),headers.nth(1));await openMenu(page,info,s,headers.nth(1),true)
  let first=true
  await page.route('**/arrangement/operations',async route=>{sent.push(route.request().postDataJSON());const response=await route.fetch();if(first){first=false;await route.abort('failed')}else await route.fulfill({response})})
  await activate(info,menu(page).getByRole('button',{name:'合併儲存格',exact:true}));await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}));await s.idle();expect(sent[0]).toEqual(sent[1]);expect((await s.state()).layout.header_merges).toHaveLength(1)
  await page.unroute('**/arrangement/operations');await openMenu(page,info,s,headers.first())
  await s.op({action:'insert_row',before_id:null})
  await activate(info,menu(page).getByRole('button',{name:'淺灰 2',exact:true}));await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  await expect(menu(page).getByRole('button',{name:'淺灰 1',exact:true})).toBeDisabled();await page.keyboard.press('Escape')
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
})

test('F跨分幅表頭與淡橘異動完整輸出',async({page},info)=>{
  const s=await setup(page,info,'edit-menu-wide',3)
  for(let i=0;i<3;i++)await s.op({action:'insert_column',before_id:null})
  const l=(await s.state()).layout
  await s.op({action:'merge_header',start_column_id:l.columns[10].id,end_column_id:l.columns[12].id})
  const m=(await s.state()).layout.header_merges[0]
  await s.op({action:'header_text',merge_id:m.id,text:'跨幅共同標題'})
  await s.op({action:'move_empty',registration_id:s.rows[0].id,target:point(l,4,2)});await s.reload()
  await expect(s.cell(0)).toHaveCSS('background-color','rgb(255, 225, 174)');await expect(s.cell(0)).toHaveCSS('color','rgb(17, 17, 17)')
  const current=await s.state();await download(page,info,s,'wide-header',{rows:current.rows,layout:current.layout,title:s.comp.name,version:'目前安排'})
  await page.evaluate(()=>window.print=()=>{});await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}))
  const print=page.locator('.arrangement-print');await expect(print.getByText('跨幅共同標題',{exact:false})).toHaveCount(2)
  await expect(print.getByText('（合併續）',{exact:true})).toHaveCount(1)
  await expect(print.locator('[data-print-registration]')).toHaveCount(3)
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('wide-header.pdf'),preferCSSPageSize:true,printBackground:false})
})

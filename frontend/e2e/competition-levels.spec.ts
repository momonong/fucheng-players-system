import { writeFile } from 'node:fs/promises'
import { expect, test, request as apiRequest, type Page, type TestInfo } from '@playwright/test'

let activeMenuContext: any
const cellMenu=(page:Page)=>page.getByRole('dialog',{name:'儲存格操作',exact:true})
async function openSelectedCellMenu(page:Page,info:TestInfo,s:any) {
  if(await cellMenu(page).isVisible()) return
  if(info.project.name==='mobile') await s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}).tap()
  else {
    const selected=s.area.locator('.grid-selected').first()
    if(await selected.count()) await selected.click({button:'right'})
    else await s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}).click()
  }
}

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
  const result={comp,other,headers,rows,area,endpoint,state,cell,slot,op,reload,idle,choose,save}
  activeMenuContext={page,info,s:result}
  return result
}
const point=(layout:any,row:number,col:number)=>({row_id:layout.rows[row].id,column_id:layout.columns[col].id})
const position=(layout:any,rid:string)=>{const c=layout.cells.find((v:any)=>v.registration_id===rid);return {row_id:c.row_id,column_id:c.column_id}}

async function drag(page:Page,info:TestInfo,from:any,to:any,cancel=false,fraction=.5) {
  await from.scrollIntoViewIfNeeded()
  const a=(await from.boundingBox())!,b=(await to.boundingBox())!
  if(info.project.name==='mobile') {
    const cdp=await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:a.x+a.width/2,y:a.y+a.height/2}]})
    await expect(page.locator('.level-drag-ghost')).toBeVisible()
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:b.x+b.width/2,y:b.y+b.height*fraction}]})
    await cdp.send('Input.dispatchTouchEvent',{type:cancel?'touchCancel':'touchEnd',touchPoints:[]})
    await cdp.detach()
  } else {
    await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down()
    await page.mouse.move(b.x+b.width/2,b.y+b.height*fraction,{steps:12})
    if(cancel) await page.keyboard.press('Escape')
    await page.mouse.up()
  }
}

test('格位八十人：搜尋不壓縮、真實插入觸控、素食與欄底鍵盤',async({page},info)=>{
  const s=await setup(page,info,'dense',80)
  await expect(s.area.locator('.grid-level-head th')).toHaveCount(10)
  const before=await s.state(),source=position(before.layout,s.rows[0].id),target=point(before.layout,2,0)
  const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/admin'))writes.push(r.url())})
  await s.area.getByRole('button',{name:'搜尋姓名',exact:true}).click()
  await s.area.getByLabel('搜尋姓名或辨識註記').fill('格位選手000')
  await expect(s.area.locator('.search-match')).toHaveCount(1);await expect(s.area.locator('.search-hidden')).toHaveCount(79);await expect(s.area.locator('.cell-name')).toHaveCount(1);await expect(s.area.getByText('格位選手020', {exact:true})).toHaveCount(0)
  await s.area.getByRole('button',{name:'素食 27 人',exact:true}).click()
  await expect(s.area.locator('.diet-highlight')).toHaveCount(27)
  expect((await s.state()).layout).toEqual(before.layout);expect(writes).toHaveLength(0)
  await s.cell(0).locator('.cell-name').focus();await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog').getByText('本場餐食：素食',{exact:true})).toBeVisible()
  await expect(page.getByRole('dialog').getByText('當次級數：1 級・長期級數：1 級',{exact:true})).toBeVisible()
  await page.getByRole('dialog').getByRole('button',{name:'關閉',exact:true}).click()
  // Viewing a player does not enter cell-range selection or leave editing tools over the grip.
  await page.evaluate(()=>{(window as any).trusted=[];window.addEventListener('pointerdown',e=>(window as any).trusted.push(`${e.pointerType}:${e.isTrusted}`))})
  await drag(page,info,s.cell(0).locator('.cell-grip'),s.slot(target),true,.1)
  expect((await s.state()).layout).toEqual(before.layout)
  await drag(page,info,s.cell(0).locator('.cell-grip'),s.slot(target),false,.1)
  await expect.poll(async()=>position((await s.state()).layout,s.rows[0].id)).toEqual(target)
  await s.idle()
  const after=await s.state()
  expect(after.layout.cells.some((c:any)=>c.row_id===source.row_id&&c.column_id===source.column_id)).toBe(false)
  expect(position(after.layout,s.rows[20].id)).toEqual(point(after.layout,3,0))
  expect(position(after.layout,s.rows[10].id)).toEqual(point(after.layout,1,0))
  await expect(s.cell(0)).toHaveClass(/net-position/)
  expect(await page.evaluate(()=>(window as any).trusted)).toContain(info.project.name==='mobile'?'touch:true':'mouse:true')
  await s.area.getByRole('button',{name:'素食 27 人',exact:true}).click();await expect(s.cell(0)).toHaveClass(/net-position/)
  await s.area.getByLabel('搜尋姓名或辨識註記').fill('')
  expect((await s.state()).layout).toEqual(after.layout)
  await page.reload();await s.choose();await expect(s.cell(0)).toBeVisible();expect((await s.state()).layout).toEqual(after.layout)
  await s.cell(0).locator('.cell-name').focus();await page.keyboard.press('Enter')
  await page.getByRole('dialog').getByLabel('移到級數').selectOption('2');await page.getByRole('dialog').getByRole('button',{name:'移動',exact:true}).click()
  await s.idle();const bottom=await s.state()
  expect(position(bottom.layout,s.rows[0].id)).toEqual(point(bottom.layout,8,1))
  expect(bottom.rows.find((r:any)=>r.registration_id===s.rows[0].id).competition_level).toBe(2)
  expect(position(bottom.layout,s.rows[1].id)).toEqual(position(before.layout,s.rows[1].id))
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:info.outputPath('grid-80.png'),fullPage:true})
})

test('格位表頭：甲乙丙上方合併、左側隊名、完整歷史與解除',async({page},info)=>{
  const s=await setup(page,info,'headers',3)
  const original=await s.state()
  await s.area.getByRole('button',{name:'在級數標題上方插入表頭列',exact:true}).click();await s.idle()
  let layout=(await s.state()).layout
  const title=point(layout,0,0)
  await activate(info,s.slot(title).locator('button'));await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
  await page.getByRole('dialog').getByLabel('儲存格文字內容',{exact:true}).fill('甲組')
  await page.getByRole('dialog').getByRole('button',{name:'儲存文字',exact:true}).click();await s.idle()
  if(info.project.name==='mobile'){await activate(info,cellMenu(page).getByRole('button',{name:'範圍選取',exact:true}));await activate(info,s.slot(point(layout,0,2)).locator('button'))}
  else await s.slot(point(layout,0,2)).locator('button').click({modifiers:['Shift']})
  await activate(info,cellMenu(page).getByRole('button',{name:'合併儲存格',exact:true}));await s.idle()
  expect((await s.state()).layout.merges).toHaveLength(1)
  for(const [text,a,b] of [['乙組',3,5],['丙組',6,9]] as const){await s.op({action:'text',target:point(layout,0,a),text});await s.op({action:'merge',start:point(layout,0,a),end:point(layout,0,b)})}
  await s.op({action:'insert_column',before_id:layout.columns[0].id});layout=(await s.state()).layout
  const team={row_id:position(original.layout,s.rows[0].id).row_id,column_id:layout.columns[0].id}
  await s.op({action:'text',target:team,text:'第一隊'});await s.reload()
  await expect(s.slot(team)).toContainText('第一隊')
  expect(position((await s.state()).layout,s.rows[0].id)).toEqual(position(original.layout,s.rows[0].id))
  const headerBox=(await s.area.locator('tr[data-row-role=header]').boundingBox())!,levelBox=(await s.area.locator('.grid-level-head').boundingBox())!
  expect(headerBox.y).toBeLessThan(levelBox.y)
  await s.save('甲乙丙布局');await s.idle();const saved=(await s.state()).latest
  await s.op({action:'unmerge',merge_id:saved.layout.merges[0].id});await s.reload()
  await s.area.getByRole('button',{name:'歷史',exact:true}).click();await s.area.locator('.version-item').filter({hasText:'甲乙丙布局'}).click()
  await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible();await expect(s.area.locator('td[colspan]')).toHaveCount(3)
  await expect(s.area.locator('.cell-grip')).toHaveCount(0)
  const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/admin'))writes.push(r.url())})
  await s.area.getByRole('button',{name:'回目前安排',exact:true}).click();await s.idle()
  expect((await s.state()).layout.merges).toHaveLength(2);expect(writes).toHaveLength(0)
  await page.screenshot({path:info.outputPath('grid-headers.png'),fullPage:true})
})

test('格位未知小存原樣重試與成功待讀回整場鎖',async({page},info)=>{
  const s=await setup(page,info,'unknown')
  const start=await s.state(),target=point(start.layout,1,0)
  let lost=true
  const payloads:any[]=[]
  await page.route('**/arrangement/operations',async route=>{payloads.push(route.request().postDataJSON());if(lost){lost=false;await route.fetch();await route.fulfill({status:503,json:{detail:'合成未知結果'}})}else await route.continue()})
  await drag(page,info,s.cell(0).locator('.cell-grip'),s.slot(target))
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible()
  await expect(s.cell(1).locator('.cell-grip')).toBeDisabled();await expect(s.area.getByRole('button',{name:'保存完整安排'})).toBeDisabled()
  await s.op({action:'insert_row',before_id:null});const revision=(await s.state()).layout_revision
  await s.area.getByRole('button',{name:'確認操作結果／原樣重試'}).click();await s.idle()
  expect(payloads[0]).toEqual(payloads[1]);expect((await s.state()).layout_revision).toBe(revision)
  expect(position((await s.state()).layout,s.rows[0].id)).toEqual(target)
  await page.unroute('**/arrangement/operations')
  let failRead=false
  await page.route('**/arrangement',async route=>{if(failRead){await route.fulfill({status:503,json:{detail:'合成讀回失敗'}})}else await route.continue()})
  await page.route('**/arrangement/operations',async route=>{const res=await route.fetch();failRead=true;await route.fulfill({response:res})})
  await s.area.getByRole('button',{name:'在表格下方插列',exact:true}).click()
  await expect(s.area.getByRole('button',{name:'讀回目前安排',exact:true})).toBeVisible();await expect(s.cell(1).locator('.cell-grip')).toBeDisabled()
  failRead=false;await s.area.getByRole('button',{name:'讀回目前安排',exact:true}).click();await s.idle()
})

test('格位文字409後切場仍保留草稿並重新核對提交',async({page},info)=>{
  const s=await setup(page,info,'draft')
  const target=point((await s.state()).layout,6,0)
  await activate(info,s.slot(target).locator('button'));await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
  await page.getByRole('dialog').getByLabel('儲存格文字內容',{exact:true}).fill('保留我的隊名草稿')
  await s.op({action:'insert_row',before_id:null}) // unseen peer state creates a real stale-token conflict
  await page.getByRole('dialog').getByRole('button',{name:'儲存文字',exact:true}).click()
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  await s.choose(true);await s.choose(false)
  await s.area.getByRole('button',{name:'重新讀取並核對',exact:true}).click();await s.idle()
  await activate(info,s.slot(target).locator('button'));await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
  await expect(page.getByRole('dialog').getByLabel('儲存格文字內容',{exact:true})).toHaveValue('保留我的隊名草稿')
  await page.getByRole('dialog').getByRole('button',{name:'儲存文字',exact:true}).click();await s.idle();await expect(s.slot(target)).toContainText('保留我的隊名草稿')
})

test('格位大存未知舊receipt不回退較新布局與基準',async({page},info)=>{
  const s=await setup(page,info,'save')
  await s.op({action:'move',registration_id:s.rows[0].id,target:point((await s.state()).layout,4,0)});await s.reload()
  let lost=true;const sent:any[]=[]
  await page.route('**/arrangement/versions',async route=>{sent.push(route.request().postDataJSON());if(lost){lost=false;await route.fetch();await route.fulfill({status:503,json:{detail:'合成未知大存'}})}else await route.continue()})
  await s.save('第一次布局');await expect(s.area.getByRole('button',{name:'確認保存結果／原樣重試'})).toBeVisible()
  await expect(s.area.getByRole('button',{name:'在表格下方插列'})).toBeDisabled()
  const peer=await apiRequest.newContext({baseURL:info.project.use.baseURL})
  const login=await (await peer.post('/api/auth/login',{data:{username:'e2e-arrangement-peer',password:process.env.FUCHENG_E2E_ADMIN_PASSWORD!}})).json()
  const peerHeaders={'X-CSRF-Token':login.csrf_token}
  const peerOp=async(operation:any)=>{const state=await s.state();expect((await peer.post(s.endpoint+'/operations',{headers:peerHeaders,data:{request_id:crypto.randomUUID(),state_token:state.state_token,operation}})).status()).toBe(200)}
  await peerOp({action:'insert_column',before_id:null})
  const current=await s.state()
  const newer=await peer.post(s.endpoint+'/versions',{headers:peerHeaders,data:{request_id:crypto.randomUUID(),state_token:current.state_token,base_version_id:current.latest.id,label:'較新保存'}})
  expect(newer.status()).toBe(200)
  await peerOp({action:'insert_row',before_id:null});const latest=await s.state()
  await s.choose(true);await s.choose(false)
  await s.area.getByRole('button',{name:'確認保存結果／原樣重試'}).click();await s.idle()
  expect(sent[0]).toEqual(sent[1]);expect((await s.state()).latest.id).toBe(latest.latest.id)
  expect((await s.state()).layout).toEqual(latest.layout);await expect(s.area.getByRole('button',{name:'保存完整安排'})).toBeEnabled();await peer.dispose()
})


test('格位移回清色、插列保持分組、外部結束重讀唯讀',async({page},info)=>{
  const s=await setup(page,info,'net')
  const original=await s.state(),source=position(original.layout,s.rows[0].id)
  await s.op({action:'move',registration_id:s.rows[0].id,target:point(original.layout,4,6)});await s.reload()
  await expect(s.cell(0)).toHaveClass(/net-level/)
  await s.op({action:'move',registration_id:s.rows[0].id,target:source});await s.reload()
  await expect(s.cell(0)).not.toHaveClass(/net-level|net-position/)
  await expect(s.area.getByRole('button',{name:'保存完整安排'})).toBeDisabled()
  await s.op({action:'insert_row',before_id:source.row_id});await s.reload()
  await expect(s.cell(0)).not.toHaveClass(/net-level|net-position/)
  await s.save('插空列');await s.idle();await expect(s.area.getByRole('button',{name:'保存完整安排'})).toBeDisabled()
  const comp=(await (await page.request.get(`/api/admin/competitions/${s.comp.id}`)).json()).competition
  expect((await page.request.put(`/api/admin/competitions/${s.comp.id}`,{headers:s.headers,data:{name:comp.name,competition_date:comp.competition_date,registration_deadline:comp.registration_deadline,capacity:comp.capacity,status:'closed',version:comp.version}})).status()).toBe(200)
  const closed=(await (await page.request.get(`/api/admin/competitions/${s.comp.id}`)).json()).competition
  expect((await page.request.put(`/api/admin/competitions/${s.comp.id}`,{headers:s.headers,data:{name:closed.name,competition_date:closed.competition_date,registration_deadline:closed.registration_deadline,capacity:closed.capacity,status:'ended',version:closed.version}})).status()).toBe(200)
  await s.reload()
  await expect(s.area.getByText('此場次為唯讀',{exact:true})).toBeVisible();await expect(s.area.locator('.cell-grip')).toHaveCount(0)
})

test('格位送出前斷線及切場晚回應不改場',async({page},info)=>{
  const s=await setup(page,info,'predispatch')
  let abort=true;const sent:any[]=[]
  await page.route('**/arrangement/operations',async route=>{sent.push(route.request().postDataJSON());if(abort){abort=false;await route.abort()}else await route.continue()})
  const before=await s.state()
  await s.area.getByRole('button',{name:'在表格下方插列',exact:true}).click();await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible()
  expect((await s.state()).layout).toEqual(before.layout)
  await s.area.getByRole('button',{name:'確認操作結果／原樣重試'}).click();await s.idle();expect(sent[0]).toEqual(sent[1])
  await page.unroute('**/arrangement/operations')
  let release!:()=>void;const waiting=new Promise<void>(resolve=>release=resolve)
  let reached!:()=>void;const committed=new Promise<void>(resolve=>reached=resolve)
  await page.route('**/arrangement/operations',async route=>{const result=await route.fetch();reached();await waiting;await route.fulfill({response:result})})
  await s.area.getByRole('button',{name:'在表格下方插列',exact:true}).click();await committed
  await s.choose(true);release();await expect(s.area.getByRole('heading',{name:s.other.name,exact:true})).toBeVisible()
  await s.choose();await s.idle();expect((await s.state()).layout.rows.length).toBe(before.layout.rows.length+2)
})


test('格位原生橫捲不寫入與拖曳最遠第十欄',async({page},info)=>{
  const s=await setup(page,info,'edge')
  const before=await s.state(),target=point(before.layout,1,9)
  const table=s.area.locator('.arrangement-table-scroll')
  await table.scrollIntoViewIfNeeded()
  if(info.project.name==='mobile') {
    const cdp=await page.context().newCDPSession(page)
    const box=(await table.boundingBox())!,y=box.y+65
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width-20,y}]})
    for(let i=1;i<=10;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+box.width-20-i*23,y}]})
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
    await expect.poll(()=>table.evaluate(el=>el.scrollLeft)).toBeGreaterThan(50)
    expect((await s.state()).layout).toEqual(before.layout)
    await s.cell(0).locator('.cell-grip').scrollIntoViewIfNeeded()
    const from=(await s.cell(0).locator('.cell-grip').boundingBox())!,edge=(await table.boundingBox())!
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:from.x+from.width/2,y:from.y+20}]})
    await expect(page.locator('.level-drag-ghost')).toBeVisible()
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:edge.x+edge.width-8,y:from.y+20}]})
    await expect.poll(()=>table.evaluate(el=>el.scrollLeft+el.clientWidth>=el.scrollWidth-4)).toBe(true)
    const to=(await s.slot(target).boundingBox())!
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:to.x+to.width/2,y:to.y+20}]})
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()
  } else await drag(page,info,s.cell(0).locator('.cell-grip'),s.slot(target))
  await expect.poll(async()=>position((await s.state()).layout,s.rows[0].id)).toEqual(target)
  await s.idle();expect((await s.state()).rows.find((r:any)=>r.registration_id===s.rows[0].id).competition_level).toBe(10)
})


test('拖曳修正：姓名與把手放下不開資訊、浮動卡跟手及來源淡化',async({page},info)=>{
  const s=await setup(page,info,'dragfix')
  const ghost=page.locator('.level-drag-ghost')
  await page.evaluate(()=>{(window as any).dragEvents=[];window.addEventListener('pointerup',e=>(window as any).dragEvents.push({type:e.pointerType,trusted:e.isTrusted,id:e.pointerId}))})
  for(const sourceSelector of info.project.name==='mobile'?['.cell-grip']:['.cell-name','.cell-grip']) {
    // Keep GET pending after commit, making the old blocked/onClick race deterministic.
    let unblock!:()=>void;const waitRead=new Promise<void>(resolve=>unblock=resolve)
    let mutation=false
    await page.route('**/arrangement/operations',async route=>{mutation=true;await route.continue()})
    await page.route('**/arrangement',async route=>{if(mutation)await waitRead;await route.continue()})
    const source=s.cell(0).locator(sourceSelector),destination=s.cell(1).locator('.cell-name')
    await source.scrollIntoViewIfNeeded()
    const a=(await source.boundingBox())!,b=(await destination.boundingBox())!,cardBox=(await s.cell(0).boundingBox())!
    const start={x:a.x+a.width/2,y:a.y+a.height/2},finish={x:b.x+b.width/2,y:b.y+b.height/2}
    const cdp=info.project.name==='mobile'?await page.context().newCDPSession(page):null
    if(cdp){await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]});await expect(ghost).toBeVisible();await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[finish]})}
    else {await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(finish.x,finish.y,{steps:8})}
    await expect(ghost).toBeVisible();await expect(ghost).toHaveText('格位選手000合成dragfix')
    await expect(s.cell(0)).toHaveCSS('opacity','0.25')
    const preview=(await ghost.boundingBox())!
    expect(Math.abs(preview.width-cardBox.width)).toBeLessThan(2);expect(Math.abs(preview.height-cardBox.height)).toBeLessThan(2)
    expect(Math.abs(preview.x-Math.max(8,Math.min(finish.x+12,info.project.use.viewport!.width-cardBox.width-8)))).toBeLessThan(3)
    expect(Math.abs(preview.y-(finish.y+(cdp?-cardBox.height-16:16)))).toBeLessThan(4)
    expect(await ghost.evaluate(el=>el.parentElement===document.body)).toBe(true)
    await page.screenshot({path:info.outputPath(`drag-preview-${sourceSelector.slice(1)}.png`),fullPage:true})
    if(cdp){await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()}else await page.mouse.up()
    await expect(ghost).toHaveCount(0);await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(s.cell(0)).toHaveCSS('opacity','1');await expect(s.cell(1).locator('.cell-grip')).toBeDisabled()
    unblock();await s.idle();await page.unroute('**/arrangement');await page.unroute('**/arrangement/operations')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    // The next click/tap selects the landing player; Enter still opens details.
    await activate(info,s.cell(1).locator('.cell-name'));await expect(page.getByRole('dialog')).toHaveCount(0);await expect(s.cell(1).locator('..')).toHaveClass(/grid-selected/);await s.cell(1).locator('.cell-name').focus();await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog',{name:'格位選手001'})).toBeVisible()
    await page.getByRole('dialog').getByRole('button',{name:'關閉',exact:true}).click()
    await s.cell(0).locator('.cell-name').focus();await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog',{name:'格位選手000'})).toBeVisible();await page.keyboard.press('Escape')
    await activate(info,s.cell(0).locator('.cell-grip'));await expect(page.getByRole('dialog')).toHaveCount(0);await s.cell(0).locator('.cell-grip').focus();await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog',{name:'格位選手000'})).toBeVisible();await page.keyboard.press('Escape')
  }
  expect(await page.evaluate(expected=>(window as any).dragEvents.some((e:any)=>e.trusted&&e.type===expected),info.project.name==='mobile'?'touch':'mouse')).toBe(true)
})

test('拖曳修正：取消與失敗清理、普通觸控捲動不殘留淡化',async({page},info)=>{
  const s=await setup(page,info,'dragcancel')
  const ghost=page.locator('.level-drag-ghost'),before=await s.state()
  const source=s.cell(0).locator(info.project.name==='mobile'?'.cell-grip':'.cell-name')
  const destination=s.cell(1).locator('.cell-name')
  await drag(page,info,source,destination,true)
  await expect(ghost).toHaveCount(0);await expect(page.getByRole('dialog')).toHaveCount(0);await expect(s.cell(0)).toHaveCSS('opacity','1')
  expect((await s.state()).layout).toEqual(before.layout)
  await openPlayer(info,s.cell(0).locator('.cell-name'))
  await expect(page.getByRole('dialog',{name:'格位選手000'})).toBeVisible();await page.keyboard.press('Escape')
  // Server failure also clears all drag visuals and suppresses the derived click while busy.
  await page.route('**/arrangement/operations',route=>route.fulfill({status:503,json:{detail:'合成拖曳失敗'}}))
  await drag(page,info,s.cell(0).locator('.cell-grip'),destination)
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible()
  await expect(ghost).toHaveCount(0);await expect(s.cell(0)).toHaveCSS('opacity','1');await expect(page.getByRole('dialog')).toHaveCount(0)
  await openPlayer(info,s.cell(0).locator('.cell-name'))
  await expect(page.getByRole('dialog',{name:'格位選手000'})).toBeVisible();await page.keyboard.press('Escape')
  await page.unroute('**/arrangement/operations');await s.area.getByRole('button',{name:'確認操作結果／原樣重試'}).click();await s.idle()
  if(info.project.name==='mobile') {
    const table=s.area.locator('.arrangement-table-scroll');await table.evaluate(el=>el.scrollLeft=0);await table.scrollIntoViewIfNeeded()
    const box=(await table.boundingBox())!,cdp=await page.context().newCDPSession(page),y=box.y+65
    const state=await s.state()
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width-25,y}]})
    for(let i=1;i<=10;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+box.width-25-i*22,y}]})
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()
    await expect.poll(()=>table.evaluate(el=>el.scrollLeft)).toBeGreaterThan(40)
    await expect(ghost).toHaveCount(0);await expect(s.area.locator('.is-drag-source')).toHaveCount(0);await expect(page.getByRole('dialog')).toHaveCount(0)
    expect((await s.state()).layout).toEqual(state.layout)
  }
})


async function editLabel(page:Page,info:TestInfo,s:any,index:number,text:string) {
  if(info.project.name==='desktop') {
    await s.area.locator('.grid-column-title').nth(index).dblclick()
    await page.getByLabel('直接編輯文字',{exact:true}).fill(text);await page.keyboard.press('Enter')
  } else {
    await s.area.getByLabel(`選取第 ${index+1} 欄表頭`,{exact:true}).tap()
    await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
    await page.getByLabel('儲存格文字內容',{exact:true}).fill(text)
    await page.getByRole('button',{name:'儲存文字',exact:true}).tap()
  }
}
async function rectangle(page:Page,info:TestInfo,s:any,a:any,b:any) {
  if(info.project.name==='mobile') {
    await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,cellMenu(page).getByRole('button',{name:'範圍選取',exact:true}))
    await activate(info,s.slot(b).locator('.grid-empty'))
  } else {
    const cancel=cellMenu(page).getByRole('button',{name:'取消選取',exact:true});if(await cancel.isVisible()&&await cancel.isEnabled())await cancel.click() // first gesture with no selected cell or toolbar
    const x=(await s.slot(a).boundingBox())!,y=(await s.slot(b).boundingBox())!
    await page.mouse.move(x.x+x.width/2,x.y+x.height/2);await page.mouse.down()
    await page.mouse.move(y.x+y.width/2,y.y+y.height/2,{steps:8});await page.mouse.up()
    expect((await s.slot(a).boundingBox())!.y).toBe(x.y)
  }
}
test('表格新版：邊界插入、直接標題與合併原位文字、框選',async({page},info)=>{
  const s=await setup(page,info,'edit-interactions',3),initial=await s.state()
  await editLabel(page,info,s,0,'自訂一級');await s.idle()
  await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeEnabled()
  await editLabel(page,info,s,0,'1 級');await s.idle()
  await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeDisabled()
  await s.area.getByRole('button',{name:'在級數標題上方插入表頭列',exact:true}).click();await s.idle()
  await s.area.getByRole('button',{name:'在第 1 欄左方插入文字欄',exact:true}).click();await s.idle()
  await s.area.getByRole('button',{name:'在第 3 列上方插列',exact:true}).click();await s.idle()
  let layout=(await s.state()).layout
  expect(layout.columns[0].kind).toBe('text');expect(layout.rows[0].role).toBe('header')
  expect(position(layout,s.rows[0].id)).toEqual(position(initial.layout,s.rows[0].id))
  const a=point(layout,0,0),b=point(layout,0,2)
  await s.op({action:'text',target:b,text:'非左上原始隊名'});await s.reload()
  await rectangle(page,info,s,a,b)
  await expect(s.area.locator('.grid-selected')).toHaveCount(3)
  await activate(info,cellMenu(page).getByRole('button',{name:'合併儲存格',exact:true}));await s.idle()
  if(info.project.name==='desktop') {
    await s.slot(a).locator('.grid-empty').dblclick();await page.getByLabel('直接編輯文字').fill('取消內容');await page.keyboard.press('Escape')
    expect((await s.state()).layout.cells.find((c:any)=>c.text==='取消內容')).toBeUndefined()
    await s.slot(a).locator('.grid-empty').dblclick();await page.getByLabel('直接編輯文字').fill('甲組修改');await page.keyboard.press('Enter')
  } else {
    await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
    await page.getByLabel('儲存格文字內容').fill('甲組修改');await page.getByRole('button',{name:'儲存文字',exact:true}).tap()
  }
  await s.idle();await expect(s.slot(a)).toContainText('甲組修改')
  await activate(info,cellMenu(page).getByRole('button',{name:'解除合併儲存格',exact:true}));await s.idle()
  expect((await s.state()).layout.cells.find((c:any)=>c.text==='甲組修改')).toMatchObject(b)
  await expect(s.slot(b)).toContainText('甲組修改')
  await s.area.getByRole('button',{name:'素食 1 人',exact:true}).click()
  await expect(s.cell(0).locator('.diet-mark')).toHaveText('素');await expect(s.cell(0)).toHaveCSS('box-shadow','none')
  if(info.project.name==='desktop') {
    // Start at the visible inset, cross a player, and reject merging without moving anyone.
    const from=s.slot(point(layout,1,0)),to=s.slot(point(layout,1,2))
    const beforeRejectedMerge=await s.state(),operationWrites:any[]=[]
    page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/arrangement/operations'))operationWrites.push(request.postDataJSON())})
    await from.locator('.grid-empty').click();const x=(await from.boundingBox())!,y=(await to.boundingBox())!
    await page.mouse.move(x.x+1,x.y+1);await page.mouse.down();await page.mouse.move(y.x+y.width/2,y.y+y.height/2,{steps:8});await page.mouse.up()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const selected=s.area.locator('[data-grid-cell].grid-selected')
    await expect(selected).toHaveCount(3)
    const fromCellId=(await from.getAttribute('data-grid-cell'))!
    const selectedRowId=fromCellId.split('/')[0]
    const selectedIds=await selected.evaluateAll(elements=>elements.map(element=>element.getAttribute('data-grid-cell')).sort())
    const expectedIds=[0,1,2].map(column=>`${selectedRowId}/${layout.columns[column].id}`).sort()
    expect(selectedIds).toEqual(expectedIds)
    const playerPosition=position(beforeRejectedMerge.layout,s.rows[0].id)
    expect(playerPosition.row_id).toBe(selectedRowId)
    expect(expectedIds).toContain(`${playerPosition.row_id}/${playerPosition.column_id}`)
    await openSelectedCellMenu(page,info,s)
    await expect(cellMenu(page).getByRole('button',{name:'合併儲存格',exact:true})).toBeDisabled()
    await expect(cellMenu(page).getByText('選區含選手，不能合併。',{exact:true})).toBeVisible()
    expect(operationWrites).toHaveLength(0)
    expect((await s.state()).layout).toEqual(beforeRejectedMerge.layout)
    await page.setViewportSize({width:1800,height:1000})
    expect((await s.area.locator('.grid-canvas').boundingBox())!.width).toBeGreaterThan(1200)
  }
  if(info.project.name==='mobile') {
    const scroll=s.area.locator('.arrangement-table-scroll')
    await scroll.evaluate(el=>el.scrollLeft=0)
    const current=(await s.state()).layout
    // Restore touch input after earlier click-based fixture operations and retain the left boundary.
    await activate(info,s.slot(point(current,0,0)).locator('.grid-empty'));await openSelectedCellMenu(page,info,s)
    await expect(cellMenu(page).getByRole('button',{name:'範圍選取',exact:true})).toBeVisible()
    await expect(s.area.locator('.grid-desktop-hint')).not.toBeVisible()
    const left=s.area.getByRole('button',{name:'在第 1 欄左方插入文字欄',exact:true})
    await expect(left).toBeVisible();await left.tap();await s.idle()
    await s.area.getByRole('button',{name:'在第 1 列上方插列',exact:true}).tap();await s.idle()
    const after=(await s.state()).layout
    expect(after.columns.length).toBe(current.columns.length+1);expect(after.rows.length).toBe(current.rows.length+1)
    await scroll.evaluate(el=>el.scrollLeft=0)
    await s.slot(point(after,0,0)).locator('.grid-empty').tap()
    await activate(info,cellMenu(page).getByRole('button',{name:'範圍選取',exact:true}))
    await activate(info,s.slot(point(after,0,1)).locator('.grid-empty'));await openSelectedCellMenu(page,info,s)
    await expect(s.area.locator('.grid-selected')).toHaveCount(2)
    await expect(cellMenu(page).getByRole('button',{name:'範圍選取',exact:true})).toBeVisible()
    await expect(s.area.locator('.grid-desktop-hint')).not.toBeVisible()
    expect(await scroll.evaluate(el=>el.scrollLeft)).toBe(0)
    // Viewport capture preserves the actual input mode and screen position.
    await page.screenshot({path:info.outputPath('grid-edit-mobile-touch-origin.png')})
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:info.outputPath('grid-edit-interactions.png'),fullPage:true})
})

test('表格新版：標題失敗保留與原樣恢復',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery')
  const sent:any[]=[]
  await page.route('**/arrangement/operations',async route=>{sent.push(route.request().postDataJSON());await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'合成暫時失敗'})})})
  await editLabel(page,info,s,0,'待確認標題')
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await expect(s.area.getByRole('button',{name:'列印安排',exact:true})).toBeDisabled()
  await expect(info.project.name==='desktop'?s.area.getByLabel('直接編輯文字'):s.area.getByLabel('選取第 1 欄表頭',{exact:true})).toBeDisabled()
  await s.choose(true);await s.choose()
  await page.unroute('**/arrangement/operations')
  const response=page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith('/arrangement/operations'))
  await s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}).click()
  expect((await response).postDataJSON()).toEqual(sent[0]);await s.idle()
  await expect(s.area.locator('.grid-column-title').first()).toHaveText('待確認標題')
  await s.save('只有標題');await s.idle();await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeDisabled()
})

test('表格新版：完整列印與歷史凍結、寬表長表分幅',async({page},info)=>{
  test.setTimeout(90000)
  const s=await setup(page,info,'edit-print',80)
  await s.op({action:'insert_header',before_id:null});let layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,0,0),text:'甲組'})
  await s.op({action:'merge',start:point(layout,0,0),end:point(layout,0,2)})
  await s.op({action:'insert_column',before_id:layout.columns[0].id});layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,1,0),text:'第一隊'})
  await s.op({action:'column_title',column_id:layout.columns[1].id,text:'一級自訂'})
  await s.reload();await s.save('列印保存版');await s.idle()
  const saved=(await s.state()).latest
  await s.area.getByRole('button',{name:'搜尋姓名',exact:true}).click();await s.area.getByLabel('搜尋姓名或辨識註記').fill('格位選手000')
  await page.evaluate(()=>{(window as any).printCalls=0;window.print=()=>{(window as any).printCalls++}})
  await s.area.getByRole('button',{name:'列印安排',exact:true}).click()
  const printed=page.locator('body > .arrangement-print')
  await expect(printed.locator('[data-print-registration]')).toHaveCount(80)
  await expect(printed.locator('.print-vegetarian')).toHaveCount(27)
  await expect(printed.locator('.print-coordinate')).toHaveCount(0);await expect(printed).not.toContainText('第 1 / 1');
  await expect(printed).toContainText('一級自訂');await expect(printed).toContainText('第一隊');await expect(printed).toContainText('甲組')
  await page.emulateMedia({media:'print'})
  await expect(s.area).not.toBeVisible();await expect(printed).toBeVisible()
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('arrangement-current.pdf'),preferCSSPageSize:true,printBackground:false})
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')))
  await expect(printed).toHaveCount(0);await page.emulateMedia({media:'screen'})
  await s.op({action:'column_title',column_id:layout.columns[1].id,text:'現況不同'})
  const updated=await s.state(),reg=updated.rows.find((r:any)=>r.registration_id===s.rows[0].id)
  expect((await page.request.put(`/api/admin/registrations/${reg.registration_id}/diet`,{headers:s.headers,data:{version:reg.version,request_id:crypto.randomUUID(),diet:'omnivore'}})).status()).toBe(200)
  await s.reload();await s.area.getByRole('button',{name:'歷史',exact:true}).click();await s.area.locator('.version-item').filter({hasText:'列印保存版'}).click()
  await expect(s.area.locator('.grid-column-title').nth(1)).toHaveText('一級自訂')
  await s.area.getByRole('button',{name:'列印安排',exact:true}).click()
  await expect(printed.locator('.print-vegetarian')).toHaveCount(27);await expect(printed).not.toContainText('現況不同')
  await page.emulateMedia({media:'print'});await expect(printed).toBeVisible();await expect(s.area).not.toBeVisible()
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('arrangement-history.pdf'),preferCSSPageSize:true})
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));await expect(printed).toHaveCount(0)
  await page.emulateMedia({media:'screen'})
  await s.area.getByRole('button',{name:'回目前安排',exact:true}).click();await s.idle()
  for(let i=0;i<3;i++)await s.op({action:'insert_column',before_id:null})
  for(let i=0;i<12;i++)await s.op({action:'insert_row',before_id:null})
  layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,0,11),text:'跨分幅合併'})
  await s.op({action:'merge',start:point(layout,0,11),end:point(layout,0,13)})
  await s.op({action:'move',registration_id:s.rows[39].id,target:point(layout,layout.rows.length-1,10)})
  await s.op({action:'text',target:point(layout,17,0),text:'跨續頁隊名'})
  await s.op({action:'merge',start:point(layout,17,0),end:point(layout,20,0)})
  await s.reload();await s.area.getByRole('button',{name:'列印安排',exact:true}).click()
  await expect(printed.locator('.arrangement-print-page')).toHaveCount(4)
  const ids=await printed.locator('[data-print-registration]').evaluateAll(els=>els.map(e=>e.getAttribute('data-print-registration')))
  expect(ids.sort()).toEqual(s.rows.map(r=>r.id).sort());expect(new Set(ids).size).toBe(80)
  await expect(printed.locator('.print-vegetarian')).toHaveCount(26)
  await expect(printed).toContainText('合併續')
  await page.emulateMedia({media:'print'});await expect(printed).toBeVisible();await expect(s.area).not.toBeVisible()
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('arrangement-wide-long.pdf'),preferCSSPageSize:true})
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));await expect(printed).toHaveCount(0)
  const historical=await (await page.request.get(s.endpoint+'/versions/'+saved.id)).json()
  expect(historical).toEqual(saved)
  await page.emulateMedia({media:'screen'});await expect(s.area).toBeVisible()
})


const activate=async(info:TestInfo,locator:any)=>{
  if(locator.toString().includes('儲存格操作')&&activeMenuContext&&await cellMenu(activeMenuContext.page).count()===0)
    await openSelectedCellMenu(activeMenuContext.page,info,activeMenuContext.s)
  return info.project.name==='mobile'?locator.tap():locator.click()
}
const openPlayer=async(info:TestInfo,locator:any)=>{if(info.project.name==='mobile'){await locator.tap();await locator.tap()}else await locator.dblclick()}
test('表格刪除：保護選手級數、文字確認與合併保留',async({page},info)=>{
  const s=await setup(page,info,'axis-delete',3),original=await s.state()
  await activate(info,s.area.getByLabel('第 1 排更多操作',{exact:true}))
  const popup=page.getByRole('group',{name:'這個範圍的操作'})
  await expect(popup).toContainText('請先移走');await expect(popup.getByRole('button',{name:'刪除這一整排'})).toBeDisabled()
  await activate(info,popup.getByRole('button',{name:'關閉'}))
  await activate(info,s.area.getByLabel('第 1 直欄更多操作',{exact:true}))
  await expect(popup).toContainText('固定級數欄不能刪除')
  await activate(info,popup.getByRole('button',{name:'關閉'}))
  await s.op({action:'insert_header',before_id:null})
  let layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,0,1),text:'要保留的組別'})
  await s.op({action:'merge',start:point(layout,0,0),end:point(layout,0,2)})
  await s.op({action:'insert_column',before_id:layout.columns[0].id});layout=(await s.state()).layout
  await s.op({action:'column_title',column_id:layout.columns[0].id,text:'隊名欄'})
  const textCell=point(layout,2,0)
  await s.op({action:'text',target:textCell,text:'確定要刪除的隊名'});await s.reload()
  await s.save('刪除前');await s.idle();const saved=(await s.state()).latest
  await activate(info,s.area.getByLabel('第 1 直欄更多操作',{exact:true}))
  await expect(s.area.locator('.axis-removal-column')).toBeVisible()
  await activate(info,popup.getByRole('button',{name:'刪除這個文字直欄'}))
  const dialog=page.getByRole('dialog',{name:'確認刪除這個範圍'})
  await expect(dialog).toContainText('第 1 直欄');await expect(dialog).toContainText('隊名欄');await expect(dialog).toContainText('確定要刪除的隊名')
  await page.screenshot({path:info.outputPath('axis-delete-confirm.png')})
  await activate(info,dialog.getByRole('button',{name:'保留這個範圍'}));expect((await s.state()).layout).toEqual(saved.layout)
  await activate(info,s.area.getByLabel('第 1 直欄更多操作',{exact:true}));await activate(info,popup.getByRole('button',{name:'刪除這個文字直欄'}))
  await activate(info,dialog.getByRole('button',{name:'確認刪除文字直欄'}));await s.idle()
  const after=await s.state();expect(after.layout.columns).toHaveLength(10);expect(after.rows).toEqual(original.rows)
  expect(after.layout.merges).toEqual(saved.layout.merges) // unaffected header remains intact
  await expect(s.area.locator('.grid-selected')).toHaveCount(0);await expect(page.getByLabel('直接編輯文字')).toHaveCount(0)
  await activate(info,s.area.getByLabel('第 4 排更多操作',{exact:true}));await activate(info,popup.getByRole('button',{name:'刪除這一整排'}));await s.idle()
  expect((await s.state()).layout.rows).toHaveLength(after.layout.rows.length-1)
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'刪除前'}))
  await expect(s.area.locator('.grid-level-head th')).toHaveCount(11);await expect(s.area.locator('.grid-axis-more')).toHaveCount(0)
  expect(await (await page.request.get(s.endpoint+'/versions/'+saved.id)).json()).toEqual(saved)
  await page.evaluate(()=>window.print=()=>{})
  await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}))
  const printed=page.locator('.arrangement-print');await expect(printed).toContainText('確定要刪除的隊名');await expect(printed.locator('[data-print-registration]')).toHaveCount(3)
  await page.emulateMedia({media:'print'});await expect(printed).toBeVisible();await expect(s.area).not.toBeVisible()
  await page.screenshot({path:info.outputPath('axis-old-history-print.png'),fullPage:true})
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));await page.emulateMedia({media:'screen'})
})


test('表格刪除：確認綁舊token、未知原樣重試與清理失效選格',async({page},info)=>{
  const s=await setup(page,info,'axis-cas')
  let layout=(await s.state()).layout
  await s.op({action:'insert_column',before_id:layout.columns[0].id});layout=(await s.state()).layout
  const target=point(layout,2,0);await s.op({action:'text',target,text:'確認時的文字'});await s.reload()
  await activate(info,s.slot(target).locator('.grid-empty'))
  const draft='尚未提交的本機草稿',editor=page.getByLabel('直接編輯文字',{exact:true})
  if(info.project.name==='desktop'){await s.slot(target).locator('.grid-empty').dblclick();await editor.fill(draft)}
  const popup=page.getByRole('group',{name:'這個範圍的操作'}),dialog=page.getByRole('dialog',{name:'確認刪除這個範圍'})
  const trigger=s.area.getByLabel('第 1 直欄更多操作',{exact:true})
  const openPopup=async()=>{
    if(info.project.name==='desktop'&&await editor.isVisible()){await trigger.focus();await page.keyboard.press('Enter')}
    else await activate(info,trigger)
    await expect(popup).toBeVisible()
  }
  const startDelete=async()=>{
    const action=popup.getByRole('button',{name:'刪除這個文字直欄'})
    if(info.project.name==='desktop'&&await editor.isVisible()){await action.focus();await page.keyboard.press('Enter')}
    else await activate(info,action)
  }
  const confirmDelete=async()=>{
    const action=dialog.getByRole('button',{name:'確認刪除文字直欄'})
    if(info.project.name==='desktop'&&await editor.isVisible()){await action.focus();await page.keyboard.press('Enter')}
    else await activate(info,action)
  }
  await openPopup();await startDelete()
  if(info.project.name==='desktop')expect((await s.state()).layout.cells.find((cell:any)=>cell.row_id===target.row_id&&cell.column_id===target.column_id)?.text).toBe('確認時的文字')
  await s.op({action:'text',target,text:'確認之後另一人新字'})
  await confirmDelete()
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  if(info.project.name==='desktop'){await expect(editor).toHaveValue(draft);await expect(editor).toBeDisabled()}
  expect((await s.state()).layout.cells.some((c:any)=>c.text==='確認之後另一人新字')).toBe(true)
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  if(info.project.name==='desktop')await expect(editor).toHaveValue(draft)
  const capturedToken=(await s.state()).state_token
  const sent:any[]=[];let lost=true
  await page.route('**/arrangement/operations',async route=>{sent.push(route.request().postDataJSON());if(lost){lost=false;await route.fetch();await route.fulfill({status:503,json:{detail:'合成刪除回應遺失'}})}else await route.continue()})
  await openPopup();await startDelete()
  await expect(dialog).toContainText('確認之後另一人新字')
  await confirmDelete()
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await expect(s.area.getByLabel('第 1 排更多操作',{exact:true})).toBeDisabled()
  if(info.project.name==='desktop'){await expect(editor).toHaveValue(draft);await expect(editor).toBeDisabled()}
  const committed=await s.state();await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}));await s.idle()
  expect(sent).toHaveLength(2);expect(sent[0]).toEqual(sent[1]);expect(sent[0].state_token).toBe(capturedToken);expect((await s.state()).layout_revision).toBe(committed.layout_revision)
  await expect(s.area.locator('.grid-selected')).toHaveCount(0);await expect(cellMenu(page).getByRole('button',{name:'編輯文字',exact:true})).toHaveCount(0)
  await expect(editor).toHaveCount(0)
  expect((await s.state()).layout.columns.some((c:any)=>c.id===target.column_id)).toBe(false)
  await page.screenshot({path:info.outputPath('axis-delete-recovered.png'),fullPage:true})
})

test('表格刪除：素食開關明確、歷史舊到新與閱讀不搶捲動',async({page},info)=>{
  test.setTimeout(90000)
  const s=await setup(page,info,'axis-history',3),original=await s.state()
  const toggle=s.area.locator('.vegetarian-toggle')
  const off=await toggle.evaluate(el=>({bg:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}))
  const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/admin'))writes.push(r.url())})
  await activate(info,toggle);await expect(toggle).toHaveAttribute('aria-pressed','true')
  const on=await toggle.evaluate(el=>({bg:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}))
  expect(on.bg).not.toBe(off.bg);expect(on.color).not.toBe(off.color)
  await expect(s.area.locator('.arrangement-cell')).toHaveCount(3);await expect(s.cell(0).locator('.diet-mark')).toHaveText('素')
  expect((await s.state()).layout).toEqual(original.layout);expect(writes).toHaveLength(0)
  await page.screenshot({path:info.outputPath('vegetarian-toggle-on.png')})
  await activate(info,toggle);await expect(toggle).toHaveAttribute('aria-pressed','false')
  for(let i=1;i<=14;i++) {
    await s.op({action:'column_title',column_id:original.layout.columns[0].id,text:`標題 ${i}`})
    const current=await s.state()
    expect((await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,base_version_id:current.latest.id,label:`保存 ${i}`,editor_label:'合成管理員',note:''}})).status()).toBe(200)
  }
  await s.reload();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}))
  const list=s.area.locator('.arrangement-version-list')
  expect(await list.locator('.version-item').evaluateAll(els=>els.map(e=>Number(e.getAttribute('data-version-sequence'))))).toEqual(Array.from({length:15},(_,i)=>i))
  await expect(list.locator('.version-item').last()).toContainText('保存 14最新')
  await expect.poll(()=>list.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2)
  await list.evaluate(el=>el.scrollTop=0);await activate(info,list.locator('.version-item').first())
  await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible()
  const scroll=await list.evaluate(el=>el.scrollTop)
  await activate(info,toggle)
  await expect.poll(()=>list.evaluate(el=>el.scrollTop)).toBe(scroll)
  await activate(info,s.area.getByRole('button',{name:'回目前安排',exact:true}));await s.idle()
  await s.op({action:'column_title',column_id:original.layout.columns[0].id,text:'剛新增'});await s.reload();await s.save('最新保存15');await s.idle();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}))
  await expect(list.locator('.version-item').last()).toContainText('最新保存15最新')
  await expect.poll(()=>list.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2)
  await page.screenshot({path:info.outputPath('history-old-to-new-latest.png'),fullPage:true})
})


test('表格刪除：低位置多文字選單與確認內容可捲、按鈕可達',async({page},info)=>{
  const s=await setup(page,info,'axis-overflow',3)
  await page.setViewportSize({width:info.project.name==='mobile'?390:1000,height:600})
  const layout=(await s.state()).layout,row=layout.rows.length-1
  for(let col=0;col<10;col++)await s.op({action:'text',target:point(layout,row,col),text:`第${col+1}格：`+'需核對的多行文字。'.repeat(35)})
  await s.reload()
  const trigger=s.area.getByLabel(`第 ${row+1} 排更多操作`,{exact:true})
  await trigger.evaluate(el=>{el.scrollIntoView({block:'end'});window.scrollBy(0,-12)})
  await activate(info,trigger)
  const popup=page.getByRole('group',{name:'這個範圍的操作'})
  const inViewport=async(locator:any)=>{const box=await locator.boundingBox();expect(box).toBeTruthy();expect(box!.y).toBeGreaterThanOrEqual(0);expect(box!.y+box!.height).toBeLessThanOrEqual(600)}
  await inViewport(popup);await inViewport(popup.getByRole('button',{name:'關閉'}));await inViewport(popup.getByRole('button',{name:'刪除這一整排'}))
  const body=popup.locator('.axis-delete-content')
  expect(await body.evaluate(el=>el.scrollHeight>el.clientHeight)).toBe(true)
  await body.evaluate(el=>el.scrollTop=el.scrollHeight);await expect(body.locator('li').last()).toBeInViewport()
  await page.screenshot({path:info.outputPath('axis-low-menu.png')})
  await activate(info,popup.getByRole('button',{name:'刪除這一整排'}))
  const dialog=page.getByRole('dialog',{name:'確認刪除這個範圍'})
  await inViewport(dialog);await inViewport(dialog.getByRole('button',{name:'保留這個範圍'}));await inViewport(dialog.getByRole('button',{name:'確認刪除整排'}))
  const content=dialog.locator('.axis-delete-content');expect(await content.evaluate(el=>el.scrollHeight>el.clientHeight)).toBe(true)
  await content.evaluate(el=>el.scrollTop=el.scrollHeight);await expect(content.locator('li').last()).toBeInViewport()
  await page.screenshot({path:info.outputPath('axis-long-confirm.png')})
  await activate(info,dialog.getByRole('button',{name:'保留這個範圍'}));expect((await s.state()).layout.rows).toEqual(layout.rows)
})


async function previewDrag(page:Page,info:TestInfo,s:any,index:number,target:any,fraction:number,mode:string,label:string) {
  const source=s.cell(index).locator('.cell-grip'),slot=s.slot(target)
  await slot.evaluate((el:Element)=>el.scrollIntoView({block:'center',inline:'nearest'}));await source.scrollIntoViewIfNeeded()
  const a=(await source.boundingBox())!,b=(await slot.boundingBox())!
  const start={x:a.x+a.width/2,y:a.y+a.height/2},end={x:b.x+b.width/2,y:b.y+b.height*fraction}
  const cdp=info.project.name==='mobile'?await page.context().newCDPSession(page):null
  if(cdp){await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]});await expect(page.locator('.level-drag-ghost')).toBeVisible();await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[end]})}
  else {await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:8})}
  const preview=page.locator('.drag-intent');await expect(preview).toHaveAttribute('data-drag-intent',mode);await expect(preview).toContainText(label)
  await expect(slot).toHaveClass(new RegExp('drop-'+mode));await expect(s.cell(index)).toHaveCSS('opacity','0.25')
  await page.screenshot({path:info.outputPath(`intent-${mode}-${fraction}.png`)})
  await expect(preview).toHaveAttribute('data-drag-intent',mode) // still the displayed intent immediately before release
  const sent=page.waitForRequest(r=>r.url().endsWith('/arrangement/operations')&&r.method()==='POST')
  if(cdp){await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()}else await page.mouse.up()
  const operation=(await sent).postDataJSON().operation;expect(operation.action).toBe(mode)
  if(mode==='insert')expect(operation.side).toBe(fraction<.5?'before':'after')
  await s.idle();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(preview).toHaveCount(0)
  return operation
}

test('表格互動：中央交換上下插入空白移動與預告一致',async({page},info)=>{
  const s=await setup(page,info,'axis-intents',4),initial=await s.state(),layout=initial.layout
  await s.op({action:'move_empty',registration_id:s.rows[1].id,target:point(layout,1,0)})
  await s.op({action:'move_empty',registration_id:s.rows[2].id,target:point(layout,2,0)})
  await s.op({action:'move_empty',registration_id:s.rows[3].id,target:point(layout,0,1)})
  await s.reload()
  let before=await s.state()
  await previewDrag(page,info,s,0,point(layout,0,1),.5,'swap','交換')
  const audit=await page.request.get(`/api/admin/competitions/${s.comp.id}/history`);expect(audit.status()).toBe(200)
  expect((await audit.json()).filter((r:any)=>r.changes.arrangement_request_id)).toHaveLength(2)
  let after=await s.state();expect(position(after.layout,s.rows[0].id)).toEqual(point(layout,0,1));expect(position(after.layout,s.rows[3].id)).toEqual(point(layout,0,0))
  expect(after.rows.find((r:any)=>r.registration_id===s.rows[0].id).competition_level).toBe(2)
  expect(after.rows.find((r:any)=>r.registration_id===s.rows[3].id).competition_level).toBe(1)
  for(const i of [1,2])expect(after.rows.find((r:any)=>r.registration_id===s.rows[i].id)).toEqual(before.rows.find((r:any)=>r.registration_id===s.rows[i].id))
  await previewDrag(page,info,s,1,point(layout,2,0),.5,'swap','交換')
  after=await s.state();expect(position(after.layout,s.rows[1].id)).toEqual(point(layout,2,0));expect(position(after.layout,s.rows[2].id)).toEqual(point(layout,1,0))
  await previewDrag(page,info,s,0,point(layout,1,0),.1,'insert','上方')
  after=await s.state();expect(position(after.layout,s.rows[0].id)).toEqual(point(layout,1,0));expect(position(after.layout,s.rows[2].id)).toEqual(point(layout,2,0));expect(position(after.layout,s.rows[1].id)).toEqual(point(layout,3,0))
  expect(after.layout.cells.some((c:any)=>c.row_id===layout.rows[0].id&&c.column_id===layout.columns[1].id)).toBe(false)
  await previewDrag(page,info,s,3,point(layout,2,0),.9,'insert','下方')
  after=await s.state();expect(position(after.layout,s.rows[3].id)).toEqual(point(layout,3,0));expect(position(after.layout,s.rows[1].id)).toEqual(point(layout,4,0))
  await previewDrag(page,info,s,0,point(layout,1,1),.5,'move_empty','空白格')
  after=await s.state();expect(position(after.layout,s.rows[0].id)).toEqual(point(layout,1,1));expect(after.layout.cells.filter((c:any)=>c.kind==='registration')).toHaveLength(4)
  expect(new Set(after.layout.cells.filter((c:any)=>c.kind==='registration').map((c:any)=>c.registration_id)).size).toBe(4)
  await openPlayer(info,s.cell(0).locator('.cell-name'));await expect(page.getByRole('dialog',{name:'格位選手000'})).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('歷次比賽級數');await expect(page.getByRole('dialog')).not.toContainText('以下為目前查詢結果')
  await expect(page.getByRole('dialog').getByLabel('移到級數')).toHaveCSS('width','80px')
  await page.screenshot({path:info.outputPath('compact-person-detail.png')});await page.keyboard.press('Escape')
})

test('表格互動：精簡邊界灰階保存復原合併歷史與實際PDF',async({page},info)=>{
  const s=await setup(page,info,'axis-shades',4)
  await s.op({action:'insert_header',before_id:null});let layout=(await s.state()).layout
  await s.op({action:'insert_column',before_id:layout.columns[0].id});layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,0,0),text:'合成灰階表頭'})
  await s.op({action:'merge',start:point(layout,0,0),end:point(layout,0,2)})
  await s.reload();await page.mouse.move(0,0)
  await expect(s.area.getByText('＋新增',{exact:true})).toHaveCount(0);await expect(s.area.locator('.grid-title-edit')).toHaveCount(0)
  const plus=s.area.getByLabel('在第 2 列上方插列',{exact:true})
  if(info.project.name==='desktop'){
    await expect(plus).toHaveCSS('opacity','0');await plus.hover();await expect(plus).toHaveCSS('opacity','1');await expect(s.area.locator('.boundary-line')).toBeVisible();await page.mouse.move(0,0)
    await plus.focus();await expect(plus).toHaveCSS('opacity','1');await page.keyboard.press('Tab')
  }
  for(const [row,shade] of [[1,1],[2,2],[3,3]])await s.op({action:'shade_row',axis_id:layout.rows[row].id,shade})
  await s.op({action:'shade_column',axis_id:layout.columns[0].id,shade:2});await s.reload()
  await expect(s.slot(point(layout,0,0))).toHaveAttribute('data-shade','2') // merged uses all covered axes
  await expect(s.slot(point(layout,1,0))).toHaveAttribute('data-shade','2');await expect(s.slot(point(layout,3,0))).toHaveAttribute('data-shade','3')
  await activate(info,s.area.locator('.vegetarian-toggle'));await expect(s.cell(0).locator('.diet-mark')).toHaveText('素')
  await s.save('三階灰');await s.idle();const saved=(await s.state()).latest
  await s.op({action:'shade_row',axis_id:layout.rows[3].id,shade:0});await s.reload()
  await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeEnabled()
  await s.op({action:'shade_row',axis_id:layout.rows[3].id,shade:3});await s.reload()
  await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeDisabled()
  await editLabel(page,info,s,1,'可雙擊標題');await s.idle()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'三階灰'}))
  await expect(s.slot(point(layout,3,0))).toHaveAttribute('data-shade','3');expect(await (await page.request.get(s.endpoint+'/versions/'+saved.id)).json()).toEqual(saved)
  await page.screenshot({path:info.outputPath('gray-history.png'),fullPage:true})
  await page.evaluate(()=>window.print=()=>{});await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}))
  await page.emulateMedia({media:'print'});const printed=page.locator('.arrangement-print')
  await expect(printed.locator('[data-print-registration]')).toHaveCount(4)
  for(const shade of [1,2,3])await expect(printed.locator(`[data-print-shade="${shade}"]`).first()).toBeVisible()
  await page.screenshot({path:info.outputPath('gray-print.png'),fullPage:true})
  if(info.project.name==='desktop'){
    for(const [index,setting] of [{name:'gray-default'},{name:'gray-background-off',printBackground:false},{name:'gray-background-on',printBackground:true}].entries()) {
      if(index>0){await page.emulateMedia({media:'screen'});await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}));await page.emulateMedia({media:'print'})}
      await expect(printed.locator('[data-print-registration]')).toHaveCount(4)
      await page.pdf({path:info.outputPath(setting.name+'.pdf'),preferCSSPageSize:true,...(setting.printBackground===undefined?{}:{printBackground:setting.printBackground})})
      await expect(printed).toHaveCount(0) // Each PDF fires afterprint and correctly clears its frozen job.
    }
  }
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));await page.emulateMedia({media:'screen'})
})

test('表格互動：歷次參考晚回應空錯誤與快照隔離',async({page},info)=>{
  const s=await setup(page,info,'axis-references',3),initial=await s.state()
  const reference=(name:string,level:number)=>[{competition_id:'synthetic-'+name,competition_name:name,competition_date:'2026-09-01',competition_level:level}]
  let release!:()=>void;const held=new Promise<void>(resolve=>release=resolve)
  let first=true
  await page.route('**/members/*/level-history',async route=>{
    const id=route.request().url().split('/members/')[1].split('/')[0]
    if(id===s.rows[0].member_id&&first){first=false;await held;await route.fulfill({json:reference('已關閉的舊回應',9)})}
    else if(id===s.rows[1].member_id)await route.fulfill({json:reference('另一位的紀錄',6)})
    else await route.fulfill({json:[]})
  })
  await openPlayer(info,s.cell(0).locator('.cell-name'));await expect(page.getByText('讀取歷次紀錄中…')).toBeVisible();await page.keyboard.press('Escape')
  await openPlayer(info,s.cell(1).locator('.cell-name'));await expect(page.getByRole('dialog')).toContainText('另一位的紀錄');release()
  await expect(page.getByRole('dialog')).not.toContainText('已關閉的舊回應');await page.keyboard.press('Escape')
  await openPlayer(info,s.cell(0).locator('.cell-name'));await expect(page.getByRole('dialog')).toContainText('沒有符合條件的歷次紀錄。');await page.keyboard.press('Escape')
  await page.unroute('**/members/*/level-history');await page.route('**/members/*/level-history',route=>route.fulfill({status:503,json:{detail:'合成參考查詢失敗'}}))
  await openPlayer(info,s.cell(2).locator('.cell-name'));await expect(page.getByRole('dialog').getByRole('alert')).toContainText('無法讀取歷次紀錄');await page.keyboard.press('Escape')
  await page.unroute('**/members/*/level-history')
  await s.op({action:'shade_row',axis_id:initial.layout.rows[0].id,shade:1});await s.reload();await s.save('快照參考分離');await s.idle()
  const frozen=(await s.state()).latest
  await s.op({action:'move_empty',registration_id:s.rows[0].id,target:point(initial.layout,2,8)})
  const current=await s.state(),r=current.rows.find((v:any)=>v.registration_id===s.rows[0].id)
  expect((await page.request.put(`/api/admin/registrations/${r.registration_id}/diet`,{headers:s.headers,data:{version:r.version,request_id:crypto.randomUUID(),diet:'omnivore'}})).status()).toBe(200)
  await s.reload();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'快照參考分離'}))
  await page.route('**/members/*/level-history',route=>route.fulfill({json:reference('目前參考區',7)}))
  await openPlayer(info,s.cell(0).locator('.cell-name'))
  await expect(page.getByRole('dialog')).toContainText('本場餐食：素食');await expect(page.getByRole('dialog')).toContainText('當次級數：1 級');await expect(page.getByRole('dialog')).toContainText('以下為目前查詢結果');await expect(page.getByRole('dialog')).toContainText('目前參考區')
  await expect(page.getByRole('dialog').getByLabel('移到級數')).toHaveCount(0)
  expect(await (await page.request.get(s.endpoint+'/versions/'+frozen.id)).json()).toEqual(frozen)
  await page.screenshot({path:info.outputPath('history-reference-separation.png')});await page.keyboard.press('Escape')
  await activate(info,s.area.getByRole('button',{name:'回目前安排',exact:true}))
  await page.unroute('**/members/*/level-history')
  let late!:()=>void;const waiting=new Promise<void>(resolve=>late=resolve)
  await page.route('**/members/*/level-history',async route=>{await waiting;await route.fulfill({json:reference('換場晚回應',8)})})
  await openPlayer(info,s.cell(0).locator('.cell-name'));await expect(page.getByText('讀取歷次紀錄中…')).toBeVisible();await page.keyboard.press('Escape');await s.choose(true);late()
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByText('換場晚回應')).toHaveCount(0)
})


test('局部底色：選區右鍵手機鍵盤與失敗原樣恢復',async({page},info)=>{
  const s=await setup(page,info,'axis-cell-menu',3),initial=await s.state(),a=point(initial.layout,2,0),b=point(initial.layout,3,1)
  await rectangle(page,info,s,a,b)
  await expect(s.area.locator('.grid-selected')).toHaveCount(4)
  const menu=cellMenu(page).getByRole('group',{name:'表格底色'})
  const open=async()=>{
    if(info.project.name==='desktop')await s.slot(a).click({button:'right'})
    else await openSelectedCellMenu(page,info,s)

    await expect(menu).toBeVisible();await expect(s.area.locator('.grid-selected')).toHaveCount(4)
    for(const shade of [1,2,3])expect(await menu.getByRole('button',{name:`淺灰 ${shade}`,exact:true}).textContent()).toBe('')
    await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  }
  await open();await page.keyboard.press('Escape');await expect(s.area.locator('.grid-selected')).toHaveCount(4)
  await open();const sent:any[]=[];let first=true
  await page.route('**/arrangement/operations',async route=>{
    sent.push(route.request().postDataJSON());const response=await route.fetch()
    if(first){first=false;await route.abort('failed')}else await route.fulfill({response})
  })
  await activate(info,menu.getByRole('button',{name:'淺灰 1',exact:true}))
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible()
  await expect(s.area.locator('.grid-selected')).toHaveCount(4)
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試'}));await s.idle()
  expect(sent[0]).toEqual(sent[1]);expect(sent[0].operation).toEqual({action:'shade_cells',start:a,end:b,shade:1})
  await expect(s.area.locator('.grid-selected')).toHaveCount(4);await expect(s.slot(b)).toHaveAttribute('data-shade','1')
  expect((await s.state()).rows).toEqual(initial.rows);expect((await s.state()).layout.cells).toEqual(initial.layout.cells)
  await page.unroute('**/arrangement/operations')
  await rectangle(page,info,s,a,b);await open()
  await s.op({action:'shade_row',axis_id:initial.layout.rows[4].id,shade:2})
  await activate(info,menu.getByRole('button',{name:'淺灰 3',exact:true}))
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  await expect(s.area.locator('.grid-selected')).toHaveCount(4)
  expect((await s.state()).layout.cell_shades.every((c:any)=>c.shade===1)).toBe(true)
  await page.screenshot({path:info.outputPath('cell-shade-conflict.png')})
})

test('局部底色：格位橘底合併歷史與實際PDF',async({page},info)=>{
  const s=await setup(page,info,'axis-cell-persist',3),initial=await s.state(),layout=initial.layout,a=point(layout,0,0),b=point(layout,1,0)
  await s.op({action:'shade_row',axis_id:layout.rows[0].id,shade:3})
  await s.op({action:'shade_cells',start:a,end:a,shade:1});await s.reload()
  await expect(s.slot(a)).toHaveAttribute('data-shade','1')
  // Detail provides a touch and keyboard entrance for a player cell.
  await s.cell(0).locator('.cell-name').focus();await page.keyboard.press('Enter')
  const detail=page.getByRole('dialog',{name:'格位選手000'})
  await expect(detail.locator('.detail-diet')).toHaveCSS('background-color','rgb(213, 239, 219)')
  await expect(detail.getByRole('button',{name:'選取儲存格'})).toHaveCount(0)
  await detail.getByRole('button',{name:'關閉',exact:true}).click();await activate(info,s.cell(0).locator('.cell-name'));await expect(s.slot(a)).toHaveClass(/grid-selected/)
  const menu=cellMenu(page)
  await openSelectedCellMenu(page,info,s)
  await menu.getByRole('button',{name:'白色',exact:true}).focus();await page.keyboard.press('Enter');await s.idle()
  await expect(s.slot(a)).toHaveAttribute('data-shade','0');await expect(s.slot(a)).toHaveCSS('background-color','rgb(255, 255, 255)')
  const white=(await s.state()).layout
  expect(white.rows.find((row:any)=>row.id===a.row_id).shade).toBe(3)
  expect(white.cell_shades.find((cell:any)=>cell.row_id===a.row_id&&cell.column_id===a.column_id)?.shade).toBe(0)
  await s.op({action:'shade_cells',start:a,end:a,shade:1})
  await s.op({action:'shade_cells',start:b,end:b,shade:2});await s.reload()
  await previewDrag(page,info,s,0,b,.5,'move_empty','空白格')
  await expect(s.cell(0)).toHaveCSS('background-color','rgb(255, 225, 174)');await expect(s.slot(a)).toHaveAttribute('data-shade','1');await expect(s.slot(b)).toHaveAttribute('data-shade','2')
  await activate(info,s.area.locator('.vegetarian-toggle'));await expect(s.cell(0).locator('.diet-mark')).toBeVisible()
  await s.save('格位局部灰');await s.idle();const frozen=(await s.state()).latest
  await expect(s.cell(0)).toHaveCSS('background-color','rgba(0, 0, 0, 0)');await expect(s.slot(b)).toHaveAttribute('data-shade','2')
  for(const [i,css] of [[1,'rgb(227, 227, 227)'],[2,'rgba(0, 0, 0, 0)']] as const){
    await openPlayer(info,s.cell(i).locator('.cell-name'));await expect(page.getByRole('dialog').locator('.detail-diet')).toHaveCSS('background-color',css);await page.keyboard.press('Escape')
  }
  await activate(info,s.slot(a).locator('.grid-empty'));if(info.project.name==='mobile'){await activate(info,cellMenu(page).getByRole('button',{name:'範圍選取',exact:true}));await activate(info,s.cell(0).locator('.cell-name'))}else await s.slot(b).click({modifiers:['Shift'],position:{x:1,y:1}})
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(s.area.locator('.grid-selected')).toHaveCount(2)
  await activate(info,cellMenu(page).getByRole('button',{name:'取消選取',exact:true}))
  const c=point(layout,3,0),d=point(layout,3,1)
  await s.op({action:'shade_cells',start:c,end:c,shade:1});await s.op({action:'shade_cells',start:d,end:d,shade:3})
  await s.op({action:'merge',start:c,end:d});await s.reload();await expect(s.slot(c)).toHaveAttribute('data-shade','3')
  await activate(info,s.slot(c).locator('.grid-empty'));await expect(s.slot(c)).toHaveClass(/grid-selected/)
  await activate(info,menu.getByRole('button',{name:'淺灰 2',exact:true}));await s.idle()
  let current=await s.state();expect(current.layout.cell_shades.filter((v:any)=>v.row_id===c.row_id)).toHaveLength(2)
  await s.op({action:'unmerge',merge_id:current.layout.merges[0].id});await s.reload()
  await expect(s.slot(c)).toHaveAttribute('data-shade','2');await expect(s.slot(d)).toHaveAttribute('data-shade','2')
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'格位局部灰'}))
  await expect(s.cell(0)).toHaveCSS('background-color','rgb(255, 225, 174)');await expect(s.slot(b)).toHaveAttribute('data-shade','2')
  expect(await (await page.request.get(s.endpoint+'/versions/'+frozen.id)).json()).toEqual(frozen)
  await page.screenshot({path:info.outputPath('local-gray-history.png'),fullPage:true})
  await page.evaluate(()=>window.print=()=>{})
  for(const name of info.project.name==='desktop'?['local-default','local-background-off']:['local-screen']){
    await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}));await page.emulateMedia({media:'print'})
    const print=page.locator('.arrangement-print');await expect(print.locator('[data-print-registration]')).toHaveCount(3)
    await expect(print.locator(`[data-print-row="${a.row_id}"] td`).first().locator('[data-print-shade="1"]')).toHaveCount(1)
    await expect(print.locator(`[data-print-row="${b.row_id}"] td`).first().locator('[data-print-shade="2"]')).toHaveCount(1)
    if(info.project.name==='desktop'){await page.pdf({path:info.outputPath(name+'.pdf'),preferCSSPageSize:true,...(name==='local-background-off'?{printBackground:false}:{})});await expect(print).toHaveCount(0)}
    else{await page.screenshot({path:info.outputPath(name+'.png'),fullPage:true});await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')))}
    await page.emulateMedia({media:'screen'})
  }
})



test('編輯工具：上方固定入口與卡片外點關閉',async({page},info)=>{
  const s=await setup(page,info,'edit-toolbar',3),layout=(await s.state()).layout,a=point(layout,2,0),b=point(layout,3,1)
  const toolbar=cellMenu(page),table=s.area.locator('.grid-table')
  await expect(s.area.getByRole('toolbar',{name:'表格編輯工具'})).toHaveCount(0)
  const before=await table.evaluate(el=>el.getBoundingClientRect().top+window.scrollY)
  await rectangle(page,info,s,a,b);expect(await table.evaluate(el=>el.getBoundingClientRect().top+window.scrollY)).toBe(before)
  if(info.project.name==='desktop'){
    await s.slot(a).click({button:'right'})
  }else await openSelectedCellMenu(page,info,s)
  await expect(toolbar).toBeVisible();await expect(toolbar.getByRole('group',{name:'表格底色'})).toBeVisible()
  for(const shade of [1,2,3])await expect(toolbar.getByRole('button',{name:`淺灰 ${shade}`,exact:true})).toBeVisible()
  await expect(s.area.locator('.grid-selected')).toHaveCount(4)
  await page.keyboard.press('Escape');await expect(toolbar).toHaveCount(0)
  if(info.project.name==='desktop'){
    await s.slot(a).click({button:'right'});await expect(toolbar).toBeVisible()
  }else await openSelectedCellMenu(page,info,s)
  await activate(info,toolbar.getByRole('button',{name:'合併儲存格',exact:true}));await s.idle()
  await expect(s.slot(a)).toHaveAttribute('colspan','2')
  await activate(info,toolbar.getByRole('button',{name:'解除合併儲存格',exact:true}));await s.idle();await expect(s.slot(a)).not.toHaveAttribute('colspan','2')
  await expect(toolbar).toHaveCount(0)
  if(info.project.name==='desktop'){
    await s.slot(a).click({button:'right'});await expect(toolbar).toBeVisible();await page.keyboard.press('Escape')
  }
  await page.screenshot({path:info.outputPath('cell-menu-screen.png')})
  await openPlayer(info,s.cell(0).locator('.cell-name'));const dialog=page.getByRole('dialog',{name:'格位選手000'})
  await expect(dialog.getByRole('button',{name:'關閉',exact:true})).toHaveText('×')
  await dialog.getByRole('heading',{name:'格位選手000'}).click();await expect(dialog).toBeVisible()
  const box=(await dialog.boundingBox())!,outside={x:Math.max(2,box.x-4),y:Math.max(2,box.y-4)}
  if(info.project.name==='desktop'){await page.mouse.move(box.x+50,box.y+30);await page.mouse.down();await page.mouse.move(outside.x,outside.y);await page.mouse.up();await expect(dialog).toBeVisible()}
  await page.screenshot({path:info.outputPath('detail-close-x.png')})
  await page.mouse.click(outside.x,outside.y);await expect(dialog).toHaveCount(0)
  await openPlayer(info,s.cell(1).locator('.cell-name'));await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0)
})

async function textEdit(page:Page,info:TestInfo,s:any,target:any,value:string){
  await activate(info,s.slot(target).locator('.grid-empty'))
  await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
  const dialog=page.getByRole('dialog',{name:'儲存格文字'});await dialog.getByLabel('儲存格文字內容').fill(value)
  await activate(info,dialog.getByRole('button',{name:'儲存文字',exact:true}));await s.idle();await expect(dialog).toHaveCount(0)
}

test('編輯工具：復原連續操作分段與原樣重試',async({page},info)=>{
  const s=await setup(page,info,'edit-undo',3),initial=await s.state(),a=point(initial.layout,2,0)
  const toolbar=cellMenu(page),undo=toolbar.getByRole('button',{name:'復原上一個動作',exact:true})
  await activate(info,s.slot(a).locator('.grid-empty'));await openSelectedCellMenu(page,info,s)
  await expect(undo).toBeDisabled()
  await textEdit(page,info,s,a,'第一筆文字');await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,toolbar.getByRole('button',{name:'淺灰 2',exact:true}));await s.idle()
  await openSelectedCellMenu(page,info,s);await expect(undo).toBeEnabled();await undo.focus();await page.keyboard.press('Control+z');await s.idle()
  expect((await s.state()).layout.cell_shades??[]).toHaveLength(0);expect((await s.state()).layout.cells.find((c:any)=>c.text==='第一筆文字')).toBeTruthy()
  await activate(info,undo);await s.idle();expect((await s.state()).layout.cells).toEqual(initial.layout.cells);await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled()
  await textEdit(page,info,s,a,'新的分支');await openSelectedCellMenu(page,info,s);await expect(undo).toBeEnabled()
  let first=true;const sent:any[]=[]
  await page.route('**/arrangement/operations',async route=>{sent.push(route.request().postDataJSON());const response=await route.fetch();if(first){first=false;await route.abort('failed')}else await route.fulfill({response})})
  await activate(info,undo);await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible();await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試'}));await s.idle();expect(sent[0]).toEqual(sent[1]);expect(sent[0].operation.action).toBe('undo');await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled()
  await page.unroute('**/arrangement/operations')
  await textEdit(page,info,s,a,'保存的新基準');await s.save('復原分段');await s.idle();await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled()
  const frozen=(await s.state()).latest
  await textEdit(page,info,s,a,'保存後修改');await openSelectedCellMenu(page,info,s);await undo.focus();await page.keyboard.press('Meta+z');await s.idle();await expect(s.slot(a)).toContainText('保存的新基準');await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled()
  expect(await (await page.request.get(s.endpoint+'/versions/'+frozen.id)).json()).toEqual(frozen)
  await textEdit(page,info,s,a,'他人修改前');await s.op({action:'text',target:point(initial.layout,3,0),text:'外部修改'})
  await activate(info,undo);await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle();await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled();await expect(s.slot(a)).toContainText('他人修改前')
  await textEdit(page,info,s,a,'重新開始');await openSelectedCellMenu(page,info,s);await expect(undo).toBeEnabled();await page.reload();await s.choose();await openSelectedCellMenu(page,info,s);await expect(undo).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'復原分段'}));await expect(toolbar).toHaveCount(0)
  const unchanged=await s.state();await page.keyboard.press('Control+z');expect(await s.state()).toEqual(unchanged)
})

test('編輯工具：文字外點保存取消組字與失敗草稿',async({page},info)=>{
  const s=await setup(page,info,'edit-outside',3),layout=(await s.state()).layout,a=point(layout,2,0),b=point(layout,3,0)
  const writes:any[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  if(info.project.name==='desktop'){
    await s.slot(a).locator('.grid-empty').dblclick();const input=page.getByLabel('直接編輯文字');await input.fill('外點保存')
    await input.press('Control+z');expect(writes).toHaveLength(0);await input.fill('外點保存')
    await input.dispatchEvent('compositionstart');await s.slot(b).click();expect(writes).toHaveLength(0);await expect(input).toHaveValue('外點保存')
    await input.dispatchEvent('compositionend');await s.slot(b).click();await s.idle();await expect(input).toHaveCount(0);await expect(s.slot(a)).toContainText('外點保存');expect(writes).toHaveLength(1)
    await expect(s.slot(b)).not.toHaveClass(/grid-selected/)
  }
  await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}))
  let dialog=page.getByRole('dialog',{name:'儲存格文字'});await dialog.getByLabel('儲存格文字內容').fill('取消這次輸入');await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0)
  await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}));dialog=page.getByRole('dialog',{name:'儲存格文字'});await dialog.getByLabel('儲存格文字內容').fill('手機外點保存')
  let box=(await dialog.boundingBox())!;await page.mouse.click(Math.max(2,box.x-4),Math.max(2,box.y-4));await s.idle();await expect(dialog).toHaveCount(0);await expect(s.slot(a)).toContainText('手機外點保存')
  await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}));await dialog.getByLabel('儲存格文字內容').fill('衝突仍保留')
  await s.op({action:'text',target:b,text:'外部文字'})
  box=(await dialog.boundingBox())!;await page.mouse.click(Math.max(2,box.x-4),Math.max(2,box.y-4))
  await expect(dialog.getByLabel('儲存格文字內容')).toHaveValue('衝突仍保留');await expect(dialog.getByRole('button',{name:'返回表格核對（保留文字）'})).toBeVisible()
  await activate(info,dialog.getByRole('button',{name:'返回表格核對（保留文字）'}));await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  await activate(info,cellMenu(page).getByRole('button',{name:'編輯文字',exact:true}));await expect(dialog.getByLabel('儲存格文字內容')).toHaveValue('衝突仍保留')
  await activate(info,dialog.getByRole('button',{name:'儲存文字',exact:true}));await s.idle();await expect(dialog).toHaveCount(0);await expect(s.slot(a)).toContainText('衝突仍保留')
})


test('表頭修正：上色回應遺失有界等待與原樣確認',async({page},info)=>{
  const s=await setup(page,info,'edit-header-timeout',3),before=await s.state(),a=point(before.layout,2,0)
  await page.clock.install();let release!:()=>void;const held=new Promise<void>(resolve=>release=resolve),sent:any[]=[];let first=true
  await page.route('**/arrangement/operations',async route=>{
    sent.push(route.request().postDataJSON());const response=await route.fetch()
    if(first){first=false;await held;await route.fulfill({response}).catch(()=>{})}else await route.fulfill({response})
  })
  await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
  await expect.poll(async()=>(await s.state()).layout_revision).toBe(before.layout_revision+1)
  await page.clock.fastForward(21000)
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await page.screenshot({path:info.outputPath('timeout-safe-recovery.png')})
  await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}));await s.idle()
  expect(sent[0]).toEqual(sent[1]);expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
  await expect(s.slot(a)).toHaveAttribute('data-shade','2');release();await page.unroute('**/arrangement/operations')
  await activate(info,s.slot(a).locator('.grid-empty'));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 1',exact:true}));await s.idle();await expect(s.slot(a)).toHaveAttribute('data-shade','1')
})


test('表頭修正：回應內容與初次讀取逾時可恢復',async({page},info)=>{
  const s=await setup(page,info,'edit-header-body-timeout',3),before=await s.state(),toolbar=cellMenu(page)
  await page.clock.install()
  const writes:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations')&&r.method()==='POST')writes.push(r.postDataJSON())})
  // Deliberately stall JSON decoding after real GET headers arrive, then honor abort.
  await page.evaluate(endpoint=>{
    const original=window.fetch;let once=true;(window as any).bodyHeld=false
    window.fetch=async(input,options)=>{
      const response=await original(input,options)
      if(once&&String(input)===endpoint&&(!options?.method||options.method==='GET')){
        once=false;response.json=()=>new Promise((_resolve,reject)=>{(window as any).bodyHeld=true;options?.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true})})
      }
      return response
    }
  },s.endpoint)
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,toolbar.getByRole('button',{name:'淺灰 3',exact:true}))
  await expect.poll(()=>page.evaluate(()=>(window as any).bodyHeld)).toBe(true);await page.clock.fastForward(21000)
  await expect(s.area.getByRole('button',{name:'讀回目前安排',exact:true})).toBeVisible();await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'讀回目前安排',exact:true}));await s.idle();expect(writes).toHaveLength(1)
  expect((await s.state()).layout_revision).toBe(before.layout_revision+1);await expect(s.area.locator('[data-grid-header]').first()).toHaveAttribute('data-header-shade','3')
  await s.choose(true)
  let entered=false,release!:()=>void;const held=new Promise<void>(resolve=>release=resolve)
  await page.route('**/arrangement',async route=>{if(route.request().url().endsWith(s.endpoint)){entered=true;await held;await route.continue().catch(()=>{})}else await route.continue()})
  await page.getByLabel('選擇比賽',{exact:true}).selectOption(s.comp.id)
  await expect.poll(()=>entered).toBe(true);await page.clock.fastForward(21000)
  await expect(s.area.getByRole('button',{name:'重新讀取',exact:true})).toBeEnabled();await expect(s.area.getByRole('alert').first()).toContainText('未及時回應')
  release();await page.unroute('**/arrangement');await s.area.getByRole('button',{name:'重新讀取',exact:true}).click();await s.idle();expect(writes).toHaveLength(1)
  await activate(info,s.area.getByLabel('選取第 2 欄表頭',{exact:true}));await page.route('**/arrangement/operations',r=>r.abort('internetdisconnected'))
  await activate(info,toolbar.getByRole('button',{name:'淺灰 1',exact:true}));await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await page.unroute('**/arrangement/operations');await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}));await s.idle()
  expect(writes[1]).toEqual(writes[2]);await expect(s.area.locator('[data-grid-header]').nth(1)).toHaveAttribute('data-header-shade','1')
})

test('表頭修正：單選工具列文字色階復原歷史及PDF',async({page},info)=>{
  const s=await setup(page,info,'edit-header-contract',3),initial=await s.state(),layout=initial.layout,toolbar=cellMenu(page),header=s.area.getByLabel('選取第 1 欄表頭',{exact:true}),th=s.area.locator(`[data-grid-header="${layout.columns[0].id}"]`)
  const writes:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations')&&r.method()==='POST')writes.push(r.postDataJSON().operation)})
  await activate(info,header);await expect(th).toHaveClass(/grid-selected/);await expect(page.getByLabel('直接編輯文字')).toHaveCount(0);await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(header).toHaveCSS('background-color','rgba(0, 0, 0, 0)')
  await page.screenshot({path:info.outputPath('header-selected-toolbar-screen.png'),fullPage:true})
  await openSelectedCellMenu(page,info,s)
  await expect(toolbar.getByRole('button',{name:'合併儲存格',exact:true})).toBeDisabled();await expect(toolbar.getByRole('button',{name:'解除合併儲存格',exact:true})).toBeDisabled()
  if(info.project.name==='desktop'){
    const body=s.slot(point(layout,2,0));await page.keyboard.press('Escape');await expect(toolbar).toHaveCount(0);await body.click({button:'right'});await page.keyboard.press('Escape');await expect(th).not.toHaveClass(/grid-selected/);await expect(body).toHaveClass(/grid-selected/)
    await activate(info,toolbar.getByRole('button',{name:'淺灰 2',exact:true}));await s.idle();await expect(body).toHaveAttribute('data-shade','2');await expect(th).toHaveAttribute('data-header-shade','0')
    expect(writes.at(-1).action).toBe('shade_cells');await activate(info,toolbar.getByRole('button',{name:'復原上一個動作',exact:true}));await s.idle();await activate(info,header)
  }
  await activate(info,toolbar.getByRole('button',{name:'淺灰 3',exact:true}));await s.idle();await expect(th).toHaveAttribute('data-header-shade','3')
  await expect(s.slot(point(layout,0,0))).toHaveAttribute('data-shade','0');expect((await s.state()).layout.cells).toEqual(initial.layout.cells)
  await openSelectedCellMenu(page,info,s);await toolbar.getByRole('button',{name:'復原上一個動作',exact:true}).focus();await page.keyboard.press('Control+z');await s.idle();await expect(th).toHaveAttribute('data-header-shade','0')
  await header.focus();await page.keyboard.press('Enter');await expect(th).toHaveClass(/grid-selected/);await expect(page.getByRole('dialog')).toHaveCount(0)
  await activate(info,toolbar.getByRole('button',{name:'編輯文字',exact:true}));const dialog=page.getByRole('dialog',{name:'儲存格文字'});await dialog.getByLabel('儲存格文字內容').fill('第一級表頭')
  await activate(info,dialog.getByRole('button',{name:'儲存文字',exact:true}));await s.idle();await expect(header).toHaveText('第一級表頭')
  await activate(info,header);await activate(info,toolbar.getByRole('button',{name:'淺灰 2',exact:true}));await s.idle()
  await activate(info,header);await activate(info,toolbar.getByRole('button',{name:'白色',exact:true}));await s.idle();await expect(th).toHaveAttribute('data-header-shade','0')
  if(info.project.name==='desktop'){
    await header.dblclick();await page.getByLabel('直接編輯文字').fill('第一級完整表頭');const count=writes.length
    await activate(info,toolbar.getByRole('button',{name:'淺灰 3',exact:true}));await s.idle();expect(writes.slice(count).map(v=>v.action)).toEqual(['column_title']);await expect(th).toHaveAttribute('data-header-shade','0')
    await activate(info,toolbar.getByRole('button',{name:'淺灰 3',exact:true}));await s.idle()
  }else{await activate(info,header);await activate(info,toolbar.getByRole('button',{name:'淺灰 3',exact:true}));await s.idle()}
  await page.keyboard.press('Escape');await expect(toolbar).toHaveCount(0)
  await activate(info,s.slot(point(layout,2,0)).locator('.grid-empty'));await expect(th).not.toHaveClass(/grid-selected/)
  if(info.project.name==='mobile'){await activate(info,toolbar.getByRole('button',{name:'範圍選取',exact:true}));await activate(info,header)}else await header.click({modifiers:['Shift']})
  await expect(s.area.locator('td.grid-selected')).toHaveCount(3);await expect(th).toHaveClass(/grid-selected/);await openSelectedCellMenu(page,info,s)
  await expect(toolbar.getByRole('button',{name:'合併儲存格',exact:true})).toBeDisabled();await expect(toolbar).toContainText('不能跨越級數表頭合併')
  expect((await s.state()).layout.columns.map((c:any)=>[c.id,c.kind,c.level])).toEqual(layout.columns.map((c:any)=>[c.id,c.kind,c.level]))
  await s.save('表頭顯示保存');await s.idle();const frozen=(await s.state()).latest
  await activate(info,header);await activate(info,toolbar.getByRole('button',{name:'淺灰 1',exact:true}));await s.idle()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'表頭顯示保存'}));await expect(th).toHaveAttribute('data-header-shade','3');await expect(s.slot(point(layout,0,0))).toHaveAttribute('data-shade','0')
  expect(await (await page.request.get(s.endpoint+'/versions/'+frozen.id)).json()).toEqual(frozen)
  await page.screenshot({path:info.outputPath('header-history.png'),fullPage:true});await page.evaluate(()=>window.print=()=>{})
  for(const name of info.project.name==='desktop'?['header-default','header-background-off']:['header-mobile']){
    await activate(info,s.area.getByRole('button',{name:'列印安排',exact:true}));await page.emulateMedia({media:'print'})
    const print=page.locator('.arrangement-print');await expect(print.locator(`[data-print-header="${layout.columns[0].id}"] [data-print-shade="3"]`)).toHaveCount(1)
    await expect(print.locator(`[data-print-cell="${layout.rows[0].id}/${layout.columns[0].id}"] [data-print-shade]`)).toHaveCount(0)
    if(info.project.name==='desktop'){await page.pdf({path:info.outputPath(name+'.pdf'),preferCSSPageSize:true,...(name==='header-background-off'?{printBackground:false}:{})});await expect(print).toHaveCount(0)}
    else{await page.screenshot({path:info.outputPath(name+'.png'),fullPage:true});await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')))}
    await page.emulateMedia({media:'screen'})
  }
})


test('雙欄選格：單雙擊鍵盤範圍與唯讀資訊',async({page},info)=>{
  const s=await setup(page,info,'edit-panels-click',3),initial=await s.state(),name=s.cell(0).locator('.cell-name'),toolbar=cellMenu(page)
  const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/admin'))writes.push(r.url())})
  await activate(info,name);await expect(s.cell(0).locator('..')).toHaveClass(/grid-selected/);await expect(page.getByRole('dialog')).toHaveCount(0)
  expect((await s.state()).state_token).toBe(initial.state_token);expect(writes).toHaveLength(0)
  await activate(info,toolbar.getByRole('button',{name:'取消選取',exact:true}))
  await openPlayer(info,name);const dialog=page.getByRole('dialog',{name:'格位選手000'})
  await expect(dialog).toBeVisible();await expect(dialog.getByRole('button',{name:'選取儲存格'})).toHaveCount(0)
  await dialog.getByRole('button',{name:'關閉',exact:true}).click()
  if(info.project.name==='mobile'){
    await name.tap();await page.waitForTimeout(550);await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
    await s.cell(1).locator('.cell-name').tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  }
  await activate(info,toolbar.getByRole('button',{name:'取消選取',exact:true}))
  await name.focus();const scroll=await page.evaluate(()=>window.scrollY);await page.keyboard.press('Space')
  await expect(s.cell(0).locator('..')).toHaveClass(/grid-selected/);await expect(page.getByRole('dialog')).toHaveCount(0);expect(await page.evaluate(()=>window.scrollY)).toBe(scroll)
  await page.keyboard.press('Enter');await expect(dialog).toBeVisible();await page.keyboard.press('Escape')
  const empty=point(initial.layout,2,0)
  await activate(info,s.slot(empty).locator('.grid-empty'))
  if(info.project.name==='mobile')await activate(info,toolbar.getByRole('button',{name:'範圍選取',exact:true}))
  if(info.project.name==='mobile')await openPlayer(info,name);else await name.dblclick({modifiers:['Shift']})
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(s.area.locator('td.grid-selected')).toHaveCount(3)
  await openSelectedCellMenu(page,info,s);await expect(toolbar.getByRole('button',{name:'合併儲存格',exact:true})).toBeDisabled()
  await page.screenshot({path:info.outputPath('player-range-screen.png'),fullPage:true})
  expect(writes).toHaveLength(0)
  await s.op({action:'column_title',column_id:initial.layout.columns[0].id,text:'選手資訊保存'});await s.reload();await s.save('資訊快照');await s.idle()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await activate(info,s.area.locator('.version-item').filter({hasText:'資訊快照'}))
  await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible();await expect(cellMenu(page)).toHaveCount(0)
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toHaveCount(0);await expect(s.area.locator('.cell-grip')).toHaveCount(0)
  const historyWrites=writes.length
  await activate(info,name);await expect(page.getByRole('dialog')).toHaveCount(0);expect(writes).toHaveLength(historyWrites)
  await name.focus();await page.keyboard.press('Enter');await expect(dialog).toBeVisible();await expect(dialog.getByLabel('移到級數')).toHaveCount(0);expect(writes).toHaveLength(historyWrites)
  await page.screenshot({path:info.outputPath('history-player-detail-screen.png')});await page.keyboard.press('Escape')
  await openPlayer(info,name);await expect(dialog).toBeVisible();await page.keyboard.press('Escape')
})

test('雙欄選格：寬桌面筆電手機布局與獨立捲動',async({page},info)=>{
  test.setTimeout(90000)
  const s=await setup(page,info,'edit-panels-layout',20),initial=await s.state()
  for(let i=1;i<=12;i++){
    await s.op({action:'column_title',column_id:initial.layout.columns[0].id,text:`第${i}次表頭`})
    const current=await s.state()
    expect((await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,base_version_id:current.latest.id,label:`版本 ${i}`,editor_label:'合成管理員',note:''}})).status()).toBe(200)
  }
  for(let i=0;i<20;i++)await s.op({action:'move_empty',registration_id:s.rows[i].id,target:point(initial.layout,4+Math.floor(i/10),i%10)})
  await s.reload();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}))
  const diff=s.area.getByRole('complementary',{name:'該版本變動'}),versions=s.area.getByRole('complementary',{name:'版本紀錄'}),list=versions.locator('.arrangement-version-list')
  await expect(diff.locator('li')).toHaveCount(20);await expect(list.locator('.version-item').last()).toContainText('版本 12最新')
  await expect.poll(()=>list.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2)
  for(const width of info.project.name==='desktop'?[1920,1440]:[390]){
    await page.setViewportSize({width,height:900})
    const sheet=(await s.area.locator('.arrangement-sheet').boundingBox())!,d=(await diff.boundingBox())!,v=(await versions.boundingBox())!
    if(width>=1700){expect(sheet.width).toBeGreaterThan(1100);expect(d.x).toBeGreaterThan(sheet.x+sheet.width);expect(v.x).toBeGreaterThan(d.x+d.width);expect(Math.abs(d.y-v.y)).toBeLessThan(1)}
    else if(width>700){expect(sheet.width).toBeGreaterThan(1200);expect(d.y).toBeGreaterThan(sheet.y+sheet.height);expect(v.x).toBeGreaterThan(d.x);expect(Math.abs(d.y-v.y)).toBeLessThan(1)}
    else{expect(d.y).toBeGreaterThan(sheet.y+sheet.height);expect(v.y).toBeGreaterThan(d.y+d.height)}
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1)
    await page.screenshot({path:info.outputPath(`history-panels-${width}-screen.png`),fullPage:true})
  }
  const versionScroll=await list.evaluate(el=>el.scrollTop)
  await diff.locator('.arrangement-diff-scroll').evaluate(el=>el.scrollTop=100);expect(await diff.locator('.arrangement-diff-scroll').evaluate(el=>el.scrollTop)).toBeGreaterThan(0);expect(await list.evaluate(el=>el.scrollTop)).toBe(versionScroll)
  await list.evaluate(el=>el.scrollTop=0);await activate(info,list.locator('.version-item').first());await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible()
  await expect(diff).toContainText('相較 前一保存版本');await expect(diff.locator('li')).toHaveCount(0)
  const oldScroll=await list.evaluate(el=>el.scrollTop);await activate(info,s.area.locator('.vegetarian-toggle'))
  await expect.poll(()=>list.evaluate(el=>el.scrollTop)).toBe(oldScroll)
})


async function downloadArrangement(page:Page,info:TestInfo,s:any,name:string,snapshot:any){
  const pending=page.waitForEvent('download');await s.area.getByRole('button',{name:'匯出 Excel',exact:true}).click()
  const download=await pending;expect(download.suggestedFilename()).toMatch(/\.xlsx$/)
  await download.saveAs(info.outputPath(name+'.xlsx'));expect(await download.failure()).toBeNull()
  await writeFile(info.outputPath(name+'.json'),JSON.stringify(snapshot,null,2))
  await expect(s.area.getByRole('button',{name:'匯出 Excel',exact:true})).toBeEnabled()
}

test('匯出精修：工具列與可編輯Excel完整格位歷史零寫入',async({page},info)=>{
  const s=await setup(page,info,'edit-export',3)
  await s.op({action:'insert_header',before_id:null});await s.op({action:'insert_column',before_id:(await s.state()).layout.columns[0].id})
  let layout=(await s.state()).layout
  await s.op({action:'text',target:point(layout,0,0),text:'=SUM(1,2)'});await s.op({action:'merge',start:point(layout,0,0),end:point(layout,0,2)})
  await s.op({action:'text',target:point(layout,1,0),text:'@隊名\n臺灣 羽球 🏸'})
  await s.op({action:'text',target:point(layout,3,0),text:'-自訂文字'});await s.op({action:'merge',start:point(layout,3,0),end:point(layout,4,1)})
  await s.op({action:'merge',start:point(layout,5,0),end:point(layout,6,1)})
  await s.op({action:'column_title',column_id:layout.columns[1].id,text:'+第一級'})
  await s.op({action:'shade_header',column_id:layout.columns[1].id,shade:3})
  await s.op({action:'shade_row',axis_id:layout.rows[3].id,shade:1})
  await s.op({action:'shade_column',axis_id:layout.columns[0].id,shade:2})
  await s.op({action:'shade_cells',start:point(layout,3,0),end:point(layout,4,1),shade:3})
  await s.reload();await s.save('=保存版');await s.idle();const saved=(await s.state()).latest
  await s.op({action:'column_title',column_id:layout.columns[1].id,text:'目前表頭'})
  await s.op({action:'move_empty',registration_id:s.rows[0].id,target:point(layout,7,3)})
  await s.reload();const current=await s.state()
  const toolbar=s.area.locator('.arrangement-tools'),history=toolbar.getByRole('button',{name:'歷史',exact:true}),search=toolbar.getByRole('button',{name:'搜尋姓名',exact:true})
  await expect(history).toHaveAttribute('aria-pressed','false');await expect(history).toHaveAttribute('aria-expanded','false')
  await expect(history).toHaveCSS('background-color','rgb(255, 255, 255)')
  await activate(info,history);await expect(history).toHaveAttribute('aria-pressed','true');await expect(history).toHaveCSS('background-color','rgb(40, 92, 62)')
  await activate(info,history);await expect(history).toHaveAttribute('aria-pressed','false')
  await expect(s.area.getByRole('button',{name:'重新讀取安排'})).toHaveCount(0)
  await expect(search).toHaveAttribute('title','搜尋姓名');await expect(search.locator('svg')).toHaveCount(1)
  const buttonBox=(await search.boundingBox())!,svgBox=(await search.locator('svg').boundingBox())!
  expect(Math.abs(buttonBox.x+buttonBox.width/2-svgBox.x-svgBox.width/2)).toBeLessThan(1)
  expect(Math.abs(buttonBox.y+buttonBox.height/2-svgBox.y-svgBox.height/2)).toBeLessThan(1)
  expect(await toolbar.locator('button').last().getAttribute('aria-label')).toBe('搜尋姓名')
  await activate(info,search);await s.area.getByLabel('搜尋姓名或辨識註記').fill('格位選手001');await activate(info,s.area.locator('.vegetarian-toggle'))
  const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/'))writes.push(r.url())})
  await downloadArrangement(page,info,s,'current',{rows:current.rows,layout:current.layout,title:s.comp.name,version:'目前安排'})
  expect(await s.state()).toEqual(current);expect(writes).toHaveLength(0)
  await page.screenshot({path:info.outputPath('export-toolbar-screen.png'),fullPage:true})
  await activate(info,history);await activate(info,s.area.locator('.version-item').filter({hasText:'=保存版'}));await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible()
  await downloadArrangement(page,info,s,'history',{rows:saved.rows,layout:saved.layout,title:s.comp.name,version:'歷史：=保存版'})
  expect(await s.state()).toEqual(current);expect(writes).toHaveLength(0)
  expect(await (await page.request.get(s.endpoint+'/versions/'+saved.id)).json()).toEqual(saved)
  await page.evaluate(()=>{window.print=()=>{}})
  for(const background of [true,false]){
    await s.area.getByRole('button',{name:'列印安排',exact:true}).click();await page.emulateMedia({media:'print'})
    await expect(page.locator('[data-print-registration]')).toHaveCount(3)
    if(info.project.name==='desktop')await page.pdf({path:info.outputPath(background?'grid-lines-default.pdf':'grid-lines-background-off.pdf'),preferCSSPageSize:true,printBackground:background})
    await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));await page.emulateMedia({media:'screen'})
  }
})

test('匯出精修：下載失敗可重試與未知操作禁止匯出',async({page},info)=>{
  const s=await setup(page,info,'edit-export-retry',3),initial=await s.state()
  await page.evaluate(()=>{
    const create=URL.createObjectURL.bind(URL)
    URL.createObjectURL=(blob)=>{
      if(blob instanceof Blob && blob.type==='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'){
        URL.createObjectURL=create
        throw new Error('Injected XLSX download failure')
      }
      return create(blob)
    }
  })
  await s.area.getByRole('button',{name:'匯出 Excel',exact:true}).click()
  await expect(s.area.getByRole('alert')).toContainText('Excel 匯出失敗')
  await expect(s.area.getByRole('button',{name:'匯出 Excel',exact:true})).toBeEnabled()
  await downloadArrangement(page,info,s,'retry',{rows:initial.rows,layout:initial.layout,title:s.comp.name,version:'目前安排'})
  await page.route('**/arrangement/operations',r=>r.abort('internetdisconnected'))
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 1',exact:true}))
  await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試'})).toBeVisible()
  await expect(s.area.getByRole('button',{name:'匯出 Excel',exact:true})).toBeDisabled()
  await page.unroute('**/arrangement/operations');await s.area.getByRole('button',{name:'確認操作結果／原樣重試'}).click();await s.idle()
  await expect(s.area.getByRole('button',{name:'匯出 Excel',exact:true})).toBeEnabled()
})

test('匯出精修：舊版無格位不補現況',async({page},info)=>{
  const s=await setup(page,info,'edit-export-legacy',3),initial=await s.state()
  await s.op({action:'column_title',column_id:initial.layout.columns[0].id,text:'新格式'});await s.reload();await s.save('舊資料合成fixture');await s.idle()
  const legacy=structuredClone((await s.state()).latest);legacy.layout=null;legacy.schema_version=1;legacy.rows.forEach((r:any)=>{r.diet=null;r.member_level=null})
  await page.route('**/arrangement/versions/'+legacy.id,r=>r.fulfill({json:legacy}))
  await s.area.getByRole('button',{name:'歷史',exact:true}).click();await s.area.locator('.version-item').filter({hasText:'舊資料合成fixture'}).click()
  await expect(s.area.getByText('舊版未記錄儲存格位置；以下僅按級數與順位檢視，不代表當時分組。未保存的餐食與長期級數顯示未知。')).toBeVisible()
  const before=await s.state();const writes:string[]=[];page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/'))writes.push(r.url())})
  await downloadArrangement(page,info,s,'legacy',{rows:legacy.rows,layout:null,title:s.comp.name,version:'歷史：舊資料合成fixture'})
  expect(await s.state()).toEqual(before);expect(writes).toHaveLength(0)
})


test('狀態精修：上色回執格式不完整仍保留原請求可恢復',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery-receipt',3),sent:any[]=[]
  for(const [index,kind] of ['object','null','empty','html','wrong-key','wrong-operation'].entries()){
    const before=await s.state();let first=true
    await page.route('**/arrangement/operations',async route=>{
      sent.push(route.request().postDataJSON());const response=await route.fetch()
      if(!first){await route.fulfill({response});return}first=false
      if(kind==='object')await route.fulfill({status:200,json:{message:'upstream response replaced'}})
      else if(kind==='null')await route.fulfill({status:200,contentType:'application/json',body:'null'})
      else if(kind==='empty')await route.fulfill({status:204,body:''})
      else if(kind==='html')await route.fulfill({status:200,contentType:'text/html',body:'<html>Gateway page</html>'})
      else{const receipt=await response.json();if(kind==='wrong-key')receipt.request_id=crypto.randomUUID();else receipt.operation.shade=3;await route.fulfill({json:receipt})}
    })
    await activate(info,s.area.getByLabel(`選取第 ${index+1} 欄表頭`,{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
    await expect.poll(async()=>(await s.state()).layout_revision).toBe(before.layout_revision+1)
    const retry=s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})
    await expect(retry).toBeVisible();await expect(s.area.getByRole('status')).toContainText('尚未確認')
    if(index===0)await page.screenshot({path:info.outputPath('unknown-recovery-screen.png'),fullPage:true})
    await activate(info,retry);await s.idle()
    expect(sent.at(-1)).toEqual(sent.at(-2));expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
    await expect(s.area.locator('[data-grid-header]').nth(index)).toHaveAttribute('data-header-shade','2');await page.unroute('**/arrangement/operations')
  }
})

test('狀態精修：另一分頁登入後舊CSRF可重新核對',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery-session',3),before=await s.state(),posts:number[]=[]
  page.on('response',r=>{if(r.url().endsWith('/arrangement/operations'))posts.push(r.status())})
  // Same cookie jar, new real session/CSRF; the already-open page retains its old token.
  expect((await page.request.post('/api/auth/login',{data:{username:`e2e-edit-${info.project.name}`,password:process.env.FUCHENG_E2E_ADMIN_PASSWORD}})).status()).toBe(200)
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}))
  await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  expect((await s.state()).layout_revision).toBe(before.layout_revision)
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}));await s.idle()
  expect(posts).toEqual([403,200]);expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
})

test('狀態精修：未知寫入遇到持續401保留原請求',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery-unknown-auth',3),before=await s.state(),sent:any[]=[]
  let first=true,expired=false
  await page.route('**/arrangement/operations',async route=>{
    sent.push(route.request().postDataJSON())
    if(first){first=false;await route.fetch();await route.abort('connectionclosed')}
    else if(expired)await route.fulfill({status:401,json:{detail:'登入已逾時，請重新登入'}})
    else await route.continue()
  })
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
  const retry=s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})
  await expect(retry).toBeVisible();expired=true
  await page.route('**/api/auth/me',r=>r.fulfill({status:401,json:{detail:'登入已逾時，請重新登入'}}))
  for(let i=0;i<2;i++){
    const response=page.waitForResponse(r=>r.url().endsWith('/api/auth/me')&&r.status()===401)
    await activate(info,retry);await response;await expect(retry).toBeEnabled()
    await expect(s.area.getByRole('alert').first()).toContainText('登入')
    await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toHaveCount(0)
  }
  expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
  await page.unroute('**/api/auth/me')
  const denied=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations')&&r.status()===401)
  await activate(info,retry);await denied;await expect(retry).toBeEnabled()
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toHaveCount(0)
  expired=false
  await page.route('**/api/auth/me',r=>r.fulfill({json:{username:'another-admin',csrf_token:'fixture-only-token'}}))
  const count=sent.length;await activate(info,retry);await expect(s.area.getByRole('alert').first()).toContainText('原帳號');expect(sent).toHaveLength(count)
  await page.unroute('**/api/auth/me');await activate(info,retry);await s.idle()
  expect(sent.every(x=>JSON.stringify(x)===JSON.stringify(sent[0]))).toBe(true)
  expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
})


test('狀態精修：合法回執後異常GET只讀回且401不丟回執',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery-readback',3),before=await s.state(),posts:any[]=[]
  page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))posts.push(r.postDataJSON())})
  await page.route('**/arrangement',r=>r.request().url().endsWith(s.endpoint)?r.fulfill({status:200,json:{message:'unexpected JSON'}}):r.continue())
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
  const retry=s.area.getByRole('button',{name:'讀回目前安排',exact:true})
  await expect(retry).toBeVisible();await expect(s.area.getByRole('status')).toContainText('回執')
  await page.unroute('**/arrangement');await page.route('**/api/auth/me',r=>r.fulfill({status:401,json:{detail:'登入已失效'}}))
  await activate(info,retry);await expect(s.area.getByRole('alert').first()).toContainText('另一分頁');await expect(retry).toBeVisible()
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  await page.unroute('**/api/auth/me');await activate(info,retry);await s.idle()
  expect(posts).toHaveLength(1);expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
  await page.screenshot({path:info.outputPath('readback-recovered-screen.png'),fullPage:true})
})

test('狀態精修：表格同高動態尺寸歷史重開與頁首對齊',async({page},info)=>{
  test.setTimeout(90000)
  const s=await setup(page,info,'edit-recovery-layout',30),initial=await s.state()
  for(let i=1;i<=12;i++){
    await s.op({action:'column_title',column_id:initial.layout.columns[0].id,text:`第${i}次表頭`})
    const state=await s.state()
    expect((await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:state.state_token,base_version_id:state.latest.id,label:`尺寸版本 ${i}`,editor_label:'合成管理員',note:''}})).status()).toBe(200)
  }
  for(let i=0;i<30;i++)await s.op({action:'move_empty',registration_id:s.rows[i].id,target:point(initial.layout,4+Math.floor(i/10),i%10)})
  await s.reload()
  const toggle=s.area.getByRole('button',{name:'歷史',exact:true}),list=s.area.locator('.arrangement-version-list'),table=s.area.locator('.arrangement-table-scroll'),diff=s.area.locator('.arrangement-diff'),history=s.area.locator('.arrangement-history')
  await activate(info,toggle)
  const bottom=async()=>await expect.poll(()=>list.evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop)).toBeLessThan(2)
  const aligned=async()=>{
    await expect.poll(async()=>{
      const t=(await table.boundingBox())!,d=(await diff.boundingBox())!,h=(await history.boundingBox())!
      return Math.max(Math.abs(d.y-t.y),Math.abs(h.y-t.y),Math.abs(d.height-t.height),Math.abs(h.height-t.height))
    }).toBeLessThan(2)
  }
  await page.setViewportSize({width:1920,height:900});await aligned();await bottom()
  const originalHeight=(await table.boundingBox())!.height
  await activate(info,s.area.getByRole('button',{name:'在表格下方插列',exact:true}));await s.idle();await aligned()
  expect((await table.boundingBox())!.height).toBeGreaterThan(originalHeight+40)
  const last=(await s.state()).layout.rows.length
  await activate(info,s.area.getByLabel(`第 ${last} 排更多操作`,{exact:true}));await activate(info,page.getByRole('group',{name:'這個範圍的操作'}).getByRole('button',{name:'刪除這一整排'}));await s.idle();await aligned()
  expect(Math.abs((await table.boundingBox())!.height-originalHeight)).toBeLessThan(2)
  const diffScroll=diff.locator('.arrangement-diff-scroll'),savedScroll=await list.evaluate(e=>e.scrollTop),headingY=(await diff.getByRole('heading').boundingBox())!.y
  await diffScroll.evaluate(e=>e.scrollTop=100);expect(await diffScroll.evaluate(e=>e.scrollTop)).toBeGreaterThan(0)
  expect(await list.evaluate(e=>e.scrollTop)).toBe(savedScroll);expect((await diff.getByRole('heading').boundingBox())!.y).toBe(headingY)
  await list.evaluate(e=>e.scrollTop=0);await activate(info,list.locator('.version-item').first());await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible();await aligned()
  await activate(info,toggle);await activate(info,toggle);await bottom();await expect(list.locator('.version-item').first()).toHaveClass(/selected/)
  await list.evaluate(e=>e.scrollTop=0);const top=await list.evaluate(e=>e.scrollTop);await activate(info,s.area.locator('.vegetarian-toggle'));expect(await list.evaluate(e=>e.scrollTop)).toBe(top)
  await activate(info,s.area.getByRole('button',{name:'回目前安排',exact:true}));await s.idle();await aligned()
  // A tall wrapped text row is measured from the live table, not a fixed viewport height.
  await textEdit(page,info,s,point(initial.layout,3,0),'多行格位文字'.repeat(45));await aligned()
  expect((await table.boundingBox())!.height).toBeGreaterThan(originalHeight)
  for(const width of [2400,1920,1440,390]){
    await page.setViewportSize({width,height:900})
    const main=(await page.locator('.arrangement-main').boundingBox())!,brand=(await page.locator('.site-brand').boundingBox())!,admin=(await page.locator('.admin-header > div').first().boundingBox())!
    expect(Math.abs(brand.x-main.x)).toBeLessThan(2);expect(Math.abs(admin.x-main.x)).toBeLessThan(2)
    if(width>=1700)await aligned()
    else{expect((await diff.boundingBox())!.y).toBeGreaterThan((await table.boundingBox())!.y+(await table.boundingBox())!.height)}
    if(width===390)expect((await history.boundingBox())!.y).toBeGreaterThan((await diff.boundingBox())!.y+(await diff.boundingBox())!.height)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1)
    if(width!==2400)await page.screenshot({path:info.outputPath(`aligned-${width}-screen.png`),fullPage:true})
  }
  // Same view switches back to 1240px container when leaving the arrangement mode.
  await page.setViewportSize({width:1920,height:900});await page.getByRole('button',{name:'報名與設定',exact:true}).click()
  expect((await page.locator('.site-brand').boundingBox())!.x).toBeGreaterThan(300)
  await page.getByRole('button',{name:'排級數',exact:true}).click();await s.choose(true);await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await aligned()
  await s.choose();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));await aligned();await bottom()
})

test('狀態精修：非同步首載開歷史後定位最新',async({page},info)=>{
  const s=await setup(page,info,'recovery-history-async',3),state=await s.state()
  for(let i=0;i<10;i++){
    await s.op({action:'column_title',column_id:state.layout.columns[0].id,text:`异步 ${i}`});const next=await s.state()
    await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:next.state_token,base_version_id:next.latest.id,label:`保存 ${i}`,editor_label:'合成管理員',note:''}})
  }
  let release!:()=>void;const held=new Promise<void>(r=>release=r)
  await page.route('**/arrangement',async r=>{if(r.request().url().endsWith(s.endpoint)){await held;await r.continue()}else await r.continue()})
  await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(s.comp.id)
  await s.area.getByRole('button',{name:'歷史',exact:true}).click();release()
  const list=s.area.locator('.arrangement-version-list');await expect(list.locator('.version-item')).toHaveCount(11)
  await expect.poll(()=>list.evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop)).toBeLessThan(2)
})


test('狀態精修：未知未送達後真實409可重新核對',async({page},info)=>{
  const s=await setup(page,info,'edit-recovery-conflict',3),before=await s.state(),sent:any[]=[]
  let first=true
  await page.route('**/arrangement/operations',async route=>{
    sent.push(route.request().postDataJSON());if(first){first=false;await route.abort('internetdisconnected')}else await route.continue()
  })
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))
  const retry=s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true});await expect(retry).toBeVisible()
  expect((await s.state()).layout_revision).toBe(before.layout_revision)
  await s.op({action:'column_title',column_id:before.layout.columns[1].id,text:'另一頁已變更'})
  const conflict=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations')&&r.status()===409)
  await activate(info,retry);await conflict
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  expect(sent[1]).toEqual(sent[0]);await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
  await expect(s.area.locator('[data-grid-header]').first()).toHaveAttribute('data-header-shade','0')
  await expect(s.area.getByLabel('選取第 2 欄表頭',{exact:true})).toHaveText('另一頁已變更')
})


test('色票故障：八十人正常連續點色生命週期',async({page},info)=>{
  test.setTimeout(90000)
  const errors:string[]=[],events:any[]=[],steps:any[]=[]
  page.on('pageerror',e=>errors.push(e.stack??e.message))
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text())})
  page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))events.push({phase:'POST',action:r.postDataJSON().operation,request_id:r.postDataJSON().request_id})})
  page.on('response',async r=>{
    if(!/\/arrangement(?:\/operations)?$/.test(r.url()))return
    const body=await r.json().catch(()=>null)
    events.push({phase:r.request().method()+' response',status:r.status(),revision:body?.revision??body?.layout_revision,receipt_id:body?.request_id,rows:body?.rows?.length,action:body?.operation?.action})
  })
  const s=await setup(page,info,'edit-shade-normal',80),initial=await s.state()
  await s.op({action:'shade_row',axis_id:initial.layout.rows[2].id,shade:1})
  await s.op({action:'shade_cells',start:point(initial.layout,2,1),end:point(initial.layout,2,1),shade:3})
  for(let i=0;i<4;i++){
    await s.op({action:'column_title',column_id:initial.layout.columns[0].id,text:`已有歷史 ${i}`});const next=await s.state()
    await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:next.state_token,base_version_id:next.latest.id,label:`既存版本 ${i}`,editor_label:'合成管理員',note:''}})
  }
  await s.reload();await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}))
  const palette=cellMenu(page).locator('.shade-palette'),choose=s.area.getByLabel('選取第 1 欄表頭',{exact:true})
  errors.length=0 // Observe the authenticated shade workflow, excluding the initial anonymous auth probe.
  steps.push(await page.evaluate(()=>({secure:window.isSecureContext,randomUUID:typeof crypto.randomUUID,userAgent:navigator.userAgent})))
  try{
    for(const target of ['header','body']){
      if(target==='header')await activate(info,choose)
      else{await page.keyboard.press('Escape');await expect(cellMenu(page)).toHaveCount(0);await activate(info,s.cell(21).locator('.cell-name'))}
      for(const shade of [1,2,3,0,2,1]){
      await openSelectedCellMenu(page,info,s)
      const before=await s.state(),button=palette.getByRole('button',{name:shade?`淺灰 ${shade}`:'白色',exact:true})
      await expect(button).toBeEnabled();await activate(info,button);await s.idle()
      await expect(s.area.getByRole('status')).toHaveText('已自動儲存')
      await expect(s.area.locator('.grid-selected')).toHaveCount(1)
      const after=await s.state()
      expect(after.layout_revision).toBe(before.layout_revision+1)
      if(target==='header')expect(after.layout.columns[0].header_shade).toBe(shade)
      else expect(after.layout.cell_shades.find((c:any)=>c.row_id===initial.layout.rows[2].id&&c.column_id===initial.layout.columns[1].id)?.shade).toBe(shade)
      steps.push({target,shade,revision:after.layout_revision,selectionCleared:false,paletteDisabled:await palette.locator('button').evaluateAll(els=>els.every(e=>(e as HTMLButtonElement).disabled)),printEnabled:await s.area.getByRole('button',{name:'列印安排',exact:true}).isEnabled(),exportEnabled:await s.area.getByRole('button',{name:'匯出 Excel',exact:true}).isEnabled()})
      expect(errors).toEqual([])
    }}
    await page.keyboard.press('Escape');await expect(cellMenu(page)).toHaveCount(0);await activate(info,choose);await openSelectedCellMenu(page,info,s);await expect(palette.getByRole('button',{name:'淺灰 2',exact:true})).toBeEnabled()
    await page.screenshot({path:info.outputPath('normal-shade-toolbar-screen.png'),fullPage:true})
  }finally{await writeFile(info.outputPath('normal-shade-observations.json'),JSON.stringify({errors,events,steps},null,2))}
})


test('色票故障：同色白色與合併範圍不重送',async({page},info)=>{
  const s=await setup(page,info,'edit-shade-same',80),initial=await s.state()
  await s.op({action:'insert_row',before_id:null});const extended=(await s.state()).layout
  const a=point(extended,extended.rows.length-1,0),b=point(extended,extended.rows.length-1,1),palette=cellMenu(page).locator('.shade-palette')
  await s.op({action:'shade_header',column_id:initial.layout.columns[0].id,shade:2})
  await s.op({action:'merge',start:a,end:b});await s.reload()
  await s.op({action:'shade_cells',start:point(initial.layout,0,0),end:point(initial.layout,0,0),shade:0})
  await s.op({action:'shade_cells',start:a,end:b,shade:0});await s.reload()
  // Genuine backend no-op responses after explicit white is already persisted.
  const noops=[{action:'shade_header',column_id:initial.layout.columns[0].id,shade:2},{action:'shade_cells',start:point(initial.layout,0,0),end:point(initial.layout,0,0),shade:0},{action:'shade_cells',start:a,end:b,shade:0}]
  const backend:any[]=[]
  for(const operation of noops){const current=await s.state(),r=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,operation}});expect(r.status()).toBe(422);const body=await r.json();expect(body).toEqual({detail:'安排沒有變更'});expect(await s.state()).toEqual(current);backend.push({operation,status:r.status(),body})}
  await writeFile(info.outputPath('genuine-noop-shapes.json'),JSON.stringify(backend,null,2))
  const writes:any[]=[];page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}))
  const before=await s.state()
  await activate(info,palette.getByRole('button',{name:'淺灰 2',exact:true}));await s.idle()
  await page.keyboard.press('Escape');await expect(cellMenu(page)).toHaveCount(0)
  await activate(info,s.slot(a).locator('.grid-empty'))
  await activate(info,palette.getByRole('button',{name:'白色',exact:true}));await s.idle()
  expect(writes).toHaveLength(0);expect((await s.state()).layout_revision).toBe(before.layout_revision)
  for(const shade of [1,2,3,0]){
    const response=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations'))
    await activate(info,palette.getByRole('button',{name:shade?`淺灰 ${shade}`:'白色',exact:true}));expect((await response).status()).toBe(200);await s.idle()
    const count=writes.length
    await activate(info,palette.getByRole('button',{name:shade?`淺灰 ${shade}`:'白色',exact:true}));await s.idle();expect(writes).toHaveLength(count)
    await expect(s.slot(a)).toHaveClass(/grid-selected/)
  }
  expect((await s.state()).rows).toEqual(initial.rows)
  await openSelectedCellMenu(page,info,s)
  await expect(palette.locator('button').first()).toHaveAttribute('aria-label','白色')
  await expect(palette.locator('button').first()).toHaveCSS('background-color','rgb(255, 255, 255)')
  await expect(palette.locator('svg')).toHaveCount(0)
  await expect(cellMenu(page).getByRole('group',{name:'表格底色'})).toHaveCSS('border-top-width','1px')
  await page.screenshot({path:info.outputPath('shade-palette-screen.png'),fullPage:true})
})

test('色票故障：真實未變更回應自動讀回且不假造保存',async({page},info)=>{
  const s=await setup(page,info,'edit-shade-noop-read',3),before=await s.state()
  await openPlayer(info,s.cell(0).locator('.cell-name'))
  const response=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations'))
  await activate(info,page.getByRole('dialog').getByRole('button',{name:'移動',exact:true}))
  const result=await response;expect(result.status()).toBe(422);expect(await result.json()).toEqual({detail:'安排沒有變更'})
  await s.idle();await expect(s.area.getByRole('status')).toHaveText('安排沒有變更；已重新讀取目前安排。')
  expect(await s.state()).toEqual(before)
  await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await openSelectedCellMenu(page,info,s)
  await expect(cellMenu(page).getByRole('button',{name:'復原上一個動作',exact:true})).toBeDisabled()
  await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 1',exact:true}));await s.idle()
  expect((await s.state()).layout_revision).toBe(before.layout_revision+1)
})


test('色票邊界：未變更讀回失敗仍鎖定而不重送',async({page},info)=>{
  const s=await setup(page,info,'edit-noop-load-failure',3),before=await s.state(),writes:any[]=[]
  page.on('request',r=>{if(r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  await page.route('**/arrangement',route=>route.abort('failed'))
  await openPlayer(info,s.cell(0).locator('.cell-name'));await activate(info,page.getByRole('dialog').getByRole('button',{name:'移動',exact:true}))
  await expect(s.area.getByRole('status')).toHaveText('讀取失敗，這場暫停修改。')
  await expect(s.area.locator('.cell-grip').first()).toBeDisabled();await expect(s.area.getByRole('button',{name:'重新讀取',exact:true})).toBeVisible()
  await expect(s.area.getByRole('status')).not.toContainText('已自動儲存')
  await page.unroute('**/arrangement');await activate(info,s.area.getByRole('button',{name:'重新讀取',exact:true}));await s.idle()
  expect(writes).toHaveLength(1);expect(await s.state()).toEqual(before)
})

test('色票邊界：一般422與未知請求不可自動解除',async({page},info)=>{
  const s=await setup(page,info,'edit-noop-reject',3),sent:any[]=[]
  let phase='invalid'
  await page.route('**/arrangement/operations',async route=>{
    sent.push(route.request().postDataJSON())
    if(phase==='abort'){phase='noop';await route.abort('failed')}
    else await route.fulfill({status:422,json:{detail:phase==='invalid'?'合成無效安排':'安排沒有變更'}})
  })
  const color=async()=>{await activate(info,s.area.getByLabel('選取第 1 欄表頭',{exact:true}));await activate(info,cellMenu(page).getByRole('button',{name:'淺灰 2',exact:true}))}
  await color();await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible();await expect(s.area.getByRole('alert')).toContainText('合成無效安排');await expect(s.area.locator('.cell-grip').first()).toBeDisabled()
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  phase='abort';await color();await expect(s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})).toBeVisible()
  await activate(info,s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true}))
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible();await expect(s.area.locator('.cell-grip').first()).toBeDisabled()
  expect(sent[2]).toEqual(sent[1]);expect(sent).toHaveLength(3)
})

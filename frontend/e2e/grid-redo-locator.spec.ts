import { expect, test, type Page, type TestInfo } from '@playwright/test'

type Point={row_id:string;column_id:string}
const point=(layout:any,row:number,column:number):Point=>({row_id:layout.rows[row].id,column_id:layout.columns[column].id})
const position=(layout:any,id:string):Point=>{const cell=layout.cells.find((value:any)=>value.kind==='registration'&&value.registration_id===id);return {row_id:cell.row_id,column_id:cell.column_id}}
const activate=(info:TestInfo,locator:any)=>info.project.name==='mobile'?locator.tap():locator.click()
const menu=(page:Page)=>page.getByRole('dialog',{name:'儲存格操作',exact:true})

async function setup(page:Page,info:TestInfo,suffix:string,count=4){
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號',{exact:true}).fill(`e2e-grid-${info.project.name}`)
  await page.getByLabel('密碼',{exact:true}).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button',{name:'登入',exact:true}).click()
  await expect(page.getByRole('heading',{name:'比賽',exact:true})).toBeVisible()
  const me=await (await page.request.get('/api/auth/me')).json(),headers={'X-CSRF-Token':me.csrf_token}
  const name=`Redo格位-${info.project.name}-${suffix}`
  const payload={name,competition_date:'2099-09-20',registration_deadline:'2099-09-19T00:00:00+08:00',capacity:count+2,status:'open',notes:'合成 undo redo 及變動定位'}
  const comp=await (await page.request.post('/api/admin/competitions',{headers,data:payload})).json()
  const registrations:any[]=[]
  for(let i=0;i<count;i++){
    const member=await (await page.request.post('/api/admin/members',{headers,data:{name:`定位選手${String(i).padStart(2,'0')}`,distinguishing_note:`合成${suffix}`,level:i%10+1,diet:'omnivore',is_active:true}})).json()
    const response=await page.request.post(`/api/admin/competitions/${comp.id}/registrations`,{headers,data:{member_id:member.id,diet:'omnivore',request_id:crypto.randomUUID()}})
    expect(response.status()).toBe(201);registrations.push(await response.json())
  }
  await page.reload()
  const area=page.getByRole('region',{name:'當次比賽級數安排'})
  const choose=async()=>{await page.getByLabel('選擇比賽',{exact:true}).selectOption(comp.id);await expect(area.getByRole('heading',{name:comp.name,exact:true})).toBeVisible()}
  await choose()
  const endpoint=`/api/admin/competitions/${comp.id}/arrangement`
  const state=async()=>await (await page.request.get(endpoint)).json()
  await expect.poll(async()=>!!(await state()).layout).toBe(true)
  const slot=(address:Point)=>area.locator(`[data-grid-cell="${address.row_id}/${address.column_id}"]`)
  const cell=(id:string)=>area.locator(`[data-registration-id="${id}"]`)
  const op=async(operation:any)=>{const current=await state(),response=await page.request.post(endpoint+'/operations',{headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,operation}});expect(response.status()).toBe(200,response.statusText());return response.json()}
  const idle=async()=>{await expect(area.locator('.cell-grip').first()).toBeEnabled();await expect(area.locator('.arrangement-recovery')).toHaveCount(0)}
  const reload=async()=>{await page.reload();await choose();await expect.poll(async()=>!!(await state()).layout).toBe(true)}
  const save=async(label:string)=>{await area.getByRole('button',{name:'保存完整安排',exact:true}).click();const dialog=page.getByRole('dialog',{name:'保存完整安排'});await dialog.getByLabel('版本名稱').fill(label);await dialog.getByRole('button',{name:'保存',exact:true}).click();await expect(area.locator('.arrangement-status')).toContainText(`已保存「${label}」`)}
  const addRegistration=async(memberName:string,level:number)=>{const member=await (await page.request.post('/api/admin/members',{headers,data:{name:memberName,distinguishing_note:'新增合成',level,diet:'omnivore',is_active:true}})).json();const response=await page.request.post(`/api/admin/competitions/${comp.id}/registrations`,{headers,data:{member_id:member.id,diet:'omnivore',request_id:crypto.randomUUID()}});expect(response.status()).toBe(201);return response.json()}
  return {page,info,headers,comp,registrations,area,endpoint,state,slot,cell,op,idle,reload,save,addRegistration,choose}
}

async function openCellMenu(page:Page,info:TestInfo,s:any,address:Point){
  if(await menu(page).isVisible())await page.keyboard.press('Escape')
  const target=s.slot(address);await target.scrollIntoViewIfNeeded()
  if(info.project.name==='desktop')await target.click({button:'right'})
  else{await target.locator('.grid-empty').tap();await activate(info,s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}))}
  await expect(menu(page)).toBeVisible()
}

async function ensureHistoryOpen(info:TestInfo,s:any){
  const toggle=s.area.getByRole('button',{name:'歷史',exact:true})
  if(await toggle.getAttribute('aria-expanded')!=='true')await activate(info,toggle)
}

async function saveBaseline(s:any,label:string){
  const current=await s.state()
  const player=current.layout.cells.find((cell:any)=>cell.kind==='registration')
  expect(player).toBeTruthy()
  const occupied=new Set(current.layout.cells.map((cell:any)=>`${cell.row_id}/${cell.column_id}`))
  const emptyRow=current.layout.rows.find((row:any)=>row.role==='body'&&!occupied.has(`${row.id}/${player.column_id}`))
  expect(emptyRow).toBeTruthy()
  await s.op({action:'move_empty',registration_id:player.registration_id,target:{row_id:emptyRow.id,column_id:player.column_id}})
  await s.reload()
  await s.save(label)
  await s.reload()
  return s.state()
}

async function shadeCell(page:Page,info:TestInfo,s:any,address:Point,shade:number){
  await openCellMenu(page,info,s,address)
  await activate(info,menu(page).getByRole('group',{name:'表格底色'}).getByRole('button',{name:shade?`淺灰 ${shade}`:'白色',exact:true}))
  await s.idle()
}

async function operateFromMenu(page:Page,info:TestInfo,s:any,address:Point,label:string){
  await openCellMenu(page,info,s,address)
  return menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:label,exact:true})
}

const storedShade=(layout:any,address:Point)=>layout.cell_shades?.find((cell:any)=>cell.row_id===address.row_id&&cell.column_id===address.column_id)?.shade??0
const locateCard=(s:any,name:string)=>s.area.locator('.arrangement-change-card').filter({hasText:name}).first()
const visiblePoints=(layout:any,points:(Point|null)[])=>points.filter((p):p is Point=>!!p&&layout.rows.some((r:any)=>r.id===p.row_id)&&layout.columns.some((c:any)=>c.id===p.column_id)).map(p=>`${p.row_id}/${p.column_id}`).sort()

test('Undo Redo 多步快捷鍵、分支清除、保存鎖定與輸入例外',async({page},info)=>{
  const s=await setup(page,info,'lifecycle',2),initial=await s.state()
  const free=initial.layout.rows.filter((row:any)=>row.role==='body').flatMap((row:any)=>initial.layout.columns.map((column:any)=>({row_id:row.id,column_id:column.id}))).filter((p:Point)=>!initial.layout.cells.some((cell:any)=>cell.row_id===p.row_id&&cell.column_id===p.column_id))
  const [a,b,c]=free
  const global=(label:string)=>menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:label,exact:true})
  await openCellMenu(page,info,s,a)
  await expect(global('復原上一個動作')).toBeDisabled();await expect(global('重做')).toBeDisabled()
  await activate(info,menu(page).getByRole('button',{name:'關閉',exact:true}).or(menu(page).getByRole('button',{name:'取消選取',exact:true})))
  await shadeCell(page,info,s,a,1);await shadeCell(page,info,s,b,2)
  await expect(global('復原上一個動作')).toBeEnabled();await expect(global('重做')).toBeDisabled()
  const writes:any[]=[];page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/arrangement/operations'))writes.push(request.postDataJSON())})
  await page.keyboard.press('Control+Z');await s.idle();expect(storedShade((await s.state()).layout,b)).toBe(0)
  await page.keyboard.press('Control+Z');await s.idle();expect(storedShade((await s.state()).layout,a)).toBe(0)
  await expect(global('復原上一個動作')).toBeDisabled();await expect(global('重做')).toBeEnabled()
  await page.evaluate(()=>document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'z',metaKey:true,shiftKey:true,bubbles:true})))
  await s.idle();expect(storedShade((await s.state()).layout,a)).toBe(1);await expect(global('重做')).toBeEnabled()
  await page.keyboard.press('Control+Y');await s.idle();expect(storedShade((await s.state()).layout,b)).toBe(2)
  await expect(global('重做')).toBeDisabled()
  await shadeCell(page,info,s,c,3);await expect(global('重做')).toBeDisabled()
  await activate(info,global('復原上一個動作'));await s.idle();await openCellMenu(page,info,s,c);await expect(global('重做')).toBeEnabled()
  await shadeCell(page,info,s,a,0);await expect(global('重做')).toBeDisabled()
  await page.keyboard.press('Escape')
  const tableHeader=s.area.locator('.grid-level-head th').first();await tableHeader.hover();await expect(tableHeader).toHaveCSS('cursor','cell');await expect(tableHeader.locator('.grid-column-title')).toHaveCSS('cursor','cell')
  await s.save('Undo Redo 保存檢查');await s.idle();await openCellMenu(page,info,s,a);await expect(global('復原上一個動作')).toBeDisabled();await expect(global('重做')).toBeDisabled();await page.keyboard.press('Escape')
  await shadeCell(page,info,s,c,1);const beforeText=(await s.state()).layout_revision,writeCount=writes.length
  await openCellMenu(page,info,s,free[3]);await activate(info,menu(page).getByRole('button',{name:'編輯文字',exact:true}))
  const editor=page.getByRole('dialog',{name:'儲存格文字'}).getByLabel('儲存格文字內容');await editor.fill('合成輸入草稿')
  await editor.evaluate(element=>element.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})))
  await page.keyboard.press('Control+Z');await page.keyboard.press('Control+Shift+Z')
  await editor.evaluate(element=>element.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})))
  expect(writes).toHaveLength(writeCount);expect((await s.state()).layout_revision).toBe(beforeText)
  await page.getByRole('dialog',{name:'儲存格文字'}).getByRole('button',{name:'取消',exact:true}).click()
  await openCellMenu(page,info,s,a);await expect(global('復原上一個動作')).toBeEnabled()
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}));const version=s.area.locator('.version-item').last();await activate(info,version)
  await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible();await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toHaveCount(0)
  await page.keyboard.press('Control+Z');await page.keyboard.press('Control+Shift+Z');expect(writes).toHaveLength(writeCount)
  expect((await s.state()).layout_revision).toBe(beforeText)
  await page.screenshot({path:info.outputPath('redo-history-readonly.png'),fullPage:true})
})

test('Redo 未知重試固定 payload、receipt 後只讀回且外來更新斷鏈',async({page},info)=>{
  const s=await setup(page,info,'redo-recovery',1),initial=await s.state()
  const address=initial.layout.cells.find((cell:any)=>cell.kind==='registration')
    ? initial.layout.rows.filter((row:any)=>row.role==='body').flatMap((row:any)=>initial.layout.columns.map((column:any)=>({row_id:row.id,column_id:column.id}))).find((p:Point)=>!initial.layout.cells.some((cell:any)=>cell.row_id===p.row_id&&cell.column_id===p.column_id))
    : point(initial.layout,5,0)
  await shadeCell(page,info,s,address,1);await activate(info,await operateFromMenu(page,info,s,address,'復原上一個動作'));await s.idle()
  await expect((await operateFromMenu(page,info,s,address,'重做'))).toBeEnabled()
  const redoRequests:any[]=[];let failFirst=true
  await page.route('**/arrangement/operations',async route=>{
    const payload=route.request().postDataJSON();if(payload.operation.action!=='redo'){await route.continue();return}
    redoRequests.push(payload);if(failFirst){failFirst=false;await route.abort('internetdisconnected')}else await route.continue()
  })
  const retry= s.area.getByRole('button',{name:'確認操作結果／原樣重試',exact:true})
  await activate(info,await operateFromMenu(page,info,s,address,'重做'));await expect(retry).toBeVisible();expect(redoRequests).toHaveLength(1)
  await expect(s.area.getByRole('button',{name:'開啟儲存格操作',exact:true})).toBeDisabled()
  expect(redoRequests).toHaveLength(1)
  let failRead=true
  await page.route(`**${s.endpoint}`,async route=>{if(route.request().method()==='GET'&&failRead){failRead=false;await route.abort('failed')}else await route.continue()})
  await activate(info,retry);await expect(s.area.getByRole('button',{name:'讀回目前安排',exact:true})).toBeVisible()
  expect(redoRequests).toHaveLength(2);expect(redoRequests[1]).toEqual(redoRequests[0])
  const afterRedo=await s.state();expect(storedShade(afterRedo.layout,address)).toBe(1)
  await activate(info,s.area.getByRole('button',{name:'讀回目前安排',exact:true}));await s.idle()
  expect(redoRequests).toHaveLength(2);expect(redoRequests[1]).toEqual(redoRequests[0])
  await page.unroute(`**${s.endpoint}`)
  await shadeCell(page,info,s,address,0);await activate(info,await operateFromMenu(page,info,s,address,'復原上一個動作'));await s.idle()
  await expect((await operateFromMenu(page,info,s,address,'重做'))).toBeEnabled()
  const beforeExternal=await s.state()
  await s.op({action:'shade_cells',start:address,end:address,shade:2})
  await activate(info,await operateFromMenu(page,info,s,address,'重做'))
  await expect(s.area.getByRole('button',{name:'重新讀取並核對',exact:true})).toBeVisible()
  await activate(info,s.area.getByRole('button',{name:'重新讀取並核對',exact:true}));await s.idle()
  await openCellMenu(page,info,s,address);await expect(menu(page).getByRole('group',{name:'整張表格'}).getByRole('button',{name:'重做',exact:true})).toBeDisabled()
  expect((await s.state()).layout_revision).toBe(beforeExternal.layout_revision+1)
  await page.screenshot({path:info.outputPath('redo-recovery-screen.png'),fullPage:true})
})

test('變動卡片以 stable 格位定位新增移出移位交換與歷史版本',async({page},info)=>{
  const s=await setup(page,info,'locate-cards',4),ids=s.registrations.map((row:any)=>row.id)
  const initial=await saveBaseline(s,'定位基準')
  const source0=position(initial.layout,ids[0]),source1=position(initial.layout,ids[1]),source2=position(initial.layout,ids[2]),source3=position(initial.layout,ids[3])
  await s.op({action:'move_empty',registration_id:ids[0],target:point(initial.layout,3,4)})
  await s.op({action:'move_empty',registration_id:ids[1],target:{row_id:initial.layout.rows[4].id,column_id:source1.column_id}})
  await s.op({action:'swap',registration_id:ids[2],target_registration_id:ids[3]})
  const added=await s.addRegistration('合成新增選手',8)
  const current=await s.state(),removed=current.rows.find((row:any)=>row.registration_id===ids[3])
  const cancelled=await page.request.post(`/api/admin/registrations/${ids[3]}/cancel`,{headers:s.headers,data:{version:removed.version,request_id:crypto.randomUUID()}});expect(cancelled.status()).toBe(200)
  await s.reload()
  const moved=await s.state(),writes:any[]=[];page.on('request',request=>{if(request.method()!=='GET'&&request.url().includes('/api/admin'))writes.push(request.url())})
  await activate(info,s.area.getByRole('button',{name:'歷史',exact:true}))
  const loc=async(name:string,expected:(Point|null)[])=>{
    const card=locateCard(s,name);await expect(card).toHaveCount(1);await card.scrollIntoViewIfNeeded();const diffScroll=s.area.locator('.arrangement-diff-scroll'),beforeScroll=await diffScroll.evaluate(element=>element.scrollTop),revision=(await s.state()).layout_revision
    await activate(info,card);await expect.poll(()=>s.area.locator('td.grid-located').count()).toBe(visiblePoints(moved.layout,expected).length)
    if(name==='定位選手00')await expect(card).toHaveCSS('background-color','rgb(255, 240, 194)')
    const actual=(await s.area.locator('td.grid-located').evaluateAll(elements=>elements.map(element=>element.getAttribute('data-grid-cell')).sort()))
    expect(actual).toEqual(visiblePoints(moved.layout,expected));expect(await diffScroll.evaluate(element=>element.scrollTop)).toBe(beforeScroll)
    expect((await s.state()).layout_revision).toBe(revision);expect(writes).toHaveLength(0)
    return card
  }
  const crossTarget=position(moved.layout,ids[0]),sameTarget=position(moved.layout,ids[1])
  await loc('定位選手00',[source0,crossTarget]);await loc('定位選手01',[source1,sameTarget])
  const swapTarget=position(moved.layout,ids[2]);await loc('定位選手02',[source2,swapTarget])
  const addedTarget=position(moved.layout,added.id);await loc('合成新增選手',[addedTarget])
  await loc('定位選手03',[source3])
  await page.keyboard.press('Enter') // The focused diff card remains keyboard operable.
  await expect(s.area.locator('td.grid-located')).toHaveCount(1)
  await s.save('定位歷史版本');await s.idle();writes.length=0
  await ensureHistoryOpen(info,s)
  const latest=s.area.locator('.version-item').filter({hasText:'定位歷史版本'});await activate(info,latest)
  await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible()
  const historicalLayout=(await s.state()).latest.layout
  await activate(info,locateCard(s,'定位選手00'));const historyTarget=position(historicalLayout,ids[0])
  await expect(s.area.locator('td.grid-located')).toHaveCount(2)
  expect((await s.area.locator('td.grid-located').evaluateAll(elements=>elements.map(element=>element.getAttribute('data-grid-cell')).sort()))).toEqual([`${source0.row_id}/${source0.column_id}`,`${historyTarget.row_id}/${historyTarget.column_id}`].sort());expect(writes).toHaveLength(0)
  await page.screenshot({path:info.outputPath('change-cards-history.png'),fullPage:true})
  const baselineId=initial.latest.id
  await page.route(`**${s.endpoint}/versions/${baselineId}`,async route=>{const response=await route.fetch(),body=await response.json();await route.fulfill({response,json:{...body,layout:null}})})
  await s.area.getByRole('button',{name:'回目前安排',exact:true}).click();await expect(s.area.locator('td.grid-located')).toHaveCount(0)
  await activate(info,s.area.locator('.version-item').filter({hasText:'定位歷史版本'}))
  await activate(info,locateCard(s,'定位選手00'))
  await expect(s.area.locator('td.grid-located')).toHaveCount(1);await expect(s.area.locator('.arrangement-change-location')).toContainText('無法定位來源')
  expect(position(historicalLayout,ids[0])).toEqual(historyTarget);expect(writes).toHaveLength(0)
  await s.area.getByRole('button',{name:'回目前安排',exact:true}).click();await expect(s.area.locator('td.grid-located')).toHaveCount(0)
  const currentLayout=(await s.state()).layout
  await s.slot(point(currentLayout,7,0)).locator('.grid-empty').click();await expect(s.area.locator('td.grid-located')).toHaveCount(0)
  await page.screenshot({path:info.outputPath('change-cards-current.png'),fullPage:true})
  await s.op({action:'insert_row',before_id:currentLayout.rows[7].id});await s.reload();await ensureHistoryOpen(info,s)
  await expect(s.area.getByRole('button',{name:'保存完整安排',exact:true})).toBeEnabled()
  await expect(s.area.getByText('文字、行列、底色或合併結構已變更',{exact:true})).toHaveCount(0)
  await expect(s.area.getByText('沒有可比較的安排變更',{exact:true})).toHaveCount(0)
})

test('刪除來源軸及缺少前版布局時只定位確定存在的格位',async({page},info)=>{
  const s=await setup(page,info,'locate-missing-axis',1),id=s.registrations[0].id,initial=await saveBaseline(s,'刪軸基準'),old=position(initial.layout,id),oldRow=old.row_id
  await s.op({action:'insert_row',before_id:oldRow});let layout=(await s.state()).layout
  const newRow=layout.rows.find((row:any)=>!initial.layout.rows.some((old:any)=>old.id===row.id)).id
  await s.op({action:'move_empty',registration_id:id,target:{row_id:newRow,column_id:old.column_id}})
  await s.op({action:'delete_row',axis_id:oldRow,confirmed_text:false})
  await s.op({action:'move_bottom',registration_id:id,level:2});await s.reload()
  const current=await s.state(),currentPoint=position(current.layout,id),card=locateCard(s,'定位選手00')
  await ensureHistoryOpen(info,s)
  await expect(card).toHaveCount(1);await activate(info,card);await expect(s.area.locator('td.grid-located')).toHaveCount(1)
  await expect(s.area.locator('.arrangement-change-location')).toContainText('來源格位已不在目前布局')
  expect(await s.area.locator('td.grid-located').getAttribute('data-grid-cell')).toBe(`${currentPoint.row_id}/${currentPoint.column_id}`)
  await s.save('刪除來源軸');await s.idle();await ensureHistoryOpen(info,s)
  await activate(info,s.area.locator('.version-item').filter({hasText:'刪除來源軸'}));await expect(s.area.getByText('歷史版本唯讀',{exact:true})).toBeVisible()
  const baselineId=initial.latest.id
  await page.route(`**${s.endpoint}/versions/${baselineId}`,async route=>{const response=await route.fetch(),body=await response.json();await route.fulfill({response,json:{...body,layout:null}})})
  await s.area.getByRole('button',{name:'回目前安排',exact:true}).click()
  await activate(info,s.area.locator('.version-item').filter({hasText:'刪除來源軸'}))
  await activate(info,locateCard(s,'定位選手00'))
  await expect(s.area.locator('td.grid-located')).toHaveCount(1);await expect(s.area.locator('.arrangement-change-location')).toContainText('前版未記錄格位')
  await page.screenshot({path:info.outputPath('change-cards-missing-layout-axis.png'),fullPage:true})
})

test('歷史與變動面板各自捲動、凍結標題與重新開啟定位最新',async({page},info)=>{
  const s=await setup(page,info,'panel-scroll',24),initial=await s.state(),column=initial.layout.columns[0].id
  for(let i=1;i<=12;i++){
    await s.op({action:'column_title',column_id:column,text:`捲動標題 ${i}`})
    const current=await s.state(),response=await page.request.post(s.endpoint+'/versions',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,base_version_id:current.latest.id,label:`捲動版本 ${i}`,editor_label:'合成測試',note:null}})
    expect(response.status()).toBe(200)
  }
  const layout=(await s.state()).layout,occupied=new Set(layout.cells.map((cell:any)=>`${cell.row_id}/${cell.column_id}`)),targets=new Set<string>()
  const players=layout.cells.filter((cell:any)=>cell.kind==='registration')
  for(const player of players){
    const free=layout.rows.find((row:any)=>row.role==='body'&&!occupied.has(`${row.id}/${player.column_id}`)&&!targets.has(`${row.id}/${player.column_id}`))
    expect(free).toBeTruthy();const address={row_id:free.id,column_id:player.column_id};targets.add(`${address.row_id}/${address.column_id}`)
    await s.op({action:'move_empty',registration_id:player.registration_id,target:address})
  }
  await s.reload()
  if(info.project.name==='desktop')await page.setViewportSize({width:1920,height:980})
  const toggle=s.area.getByRole('button',{name:'歷史',exact:true}),diff=s.area.getByRole('complementary',{name:'該版本變動'}),history=s.area.getByRole('complementary',{name:'版本紀錄'}),diffScroll=diff.locator('.arrangement-diff-scroll'),list=history.locator('.arrangement-version-list')
  await activate(info,toggle)
  const atBottom=async()=>await expect.poll(()=>list.evaluate(element=>element.scrollHeight-element.clientHeight-element.scrollTop)).toBeLessThan(2)
  await atBottom();await expect(list.locator('.version-item').last()).toContainText('捲動版本 12最新')
  for(const panel of [diff,history]){
    await expect(panel).toHaveCSS('border-top-width','1px');await expect(panel).toHaveCSS('border-bottom-width','1px');await expect(panel).toHaveCSS('border-left-width','1px');await expect(panel).toHaveCSS('border-right-width','1px')
  }
  const diffHeader=diff.locator('.arrangement-panel-heading'),historyHeader=history.locator('.arrangement-panel-heading'),baseline=diff.getByText(/相較/),currentButton=history.getByRole('button',{name:'目前安排',exact:true})
  const fixed=async()=>{await expect(diffHeader).toBeVisible();await expect(historyHeader).toBeVisible();await expect(baseline).toBeVisible();await expect(currentButton).toBeVisible()}
  await fixed();const headerBoxes=await Promise.all([diffHeader.boundingBox(),historyHeader.boundingBox(),baseline.boundingBox(),currentButton.boundingBox()])
  await diffScroll.evaluate(element=>element.scrollTop=120);expect(await diffScroll.evaluate(element=>element.scrollTop)).toBeGreaterThan(0)
  const listScroll=await list.evaluate(element=>element.scrollTop)
  const afterDiff=[await diffHeader.boundingBox(),await historyHeader.boundingBox(),await baseline.boundingBox(),await currentButton.boundingBox()]
  expect(afterDiff.map((box,index)=>Math.abs(box!.y-headerBoxes[index]!.y))).toEqual([0,0,0,0]);expect(await list.evaluate(element=>element.scrollTop)).toBe(listScroll)
  const leftScroll=await diffScroll.evaluate(element=>element.scrollTop);await list.evaluate(element=>element.scrollTop=0);expect(await diffScroll.evaluate(element=>element.scrollTop)).toBe(leftScroll)
  await list.evaluate(element=>element.scrollTop=element.scrollHeight);await atBottom()
  const card=diff.locator('.arrangement-change-card').first();await card.scrollIntoViewIfNeeded();const panelScroll=await diffScroll.evaluate(element=>element.scrollTop)
  const revision=(await s.state()).layout_revision;await activate(info,card);expect(await diffScroll.evaluate(element=>element.scrollTop)).toBe(panelScroll);expect((await s.state()).layout_revision).toBe(revision)
  await fixed();expect((await s.area.locator('td.grid-located').count())).toBeGreaterThan(0)
  await page.screenshot({path:info.outputPath('sidebar-independent-scroll.png'),fullPage:true})
  await activate(info,toggle);await activate(info,toggle);await atBottom();await expect(list.locator('.version-item').last()).toContainText('捲動版本 12最新')
})

import { expect, test, type Page, type TestInfo } from '@playwright/test'

const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => prefix + path
const activate = (info: TestInfo, locator: any) => info.project.name === 'mobile' ? locator.tap() : locator.click()

async function setup(page: Page, info: TestInfo) {
  await page.goto(url('/admin/competitions'))
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('navigation', { name: '管理功能' })).toBeVisible()
  const me = await (await page.request.get(url('/api/auth/me'))).json(), headers = { 'X-CSRF-Token': me.csrf_token }
  const comp = await (await page.request.post(url('/api/admin/competitions'), { headers, data: { name: `手機流程-${info.project.name}-${info.testId}`, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: 10, status: 'open', notes: '僅合成資料' } })).json()
  const people: any[] = []
  for (let i = 0; i < 3; i++) {
    const member = await (await page.request.post(url('/api/admin/members'), { headers, data: { name: i < 2 ? '合成同名操作' : '合成操作三', distinguishing_note: `辨識${i}`, level: i + 1, diet: i === 0 ? 'vegetarian' : 'unset', is_active: true } })).json()
    const registration = await page.request.post(url(`/api/admin/competitions/${comp.id}/registrations`), { headers, data: { member_id: member.id, diet: i < 2 ? 'vegetarian' : 'unset', request_id: crypto.randomUUID() } })
    expect(registration.status()).toBe(201); people.push(await registration.json())
  }
  await page.reload()
  await page.getByLabel('選擇比賽', { exact: true }).selectOption(comp.id)
  const area = page.getByRole('region', { name: '當次比賽級數安排' })
  const endpoint = url(`/api/admin/competitions/${comp.id}/arrangement`)
  const state = async () => (await page.request.get(endpoint)).json()
  await expect.poll(async () => !!(await state()).layout).toBe(true)
  await expect(area.locator('.arrangement-status')).not.toContainText('讀取中')
  return { area, endpoint, state, people, headers, comp }
}
const position = (state: any, id: string) => { const cell = state.layout.cells.find((c: any) => c.registration_id === id); return [cell.row_id, cell.column_id] }

test('手機會員與公告分頁保留草稿，報名操作使用可關閉的觸控面板', async ({ page }, info) => {
  const s = await setup(page, info)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('link', { name: '會員管理', exact: true }).click()
  await page.getByLabel('搜尋會員').fill('合成會員一')
  await page.getByRole('button', { name: /合成會員一/ }).click()
  await page.getByLabel('重名辨識註記').fill('保留中的手機草稿')
  await page.getByRole('button', { name: '← 返回會員清單（保留輸入）' }).click()
  await expect(page.getByLabel('姓名（必填）')).toBeHidden()
  await page.getByRole('button', { name: /合成會員一/ }).click()
  await expect(page.getByLabel('重名辨識註記')).toHaveValue('保留中的手機草稿')
  await page.setViewportSize({ width: 1440, height: 900 }); await expect(page.getByLabel('搜尋會員')).toBeVisible()
  await expect(page.getByLabel('重名辨識註記')).toHaveValue('保留中的手機草稿')
  await page.setViewportSize({ width: 390, height: 844 }); await expect(page.getByLabel('重名辨識註記')).toHaveValue('保留中的手機草稿')
  await page.getByRole('link', { name: '公告管理', exact: true }).click()
  await page.getByRole('button', { name: '新增公告' }).click()
  await page.getByLabel('公告標題').fill('合成手機公告')
  await page.getByLabel('公告內容').fill('公告草稿')
  await page.getByRole('button', { name: '← 返回公告清單（保留輸入）' }).click()
  await page.getByRole('button', { name: '繼續編輯公告' }).click()
  await expect(page.getByLabel('公告內容')).toHaveText('公告草稿')
  await page.setViewportSize({ width: 1440, height: 900 }); await expect(page.getByLabel('公告內容')).toHaveText('公告草稿')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('link', { name: '比賽管理', exact: true }).click()
  await page.getByLabel('選擇比賽', { exact: true }).selectOption(s.comp.id)
  await page.getByRole('button', { name: '報名與設定', exact: true }).click()
  await page.locator('.mobile-registration-list').getByRole('button', { name: /合成同名操作/ }).first().click()
  const panel = page.getByRole('dialog', { name: '報名管理操作' })
  await expect(panel).toBeVisible()
  await expect(panel.getByLabel('合成同名操作當次餐食')).toBeVisible()
  await page.screenshot({ path: info.outputPath('registration-sheet.png'), fullPage: true })
  await page.keyboard.press('Escape'); await expect(panel).toHaveCount(0)
})


const dragSurface = (page: Page, s: any, index = 0) => s.area.locator(`[data-registration-id="${s.people[index].id}"] ${page.viewportSize()!.width <= 900 ? '.cell-name' : '.cell-grip'}`)

async function gridDrag(page: Page, info: TestInfo, s: any, source = 0, target = 1, options: { cancel?: boolean; context?: boolean; fraction?: number; point?: { row_id: string; column_id: string }; beforeRelease?: () => Promise<void> } = {}) {
  await expect(s.area.locator(`[data-registration-id="${s.people[source].id}"]`)).toHaveAttribute('data-draggable','true')
  const from = dragSurface(page,s,source)
  const to = options.point ? s.area.locator(`td[data-grid-cell="${options.point.row_id}/${options.point.column_id}"]`) : s.area.locator(`td[data-drop-registration="${s.people[target].id}"]`)
  await from.evaluate(el=>el.scrollIntoView({block:'center',inline:'nearest'}))
  const a = (await from.boundingBox())!, b = (await to.boundingBox())!
  const start = { x: a.x + a.width / 2, y: a.y + a.height / 2 }, finish = { x: b.x + b.width / 2, y: b.y + b.height * (options.fraction ?? .5) }
  if (info.project.name === 'mobile') {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [start] })
    // Deliberately move immediately: waiting for the old long-press timer masked this bug.
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [finish] })
    if (options.context) await from.dispatchEvent('contextmenu', { bubbles: true, cancelable: true, clientX: finish.x, clientY: finish.y, button: 2 })
    await expect(page.getByRole('dialog', { name: '儲存格操作', exact: true })).toHaveCount(0)
    await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent', options.point ? 'move_empty' : options.fraction ? 'insert' : 'swap')
    if(options.beforeRelease)await options.beforeRelease()
    await cdp.send('Input.dispatchTouchEvent', { type: options.cancel ? 'touchCancel' : 'touchEnd', touchPoints: [] })
    await cdp.detach()
  } else {
    await page.mouse.move(start.x,start.y); await page.mouse.down(); await page.mouse.move(finish.x,finish.y,{steps:5})
    await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent', options.point ? 'move_empty' : options.fraction ? 'insert' : 'swap')
    if(options.beforeRelease)await options.beforeRelease()
    if (options.cancel) await page.keyboard.press('Escape')
    await page.mouse.up()
  }
}

test('單一表格快速拖曳不被觸控右鍵遮擋，點按取消與桌面選單相容', async ({ page }, info) => {
  const s = await setup(page,info)
  await expect(s.area.getByRole('group',{name:'安排顯示方式'})).toHaveCount(0)
  await expect(s.area.getByRole('button',{name:'名單操作',exact:true})).toHaveCount(0)
  await expect(s.area.getByRole('table',{name:'當次級數表'})).toBeVisible()
  const before = await s.state(), writes: any[] = []
  page.on('request',r=>{if(r.method()==='POST' && r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  const grip = dragSurface(page,s)
  await activate(info,grip); expect(writes).toHaveLength(0)
  await s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'儲存格操作',exact:true})).toBeVisible()
  await gridDrag(page,info,s,0,1,{context:true,cancel:true})
  expect((await s.state()).state_token).toBe(before.state_token);expect(writes).toHaveLength(0)
  await gridDrag(page,info,s,0,1,{context:true})
  await expect.poll(async()=>position(await s.state(),s.people[0].id)).toEqual(position(before,s.people[1].id))
  expect(writes).toHaveLength(1);expect(writes[0].operation.action).toBe('swap')
  await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(grip).toBeEnabled()
  await gridDrag(page,info,s,0,1,{context:true,fraction:.1})
  await expect.poll(()=>writes.length).toBe(2)
  await expect(grip).toBeEnabled()
  const inserted=await s.state(), empty={row_id:inserted.layout.rows[3].id,column_id:inserted.layout.columns[0].id}
  await gridDrag(page,info,s,0,1,{context:true,point:empty})
  await expect.poll(async()=>position(await s.state(),s.people[0].id)).toEqual([empty.row_id,empty.column_id])
  expect(writes).toHaveLength(3)
  // The normal selection/menu path remains explicit on touch and supports desktop right click.
  const name = s.area.locator('.cell-name').first()
  await activate(info,name)
  if(info.project.name==='mobile') {
    for(const selector of ['.cell-name','.cell-grip','.grid-empty','.grid-column-title','.grid-axis-more']) {
      await s.area.locator(selector).first().dispatchEvent('contextmenu',{bubbles:true,cancelable:true,button:2})
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.locator('.grid-axis-popup,.axis-delete-dialog')).toHaveCount(0)
    }
    await s.area.getByRole('button',{name:'開啟儲存格操作',exact:true}).tap()
  } else await name.click({button:'right'})
  await expect(page.getByRole('dialog',{name:'儲存格操作',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  await name.focus();await page.keyboard.press('Shift+F10')
  await expect(page.getByRole('dialog',{name:'儲存格操作',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  await page.screenshot({path:info.outputPath('single-grid.png'),fullPage:true})
})

test('拖曳未知原樣恢復及外來版本409，不重複或自動覆寫',async({page},info)=>{
  const s=await setup(page,info),writes:any[]=[]
  let first=true
  await page.route('**/arrangement/operations',async route=>{
    writes.push(route.request().postDataJSON())
    if(first){first=false;await route.fetch();await route.abort('failed')}else await route.continue()
  })
  await gridDrag(page,info,s)
  await expect(s.area.locator('.arrangement-recovery')).toContainText('結果尚未確認')
  await expect(s.area.locator('.cell-grip').first()).toBeDisabled()
  await s.area.getByRole('button',{name:'確認操作結果／原樣重試'}).click()
  await expect(s.area.locator('.arrangement-recovery')).toHaveCount(0)
  expect(writes).toHaveLength(2);expect(writes[1]).toEqual(writes[0])
  await page.unroute('**/arrangement/operations')
  const current=await s.state()
  const external=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,operation:{action:'move_bottom',registration_id:s.people[2].id,level:8}}})
  expect(external.status()).toBe(200)
  const request=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations') && r.status()===409)
  await gridDrag(page,info,s);await request
  await expect(s.area.locator('.cell-grip').first()).toBeDisabled()
  await s.area.getByRole('button',{name:'重新讀取並核對',exact:true}).click()
  await expect(s.area.locator('.arrangement-recovery')).toHaveCount(0)
  expect((await s.state()).rows.find((r:any)=>r.registration_id===s.people[2].id).competition_level).toBe(8)
})

test('素食名單依顯示布局列出隊名，不受搜尋裁減；帳號在備份右側',async({page},info)=>{
  await page.route('**/api/admin/backup-status',route=>route.fulfill({json:{state:'ok',last_success_at:'2026-10-04T00:00:00Z'}}))
  const s=await setup(page,info)
  const header=page.locator('.admin-status-line')
  await expect(header.locator('.admin-backup')).toContainText('備份正常')
  await expect(header.locator('.admin-username')).toHaveText('e2e-admin')
  const a=(await header.locator('.admin-backup').boundingBox())!,b=(await header.locator('.admin-username').boundingBox())!
  expect(b.x).toBeGreaterThanOrEqual(a.x+a.width)
  expect(Math.abs((a.y+a.height/2)-(b.y+b.height/2))).toBeLessThan(5)
  const initial=await s.state()
  if(info.project.name==='desktop')await s.area.getByRole('button',{name:'搜尋姓名',exact:true}).click()
  await s.area.getByLabel('搜尋姓名或辨識註記').fill('合成操作三')
  await s.area.getByRole('button',{name:'素食 2 人',exact:true}).click()
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  const dialog=page.getByRole('dialog',{name:'本場素食名單・2 人'})
  await expect(dialog.locator('li')).toHaveCount(2)
  await expect(dialog.locator('li').nth(1)).toContainText('2 級')
  await expect(dialog.locator('li').nth(1)).toContainText('操作隊')
  await expect(dialog.locator('li').nth(1)).toContainText('合成同名操作（辨識1）')
  await page.screenshot({path:info.outputPath('vegetarian-roster.png'),fullPage:true})
  await dialog.getByRole('button',{name:'關閉名單'}).click()
  expect((await s.state()).state_token).toBe(initial.state_token)
  const op=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:initial.state_token,operation:{action:'move_empty',registration_id:s.people[0].id,target:{row_id:initial.layout.rows[1].id,column_id:initial.layout.columns.find((c:any)=>c.level===1).id}}}})
  expect(op.status()).toBe(200)
  await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(s.comp.id)
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  await expect(dialog.locator('li').nth(1)).toContainText('操作隊')
  await dialog.getByRole('button',{name:'關閉名單'}).click()
  for(const width of [360,390,430,768,1440]){
    await page.setViewportSize({width,height:900})
    await expect(header.locator('.admin-username')).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    const toggle=s.area.locator('.vegetarian-toggle'), trigger=s.area.getByRole('button',{name:'查看素食人員名單'})
    await trigger.scrollIntoViewIfNeeded()
    const badge=(await trigger.locator('.vegetarian-roster-badge').boundingBox())!, button=(await toggle.boundingBox())!, hit=(await trigger.boundingBox())!
    expect(badge.width).toBe(24);expect(badge.height).toBe(24)
    expect(badge.x).toBeLessThan(button.x+button.width)
    expect(badge.x+badge.width).toBeLessThan(button.x+button.width)
    expect(badge.y).toBeGreaterThan(button.y)
    expect(badge.y+badge.height).toBeLessThan(button.y+button.height)
    expect(hit.width).toBeGreaterThanOrEqual(44);expect(hit.height).toBeGreaterThanOrEqual(44)
    const textEnd=await toggle.evaluate(el=>{
      const range=document.createRange();range.selectNodeContents(el)
      const rect=range.getBoundingClientRect()
      return {x:rect.right-2,y:rect.top+rect.height/2}
    })
    expect(textEnd.x).toBeLessThan(hit.x)
    const beforeToggle=await toggle.getAttribute('aria-pressed')
    if(info.project.name==='mobile')await page.touchscreen.tap(textEnd.x,textEnd.y)
    else await page.mouse.click(textEnd.x,textEnd.y)
    await expect(toggle).toHaveAttribute('aria-pressed',beforeToggle==='true'?'false':'true')
    await expect(dialog).toHaveCount(0)
    const pressed=await toggle.getAttribute('aria-pressed')
    await activate(info,trigger);await expect(dialog).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-pressed',pressed!)
    await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0)
    if(width===360||width===1440) await page.screenshot({path:info.outputPath(`roster-trigger-${width}.png`),clip:{x:Math.max(0,button.x-8),y:Math.max(0,badge.y-8),width:Math.min(button.width+44, width-Math.max(0,button.x-8)),height:button.height+30}})
  }
})

test('名單讀取多層欄名與合併隊名，保存後歷史保留原標籤',async({page},info)=>{
  const s=await setup(page,info)
  const op=async(operation:any)=>{
    const current=await s.state()
    const response=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:current.state_token,operation}})
    expect(response.status()).toBe(200)
  }
  await op({action:'insert_header',before_id:null});await op({action:'insert_header',before_id:null})
  await op({action:'insert_column',before_id:(await s.state()).layout.columns[0].id})
  const layout=(await s.state()).layout, [h1,h2,r1,r2]=layout.rows, [team,c1,c2,c3]=layout.columns
  const point=(row:any,col:any)=>({row_id:row.id,column_id:col.id})
  await op({action:'text',target:point(h1,c3),text:'乙組'})
  await op({action:'merge',start:point(h1,c1),end:point(h1,c3)})
  await op({action:'text',target:point(h2,c2),text:'下午場'})
  await op({action:'text',target:point(r2,team),text:'釋教合成隊'})
  await op({action:'merge',start:point(r1,team),end:point(r2,team)})
  const reload=async()=>{await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(s.comp.id);await expect(s.area.locator('.cell-grip').first()).toBeEnabled()}
  await reload()
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  const list=page.getByRole('dialog',{name:'本場素食名單・2 人'})
  await expect(list.locator('li').nth(1).locator('.vegetarian-roster-columns')).toHaveText('2 級乙組下午場')
  await expect(list.locator('li').nth(1).locator('.vegetarian-roster-team')).toHaveText('釋教合成隊')
  await page.screenshot({path:info.outputPath('roster-multilevel.png'),fullPage:true})
  await list.getByRole('button',{name:'關閉名單'}).click()
  await s.area.getByRole('button',{name:'保存完整安排',exact:true}).click()
  const save=page.getByRole('dialog',{name:'保存完整安排'})
  await save.getByLabel('版本名稱').fill('欄名隊名原版');await save.getByRole('button',{name:'保存',exact:true}).click()
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存')
  await op({action:'text',target:point(r2,team),text:'重新組隊'})
  await op({action:'text',target:point(h1,c3),text:'甲組'})
  await reload()
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  await expect(list.locator('li').nth(1)).toContainText('重新組隊')
  await expect(list.locator('li').nth(1)).toContainText('甲組')
  await list.getByRole('button',{name:'關閉名單'}).click()
  await s.area.getByRole('button',{name:'歷史',exact:true}).click()
  await s.area.getByRole('button',{name:/^欄名隊名原版/}).click()
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  const history=page.getByRole('dialog',{name:'此版本素食名單・2 人'})
  await expect(history.locator('li').nth(1)).toContainText('釋教合成隊')
  await expect(history.locator('li').nth(1)).toContainText('乙組')
  await expect(history).not.toContainText('重新組隊')
})


test('較大觸控畫面拖曳關閉軸選單，舊歷史餐食和隊長維持未知',async({page},info)=>{
  test.skip(info.project.name!=='mobile','Touch pointer coverage')
  const s=await setup(page,info)
  await page.setViewportSize({width:1024,height:900})
  await s.area.getByRole('button',{name:'第 1 排更多操作',exact:true}).tap()
  await expect(page.locator('.grid-axis-popup')).toBeVisible()
  await gridDrag(page,info,s,0,1,{context:true})
  await expect(page.locator('.grid-axis-popup,.axis-delete-dialog')).toHaveCount(0)
  await expect(s.area.locator('.cell-grip').first()).toBeEnabled()
  await s.area.getByRole('button',{name:'保存完整安排',exact:true}).click()
  const save=page.getByRole('dialog',{name:'保存完整安排'})
  await save.getByLabel('版本名稱').fill('素食歷史')
  await save.getByRole('button',{name:'保存',exact:true}).click()
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存')
  await page.route('**/arrangement/versions/*',async route=>{
    const response=await route.fetch(), body=await response.json()
    body.layout=null;body.rows[0].diet=null
    await route.fulfill({json:body})
  })
  await s.area.getByRole('button',{name:'歷史',exact:true}).click()
  await s.area.getByRole('button',{name:/^素食歷史/}).click()
  await expect(s.area.getByText('舊版未記錄儲存格位置；以下僅按級數與順位檢視，不代表當時分組。未保存的餐食與長期級數顯示未知。')).toBeVisible()
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  const list=page.getByRole('dialog',{name:/此版本素食名單/})
  await expect(list.getByText('此版本未記錄格位，欄名與隊伍未知。')).toBeVisible()
  await expect(list.getByText('1 人的餐食未記錄，未列入素食名單。')).toBeVisible()
  await expect(list.locator('li')).toHaveCount(1)
  await expect(list.locator('li')).toContainText('隊伍未知')
})


test('起拖後外來更新仍以起拖token拒絕，拖曳鍵盤選單不延後冒出',async({page},info)=>{
  const s=await setup(page,info),before=await s.state(),writes:any[]=[]
  await page.route('**/arrangement/operations',async route=>{writes.push(route.request().postDataJSON());await route.continue()})
  const rejected=page.waitForResponse(r=>r.url().endsWith('/arrangement/operations')&&r.status()===409)
  await gridDrag(page,info,s,0,1,{context:true,beforeRelease:async()=>{
    await page.keyboard.press('Shift+F10')
    await expect(page.getByRole('dialog',{name:'儲存格操作',exact:true})).toHaveCount(0)
    const external=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:before.state_token,operation:{action:'move_bottom',registration_id:s.people[2].id,level:8}}})
    expect(external.status()).toBe(200)
  }})
  await rejected
  expect(writes).toHaveLength(1);expect(writes[0].state_token).toBe(before.state_token)
  await expect(page.getByRole('dialog',{name:'儲存格操作',exact:true})).toHaveCount(0)
  await s.area.getByRole('button',{name:'重新讀取並核對',exact:true}).click()
  await expect(s.area.locator('.arrangement-recovery')).toHaveCount(0)
  expect(position(await s.state(),s.people[0].id)).toEqual(position(before,s.people[0].id))
})

test('手機長按方塊與第二指介入不留下選單或誤寫',async({page},info)=>{
  test.skip(info.project.name!=='mobile','Touch pointer coverage')
  const s=await setup(page,info),before=await s.state(),writes:any[]=[]
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  const grip=dragSurface(page,s)
  await grip.evaluate(el=>el.scrollIntoView({block:'center',inline:'nearest'}))
  const a=(await grip.boundingBox())!,b=(await s.area.locator(`td[data-drop-registration="${s.people[1].id}"]`).boundingBox())!
  const start={x:a.x+a.width/2,y:a.y+a.height/2,id:0},end={x:b.x+b.width/2,y:b.y+b.height/2,id:0}
  const cdp=await page.context().newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]})
  await page.waitForTimeout(650) // Exercise the browser long-press interval, not readiness polling.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  expect(writes).toHaveLength(0)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[end]})
  await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent','swap')
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[end,{...start,id:1}]})
  await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  // A second finger outside the name also cancels tap counting.
  const name=s.area.locator(`[data-registration-id="${s.people[0].id}"] .cell-name`)
  const nameBox=(await name.boundingBox())!,tap={x:nameBox.x+nameBox.width/2,y:nameBox.y+nameBox.height/2,id:0}
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[tap]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[tap,{x:20,y:20,id:1}]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await cdp.detach()
  await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog',{name:'合成同名操作',exact:true})).toBeVisible()
  expect(writes).toHaveLength(0);expect((await s.state()).state_token).toBe(before.state_token)
})

test('手機整張選手卡含四邊與註記可起拖，輕點雙點和取消不誤寫',async({page},info)=>{
  test.skip(info.project.name!=='mobile','Narrow touch gestures')
  const s=await setup(page,info),before=await s.state(),writes:any[]=[]
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  const card=s.area.locator(`[data-registration-id="${s.people[0].id}"]`),name=card.locator('.cell-name')
  await name.evaluate(el=>el.scrollIntoView({block:'center',inline:'nearest'}))
  await expect(card.locator('.cell-grip')).toBeHidden()
  const box=(await card.boundingBox())!,button=(await name.boundingBox())!,note=(await name.locator('small').boundingBox())!
  expect(button).toEqual(box)
  const target=(await s.area.locator(`td[data-drop-registration="${s.people[1].id}"]`).boundingBox())!
  const finish={x:target.x+target.width/2,y:target.y+target.height/2}
  const center={x:box.x+box.width/2,y:box.y+box.height/2}
  const starts=[{x:box.x+1,y:center.y},{x:box.x+box.width-1,y:center.y},{x:center.x,y:box.y+1},{x:center.x,y:box.y+box.height-1},{x:note.x+note.width/2,y:note.y+note.height/2}]
  const cdp=await page.context().newCDPSession(page)
  for(const start of starts){
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]})
    await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[finish]})
    await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent','swap')
    await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]})
    await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  }
  await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog',{name:'合成同名操作',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  // A 7px movement must not count as a tap; returning to the start still cancels it.
  await name.tap()
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[center]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{...center,x:center.x+7}]})
  await expect(page.locator('.level-drag-ghost')).toBeVisible()
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[center]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog',{name:'合成同名操作',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  // Losing capture before movement must also discard the tap sequence.
  await name.tap()
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[center]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{...center,x:center.x+1}]})
  await page.keyboard.press('Escape')
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog',{name:'合成同名操作',exact:true})).toBeVisible()
  await page.keyboard.press('Escape');await cdp.detach()
  expect(writes).toHaveLength(0);expect((await s.state()).state_token).toBe(before.state_token)
  await page.screenshot({path:info.outputPath('whole-card-mobile.png'),fullPage:true})
})

test('900px整卡與901px桌面邊界保留把手樣式和姓名原生捲動',async({page},info)=>{
  test.skip(info.project.name!=='mobile','Touch breakpoint coverage')
  const s=await setup(page,info),before=await s.state()
  const card=s.area.locator(`[data-registration-id="${s.people[0].id}"]`),name=card.locator('.cell-name'),grip=card.locator('.cell-grip')
  for(const width of [900,901,900,1024]){
    await page.setViewportSize({width,height:844})
    if(width<=900){await expect(grip).toBeHidden();await expect(name).toHaveCSS('touch-action','none')}
    else{await expect(grip).toBeVisible();await expect(grip).toHaveCSS('width','44px');await expect(name).toHaveCSS('touch-action','manipulation')}
  }
  await name.evaluate(el=>el.scrollIntoView({block:'center',inline:'nearest'}))
  const box=(await name.boundingBox())!,cdp=await page.context().newCDPSession(page),start={x:box.x+box.width/2,y:box.y+box.height/2}
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start.x+80,y:start.y}]})
  await expect(page.locator('.level-drag-ghost')).toHaveCount(0)
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()
  expect((await s.state()).state_token).toBe(before.state_token)
  await gridDrag(page,info,s)
  await expect.poll(async()=>position(await s.state(),s.people[0].id)).toEqual(position(before,s.people[1].id))
})

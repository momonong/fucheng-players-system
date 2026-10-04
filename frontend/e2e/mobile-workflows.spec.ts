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


async function gridDrag(page: Page, info: TestInfo, s: any, source = 0, target = 1, options: { cancel?: boolean; context?: boolean; fraction?: number; point?: { row_id: string; column_id: string }; beforeRelease?: () => Promise<void> } = {}) {
  const from = s.area.locator(`[data-registration-id="${s.people[source].id}"] .cell-grip`)
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
  const grip = s.area.locator(`[data-registration-id="${s.people[0].id}"] .cell-grip`)
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

test('素食名單依顯示布局列出隊長，不受搜尋裁減；帳號在備份右側',async({page},info)=>{
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
  await expect(dialog.locator('li').nth(1)).toContainText('合成同名操作（辨識0） 隊長')
  await expect(dialog.locator('li').nth(1)).toContainText('合成同名操作（辨識1）')
  await page.screenshot({path:info.outputPath('vegetarian-roster.png'),fullPage:true})
  await dialog.getByRole('button',{name:'關閉名單'}).click()
  expect((await s.state()).state_token).toBe(initial.state_token)
  const op=await page.request.post(s.endpoint+'/operations',{headers:s.headers,data:{request_id:crypto.randomUUID(),state_token:initial.state_token,operation:{action:'move_empty',registration_id:s.people[0].id,target:{row_id:initial.layout.rows[1].id,column_id:initial.layout.columns.find((c:any)=>c.level===1).id}}}})
  expect(op.status()).toBe(200)
  await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(s.comp.id)
  await s.area.getByRole('button',{name:'查看素食人員名單'}).click()
  await expect(dialog.locator('li').nth(1)).toContainText('隊長未安排')
  await dialog.getByRole('button',{name:'關閉名單'}).click()
  for(const width of [360,390,430,768,1440]){
    await page.setViewportSize({width,height:900})
    await expect(header.locator('.admin-username')).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
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
  await expect(list.getByText('此版本未記錄格位，無法判定隊長。')).toBeVisible()
  await expect(list.getByText('1 人的餐食未記錄，未列入素食名單。')).toBeVisible()
  await expect(list.locator('li')).toHaveCount(1)
  await expect(list.locator('li')).toContainText('隊長未知')
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

test('手機長按把手與第二指介入不留下選單或誤寫',async({page},info)=>{
  test.skip(info.project.name!=='mobile','Touch pointer coverage')
  const s=await setup(page,info),before=await s.state(),writes:any[]=[]
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/arrangement/operations'))writes.push(r.postDataJSON())})
  const grip=s.area.locator(`[data-registration-id="${s.people[0].id}"] .cell-grip`)
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
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[tap,{...start,id:1}]})
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await cdp.detach()
  await name.tap();await expect(page.getByRole('dialog')).toHaveCount(0)
  await name.tap();await expect(page.getByRole('dialog',{name:'合成同名操作',exact:true})).toBeVisible()
  expect(writes).toHaveLength(0);expect((await s.state()).state_token).toBe(before.state_token)
})

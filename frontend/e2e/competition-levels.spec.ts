import { expect, test, request, type Page, type TestInfo } from '@playwright/test'
type Row = { id: string; member_id: string; member_name: string; competition_level: number; hard_level_snapshot: number; version: number }
async function setup(page: Page, info: TestInfo, suffix: string, count = 3) {
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-levels-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '比賽', exact: true })).toBeVisible()
  const me = await (await page.request.get('/api/auth/me')).json()
  const headers = { 'X-CSRF-Token': me.csrf_token }
  const name = `合成安排-${info.project.name}-${suffix}`
  const payload = { name, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: count, status: 'open', notes: '獨立合成資料' }
  const comp = await (await page.request.post('/api/admin/competitions', { headers, data: payload })).json()
  const other = await (await page.request.post('/api/admin/competitions', { headers, data: { ...payload, name: `${name}-另一場` } })).json()
  const rows: Row[] = []
  for (let i = 0; i < count + 2; i++) {
    const member = await (await page.request.post('/api/admin/members', { headers, data: { name: i < 2 ? '安排同名' : i === 2 ? '合成超長姓名測試會員' : `合成選手${String(i).padStart(2, '0')}`, distinguishing_note: `辨識${i}`, level: i === 0 ? 5 : i % 10 + 1, diet: 'unset', is_active: true } })).json()
    const registered = await page.request.post(`/api/admin/competitions/${comp.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })
    expect(registered.status()).toBe(201); rows.push(await registered.json())
    if (i === 0) expect((await page.request.post(`/api/admin/competitions/${other.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })).status()).toBe(201)
  }
  expect((await page.request.post(`/api/admin/registrations/${rows[count + 1].id}/cancel`, { headers, data: { version: 1, request_id: crypto.randomUUID() } })).status()).toBe(200)
  expect((await page.request.put(`/api/admin/competitions/${comp.id}`, { headers, data: { ...payload, status: 'closed', version: 1 } })).status()).toBe(200)
  await page.reload()
  const area = page.getByRole('region', { name: '當次比賽級數安排' })
  const choose = async (otherScene = false) => {
    await page.getByLabel('選擇比賽', { exact: true }).selectOption(otherScene ? other.id : comp.id)
    await expect(area.getByRole('heading', { name: otherScene ? other.name : comp.name, exact: true })).toBeVisible()
    await expect(area.locator('.arrangement-cell')).toHaveCount(otherScene ? 1 : count)
  }
  await choose()
  const cell = (i: number) => area.locator(`[data-registration-id="${rows[i].id}"]`)
  const endpoint = `/api/admin/competitions/${comp.id}/arrangement`
  const state = async () => (await page.request.get(endpoint)).json()
  const read = async (i: number) => (await (await page.request.get(`/api/admin/competitions/${comp.id}`)).json()).registrations.find((r: Row) => r.id === rows[i].id)
  const history = async () => (await (await page.request.get(`/api/admin/competitions/${comp.id}/history`)).json()).filter((r: { action: string }) => r.action === 'level')
  const move = async (i: number, level: number, wait = true) => {
    await cell(i).locator('.cell-name').focus(); await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('移到級數').selectOption(String(level))
    await dialog.getByRole('button', { name: '移動', exact: true }).click()
    if (wait) { await expect(cell(i)).not.toHaveClass(/cell-pending/); await expect.poll(async () => (await read(i)).competition_level).toBe(level) }
  }
  const save = async (label?: string, editor?: string, note?: string) => {
    await area.getByRole('button', { name: '保存完整安排', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '保存完整安排' })
    if (label) await dialog.getByLabel('版本名稱').fill(label)
    if (editor) await dialog.getByLabel('顯示編輯者').fill(editor)
    if (note) await dialog.getByLabel('備註（選填）').fill(note)
    await dialog.getByRole('button', { name: '保存', exact: true }).click()
  }
  return { comp, other, payload, headers, rows, area, choose, cell, endpoint, state, read, history, move, save }
}

test('緊湊八十人表格、真實拖曳橫捲、淨差保存及唯讀歷史', async ({ page }, info) => {
  const s = await setup(page, info, 'table', 80)
  await expect(s.area.locator('thead th')).toHaveCount(10)
  await expect(s.area.getByText(/正取|候補|取消/)).toHaveCount(0)
  await expect(s.area.locator('.level-drop-shortcuts,.level-name-card,.level-session-reason')).toHaveCount(0)
  await expect(s.area.getByRole('textbox')).toHaveCount(0)
  await expect(s.area.getByRole('button', { name: '保存完整安排' })).toBeDisabled()
  await expect(s.cell(0).locator('.cell-grip')).toBeEnabled()
  const table = s.area.locator('.arrangement-table-scroll')
  await table.scrollIntoViewIfNeeded()
  await page.evaluate(() => { (window as unknown as { pointers: string[] }).pointers = []; window.addEventListener('pointerdown', e => { (window as unknown as { pointers: string[] }).pointers.push(`${e.pointerType}:${e.isTrusted}`) }) })
  if (info.project.name === 'mobile') {
    // A normal touch swipe on the name scrolls horizontally without changing the registration.
    await table.evaluate(el => el.scrollLeft = 0)
    const box = (await table.boundingBox())!
    const cdp = await page.context().newCDPSession(page)
    const y = box.y + 80
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: box.x + box.width - 30, y }] })
    for (let i = 1; i <= 10; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: box.x + box.width - 30 - i * 24, y }] })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await expect.poll(() => table.evaluate(el => el.scrollLeft)).toBeGreaterThan(50)
    await expect.poll(async () => (await s.read(0)).version).toBe(1)
    // Start from level 5 and hold the right edge until the farthest column arrives.
    const handle = s.cell(0).locator('.cell-grip')
    await handle.scrollIntoViewIfNeeded()
    const from = (await handle.boundingBox())!
    const x = from.x + from.width / 2, sy = from.y + from.height / 2
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: sy }] })
    await expect(page.locator('.level-drag-ghost')).toBeVisible()
    const edge = (await table.boundingBox())!
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: edge.x + edge.width - 8, y: sy }] })
    await expect.poll(() => table.evaluate(el => el.scrollLeft + el.clientWidth >= el.scrollWidth - 4)).toBe(true)
    const dest = (await s.area.locator('tbody tr').first().locator('td').nth(9).boundingBox())!
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: dest.x + dest.width / 2, y: sy }] })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await cdp.detach()
  } else {
    const from = (await s.cell(0).locator('.cell-grip').boundingBox())!
    const dest = (await s.area.locator('tbody tr').first().locator('td').nth(9).boundingBox())!
    await page.mouse.move(from.x + 8, from.y + 20); await page.mouse.down()
    await page.mouse.move(dest.x + dest.width / 2, dest.y + 20, { steps: 15 }); await page.mouse.up()
  }
  await expect.poll(async () => (await s.read(0)).competition_level).toBe(10)
  await expect(s.cell(0)).not.toHaveClass(/cell-pending/)
  expect(await page.evaluate(() => (window as unknown as { pointers: string[] }).pointers)).toContain(info.project.name === 'mobile' ? 'touch:true' : 'mouse:true')
  await s.move(0, 5)
  await expect(s.cell(0)).not.toHaveClass(/net-level/)
  const before = (await s.history()).length
  await s.move(0, 4); await s.move(0, 6)
  expect((await s.history()).length - before).toBe(2)
  await expect(s.cell(0)).toHaveClass(/net-level/)
  await expect(s.cell(0).locator('.cell-change')).toHaveText('5→6')
  await s.area.getByRole('button', { name: '歷史', exact: true }).click()
  await expect(s.area.locator('.arrangement-changes')).toContainText('5 → 6 級')
  await s.save('第一安排', '教練甲', '合成選填備註')
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存「第一安排」')
  await expect(s.cell(0)).not.toHaveClass(/net-level/)
  const first = (await s.state()).latest
  expect(first.actor_name).toBe('e2e-levels-admin'); expect(first.editor_label).toBe('教練甲')
  await s.move(0, 7); await s.save()
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存「版本 2」')
  await s.move(0, 8)
  const current = await s.state()
  await s.area.locator('.version-item').filter({ hasText: '第一安排' }).click()
  await expect(s.cell(0).locator('.cell-change')).toHaveText('5→6')
  await expect(s.area.getByText('實際操作：e2e-levels-admin')).toBeVisible()
  await expect(s.area.locator('.cell-grip')).toHaveCount(0)
  expect(await s.state()).toEqual(current)
  await s.area.locator('.version-item').filter({ hasText: '版本 2' }).click()
  await expect(s.cell(0).locator('.cell-change')).toHaveText('6→7')
  await s.area.getByRole('button', { name: '回目前安排', exact: true }).click()
  await expect(s.cell(0).locator('.cell-change')).toHaveText('7→8')
  await s.area.getByRole('button', { name: '搜尋姓名', exact: true }).click()
  await s.area.getByRole('searchbox').fill('安排同名')
  await expect(s.area.locator('.arrangement-cell')).toHaveCount(2)
  await expect(s.area.locator('thead th')).toHaveCount(10)
  await s.area.getByRole('searchbox').fill('')
  await s.area.getByRole('button', { name: '搜尋姓名', exact: true }).click()
  await s.area.getByRole('button', { name: '歷史', exact: true }).click()
  await table.evaluate(el => el.scrollLeft = 0)
  await s.area.evaluate(el => el.scrollIntoView({ block: 'start' }))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await s.area.locator('table').boundingBox().then(box => box!.height)).toBeLessThan(650)
  await page.screenshot({ path: info.outputPath('compact-80.png') })
  await page.reload(); await s.choose()
  await expect(s.cell(0).locator('.cell-change')).toHaveText('7→8')
  expect((await s.read(0)).hard_level_snapshot).toBe(5)
  const other = await (await page.request.get(`/api/admin/competitions/${s.other.id}`)).json()
  expect(other.registrations[0].competition_level).toBe(5)
})

test('大存未知結果、其他管理員新版本及切場晚回應保持目前基準', async ({ page }, info) => {
  const s = await setup(page, info, 'big-race')
  const peer = await request.newContext({ baseURL: new URL(page.url()).origin })
  const peerAuth = await (await peer.post('/api/auth/login', { data: { username: 'e2e-arrangement-peer', password: process.env.FUCHENG_E2E_ADMIN_PASSWORD } })).json()
  const peerHeaders = { 'X-CSRF-Token': peerAuth.csrf_token }
  await s.move(0, 6)
  const sent: Record<string, unknown>[] = []
  await page.route(`**${s.endpoint}/versions`, async route => {
    sent.push(route.request().postDataJSON())
    if (sent.length === 1) { expect((await route.fetch()).status()).toBe(200); await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成保存回應中斷' }) }) }
    else await route.continue()
  })
  await s.save('等待確認版', '編輯乙')
  await expect(s.area.getByRole('button', { name: '確認保存結果／原樣重試' })).toBeVisible()
  await expect(s.area.locator('.cell-grip')).toHaveCount(0)
  await expect(s.area.getByRole('button', { name: '保存完整安排', exact: true })).toBeDisabled()
  let row = await s.read(0)
  expect((await peer.put(`/api/admin/registrations/${row.id}/level`, { headers: peerHeaders, data: { version: row.version, competition_level: 7, request_id: crypto.randomUUID() } })).status()).toBe(200)
  const state = await s.state()
  const later = await peer.post(s.endpoint + '/versions', { headers: peerHeaders, data: { request_id: crypto.randomUUID(), state_token: state.state_token, base_version_id: state.latest.id, label: '後來新版本' } })
  expect(later.status()).toBe(200)
  row = await s.read(0)
  expect((await peer.put(`/api/admin/registrations/${row.id}/level`, { headers: peerHeaders, data: { version: row.version, competition_level: 8, request_id: crypto.randomUUID() } })).status()).toBe(200)
  await s.choose(true); await s.choose()
  await s.area.getByRole('button', { name: '確認保存結果／原樣重試' }).click()
  await expect(s.area.locator('.arrangement-status')).toContainText('其後已有其他異動')
  await expect(s.cell(0).locator('.cell-change')).toHaveText('7→8')
  expect(sent).toHaveLength(2); expect(sent[1]).toEqual(sent[0])
  expect((await s.state()).latest.label).toBe('後來新版本')
  expect((await s.state()).versions).toHaveLength(3)
  await page.unroute(`**${s.endpoint}/versions`)
  let release!: () => void
  const gate = new Promise<void>(resolve => release = resolve)
  let committed = false
  await page.route(`**${s.endpoint}/versions`, async route => { const response = await route.fetch(); committed = true; await gate; await route.fulfill({ response }) })
  try {
    await s.save('延遲版')
    await expect.poll(() => committed).toBe(true)
    await s.choose(true)
    release()
    await expect(s.area.getByRole('heading', { name: s.other.name, exact: true })).toBeVisible()
    await s.choose()
    await expect(s.cell(0)).not.toHaveClass(/net-level/)
    expect((await s.state()).latest.label).toBe('延遲版')
  } finally { release(); await peer.dispose() }
})

test('免原因移動未知重試與409保留、取消拖曳及終態唯讀', async ({ page }, info) => {
  const s = await setup(page, info, 'moves')
  const url = `/api/admin/registrations/${s.rows[0].id}/level`
  const sent: Record<string, unknown>[] = []
  await page.route(`**${url}`, async route => {
    sent.push(route.request().postDataJSON())
    if (sent.length === 1) { await route.fetch(); await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成移動中斷' }) }) }
    else await route.continue()
  })
  await s.move(0, 7, false)
  await expect(s.area.getByRole('button', { name: '確認移動結果／原樣重試' })).toBeVisible()
  await expect(s.cell(0).locator('.cell-grip')).toBeDisabled()
  await s.move(1, 4)
  expect((await s.read(1)).competition_level).toBe(4)
  await s.choose(true); await s.choose()
  await s.area.getByRole('button', { name: '確認移動結果／原樣重試' }).click()
  await expect(s.cell(0)).not.toHaveClass(/cell-pending/)
  expect(sent).toHaveLength(2); expect(sent[1]).toEqual(sent[0]); expect(sent[0].reason).toBeNull()
  expect((await s.history()).filter((r: { registration_id: string }) => r.registration_id === s.rows[0].id)).toHaveLength(1)
  await page.unroute(`**${url}`)
  const disconnected: Record<string, unknown>[] = []
  await page.route(`**${url}`, async route => { disconnected.push(route.request().postDataJSON()); if (disconnected.length === 1) await route.abort('failed'); else await route.continue() })
  await s.move(0, 8, false)
  await expect(s.area.getByRole('button', { name: '確認移動結果／原樣重試' })).toBeVisible()
  expect((await s.read(0)).competition_level).toBe(7)
  await s.area.getByRole('button', { name: '確認移動結果／原樣重試' }).click()
  await expect(s.cell(0)).not.toHaveClass(/cell-pending/)
  expect(disconnected).toHaveLength(2); expect(disconnected[0]).toEqual(disconnected[1])
  expect((await s.read(0)).competition_level).toBe(8)
  const row = await s.read(2)
  expect((await page.request.put(`/api/admin/registrations/${row.id}/level`, { headers: s.headers, data: { version: row.version, competition_level: 9, request_id: crypto.randomUUID() } })).status()).toBe(200)
  await s.move(2, 6, false)
  await expect(s.area.getByText(/其他管理員更新/)).toBeVisible()
  await s.area.getByRole('button', { name: '放棄未完成移動並核對' }).click()
  await expect(s.cell(2)).not.toHaveClass(/cell-pending/)
  expect((await s.read(2)).competition_level).toBe(9)
  const startVersion = (await s.read(1)).version
  const handle = s.cell(1).locator('.cell-grip'); await handle.scrollIntoViewIfNeeded()
  const box = (await handle.boundingBox())!
  if (info.project.name === 'mobile') {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: box.x + 10, y: box.y + 20 }] })
    await expect(page.locator('.level-drag-ghost')).toBeVisible()
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] }); await cdp.detach()
  } else {
    await page.mouse.move(box.x + 8, box.y + 20); await page.mouse.down(); await page.mouse.move(box.x + 25, box.y + 20)
    await page.keyboard.press('Escape'); await page.mouse.up()
  }
  expect((await s.read(1)).version).toBe(startVersion)
  expect((await page.request.put(`/api/admin/competitions/${s.comp.id}`, { headers: s.headers, data: { ...s.payload, status: 'ended', version: 2 } })).status()).toBe(200)
  await s.area.getByRole('button', { name: '重新讀取安排' }).click()
  await expect(s.area.locator('.cell-grip')).toHaveCount(0)
  await expect(s.area.getByRole('button', { name: '保存完整安排', exact: true })).toBeDisabled()
})

test('儲存後讀回前同卡鎖定、GET失敗復原及大存409保留輸入', async ({ page }, info) => {
  const s = await setup(page, info, 'refresh')
  let release!: () => void
  const gate = new Promise<void>(resolve => release = resolve)
  let waiting = false, first = true
  await page.route(`**${s.endpoint}`, async route => {
    if (first) { first = false; waiting = true; await gate; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成讀回失敗' }) }) }
    else await route.continue()
  })
  try {
    await s.move(0, 6, false)
    await expect.poll(() => waiting).toBe(true)
    await expect(s.cell(0).locator('.cell-grip')).toBeDisabled()
    await expect(s.cell(1).locator('.cell-grip')).toBeEnabled()
    release()
    await expect(s.area.getByText('合成讀回失敗', { exact: false })).toBeVisible()
    await expect(s.cell(0).locator('.cell-grip')).toBeDisabled()
    await s.area.getByRole('button', { name: '讀回目前安排', exact: true }).click()
    await expect(s.cell(0).locator('.cell-grip')).toBeEnabled()
    await s.move(0, 7)
    expect((await s.read(0)).version).toBe(3)
  } finally { release() }
  await page.unroute(`**${s.endpoint}`)
  let stale = true
  await page.route(`**${s.endpoint}/versions`, async route => {
    if (stale) {
      stale = false
      const row = await s.read(1)
      expect((await page.request.put(`/api/admin/registrations/${row.id}/level`, { headers: s.headers, data: { version: row.version, competition_level: 4, request_id: crypto.randomUUID() } })).status()).toBe(200)
    }
    await route.continue()
  })
  await s.save('保留名稱', '保留編輯者', '保留備註')
  await expect(s.area.getByRole('button', { name: '重新讀取並核對' })).toBeVisible()
  await s.area.getByRole('button', { name: '重新讀取並核對' }).click()
  await s.area.getByRole('button', { name: '保存完整安排', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('版本名稱')).toHaveValue('保留名稱')
  await expect(dialog.getByLabel('顯示編輯者')).toHaveValue('保留編輯者')
  await expect(dialog.getByLabel('備註（選填）')).toHaveValue('保留備註')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存「保留名稱」')
  expect((await s.state()).latest.rows.find((r: { registration_id: string }) => r.registration_id === s.rows[1].id).competition_level).toBe(4)
})

test('同名與重報遞補以報名ID比較、移出新增及更名歷史保留', async ({ page }, info) => {
  const s = await setup(page, info, 'membership')
  for (const i of [0, 1]) expect((await page.request.post(`/api/admin/registrations/${s.rows[i].id}/cancel`, { headers: s.headers, data: { version: 1, request_id: crypto.randomUUID(), reason: '合成名單調整' } })).status()).toBe(200)
  expect((await page.request.post(`/api/admin/registrations/${s.rows[3].id}/promote`, { headers: s.headers, data: { version: 1, request_id: crypto.randomUUID(), reason: '合成遞補' } })).status()).toBe(200)
  const rejoinedResponse = await page.request.post(`/api/admin/competitions/${s.comp.id}/registrations`, { headers: s.headers, data: { member_id: s.rows[0].member_id, request_id: crypto.randomUUID(), reason: '合成重報' } })
  expect(rejoinedResponse.status()).toBe(201)
  const rejoined = await rejoinedResponse.json()
  await s.area.getByRole('button', { name: '重新讀取安排' }).click()
  await expect(s.area.locator('.net-added')).toHaveCount(2)
  await expect(s.cell(0)).toHaveCount(0)
  await s.area.getByRole('button', { name: '歷史', exact: true }).click()
  await expect(s.area.locator('.arrangement-changes .net-removed')).toHaveCount(2)
  await expect(s.area.locator('.arrangement-changes .net-added')).toHaveCount(2)
  await expect(s.area.locator('.arrangement-changes .net-level')).toHaveCount(0)
  await s.save('名單調整版')
  await expect(s.area.locator('.arrangement-status')).toContainText('已保存「名單調整版」')
  const members = await (await page.request.get('/api/admin/members')).json()
  const member = members.find((row: { id: string }) => row.id === s.rows[0].member_id)
  expect((await page.request.put(`/api/admin/members/${member.id}`, { headers: s.headers, data: { name: '合成更名之後', distinguishing_note: '新辨識', legacy_number: member.legacy_number, level: member.level, diet: member.diet, is_active: true, version: member.version } })).status()).toBe(200)
  await s.area.getByRole('button', { name: '重新讀取安排' }).click()
  await expect(s.area.locator(`[data-registration-id="${rejoined.id}"]`)).toContainText('合成更名之後')
  await s.area.locator('.version-item').filter({ hasText: '名單調整版' }).click()
  await expect(s.area.locator(`[data-registration-id="${rejoined.id}"]`)).toContainText('安排同名')
  await expect(s.area.locator('.arrangement-changes .net-removed')).toHaveCount(2)
  await expect(s.area.locator('.arrangement-changes .net-added')).toHaveCount(2)
  await page.screenshot({ path: info.outputPath('membership-history.png') })
  await s.area.getByRole('button', { name: '回目前安排', exact: true }).click()
  await expect(s.area.locator(`[data-registration-id="${rejoined.id}"]`)).toContainText('合成更名之後')
  await expect(s.area.locator('.arrangement-changes li')).toHaveCount(0)
})

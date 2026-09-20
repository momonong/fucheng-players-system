import { expect, test, type Page, type Locator, type TestInfo } from '@playwright/test'

type Row = { id: string; member_id: string; member_name: string; competition_level: number; version: number }
async function setup(page: Page, info: TestInfo, suffix: string) {
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-levels-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '比賽', exact: true })).toBeVisible()
  const me = await (await page.request.get('/api/auth/me')).json()
  const headers = { 'X-CSRF-Token': me.csrf_token }
  const name = `合成卡片-${info.project.name}-${suffix}`
  const payload = { name, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: 3, status: 'open', notes: '獨立合成資料' }
  const comp = await (await page.request.post('/api/admin/competitions', { headers, data: payload })).json()
  const other = await (await page.request.post('/api/admin/competitions', { headers, data: { ...payload, name: `${name}-另一場` } })).json()
  const rows: Row[] = []
  for (let i = 0; i < 5; i++) {
    const member = await (await page.request.post('/api/admin/members', { headers, data: { name: `${name}-合成長姓名選手測試${i}`, distinguishing_note: `卡片辨識${i}`, level: i + 2, diet: 'unset', is_active: true } })).json()
    const registered = await page.request.post(`/api/admin/competitions/${comp.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })
    expect(registered.status()).toBe(201)
    rows.push(await registered.json())
    if (i === 0) expect((await page.request.post(`/api/admin/competitions/${other.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })).status()).toBe(201)
  }
  expect((await page.request.post(`/api/admin/registrations/${rows[4].id}/cancel`, { headers, data: { version: 1, request_id: crypto.randomUUID() } })).status()).toBe(200)
  expect((await page.request.put(`/api/admin/competitions/${comp.id}`, { headers, data: { ...payload, status: 'closed', version: 1 } })).status()).toBe(200)
  await page.reload()
  const choose = async (otherScene = false) => {
    await page.locator('.competition-item').filter({ has: page.getByText(otherScene ? other.name : comp.name, { exact: true }) }).click()
    await expect(page.getByLabel('名稱', { exact: true })).toHaveValue(otherScene ? other.name : comp.name)
    await expect(page.getByRole('region', { name: '當次比賽級數安排' })).toBeVisible()
  }
  await choose()
  const area = page.getByRole('region', { name: '當次比賽級數安排' })
  const card = (i: number) => area.locator(`.level-name-card[data-registration-id="${rows[i].id}"]`)
  const read = async (i: number) => (await (await page.request.get(`/api/admin/competitions/${comp.id}`)).json()).registrations.find((r: Row) => r.id === rows[i].id)
  const history = async () => (await (await page.request.get(`/api/admin/competitions/${comp.id}/history`)).json()).filter((r: { action: string }) => r.action === 'level')
  const keyboardMove = async (i: number, level: number) => {
    const button = card(i).getByRole('button', { name: '點選移動' })
    await button.focus(); await button.press('Enter')
    const target = area.getByRole('button', { name: `移到 ${level} 級`, exact: true })
    await target.focus(); await target.press('Enter')
  }
  return { comp, other, headers, payload, rows, area, card, read, history, choose, keyboardMove }
}

async function pointerDrag(page: Page, card: Locator, target: Locator, mobile: boolean, cancel = false, hold = true) {
  const handle = card.getByRole('button', { name: /^拖曳 / })
  await handle.scrollIntoViewIfNeeded()
  const from = (await handle.boundingBox())!
  const to = (await target.boundingBox())!
  const x = from.x + from.width / 2, y = from.y + from.height / 2
  const tx = to.x + to.width / 2, ty = to.y + to.height / 2
  if (mobile) {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    if (hold) await expect(page.locator('.level-drag-ghost')).toBeVisible()
    for (let step = 1; step <= 8; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + (tx - x) * step / 8, y: y + (ty - y) * step / 8 }] })
    await cdp.send('Input.dispatchTouchEvent', { type: cancel ? 'touchCancel' : 'touchEnd', touchPoints: [] })
    await cdp.detach()
  } else {
    await page.mouse.move(x, y); await page.mouse.down()
    await page.mouse.move(tx, ty, { steps: 12 })
    if (cancel) await page.keyboard.press('Escape')
    await page.mouse.up()
  }
}

test('姓名卡片滑鼠或長按觸控拖曳、自動儲存、反向撤回與鍵盤替代', async ({ page }, info) => {
  const s = await setup(page, info, 'drag')
  await expect(s.area.getByText('全場正取安排 3 人・候補 1 人・取消 1 人')).toBeVisible()
  await expect(s.card(0).getByRole('button', { name: /^拖曳 / })).toBeDisabled()
  await expect(s.area.getByText(/請先填寫原因/)).toBeVisible()
  await s.area.getByLabel('本次調整原因（必填）').fill('合成逐次安排')
  await page.evaluate(() => { (window as unknown as { touches: string[] }).touches = []; window.addEventListener('pointerdown', e => { (window as unknown as { touches: string[] }).touches.push(`${e.pointerType}:${e.isTrusted}`) }) })
  const mobile = info.project.name === 'mobile'
  const target5 = s.area.getByRole('button', { name: '移到 5 級', exact: true })
  if (mobile) {
    // Moving before long-press activation must cancel, without a write.
    await pointerDrag(page, s.card(0), target5, true, false, false)
    expect((await s.read(0)).version).toBe(1)
    // Native swipe from the name, outside the handle, still scrolls the page.
    const name = s.card(0).locator('.level-card-name')
    await name.scrollIntoViewIfNeeded()
    const box = (await name.boundingBox())!
    const startY = await page.evaluate(() => scrollY)
    const cdp = await page.context().newCDPSession(page)
    const x = box.x + box.width / 2, y = box.y + box.height / 2
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let step = 1; step <= 6; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - step * 25 }] })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await cdp.detach()
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(startY)
    expect((await s.read(0)).version).toBe(1)
  }
  await pointerDrag(page, s.card(0), target5, mobile)
  await expect.poll(async () => (await s.read(0)).competition_level).toBe(5)
  await expect(s.card(0)).toContainText('當次級數 5 級')
  await expect(s.card(0)).toContainText('報名快照 2 級')
  expect(await page.evaluate(() => (window as unknown as { touches: string[] }).touches)).toContain(`${mobile ? 'touch' : 'mouse'}:true`)
  await s.keyboardMove(0, 6)
  await expect.poll(async () => (await s.read(0)).version).toBe(3)
  await expect(s.card(0)).toContainText('當次級數 6 級')
  await s.area.getByLabel('本次調整原因（必填）').fill('合成撤回原因')
  await s.card(0).getByRole('button', { name: '撤回到 5 級', exact: true }).click()
  await expect.poll(async () => (await s.read(0)).version).toBe(4)
  await expect(s.card(0)).toContainText('當次級數 5 級')
  await pointerDrag(page, s.card(0), s.area.getByRole('button', { name: '移到 7 級', exact: true }), mobile, true)
  expect((await s.read(0)).version).toBe(4)
  await s.keyboardMove(0, 5)
  expect((await s.read(0)).version).toBe(4)
  const history = await s.history()
  expect(history.map((r: { changes: { competition_level: { before: number; after: number } } }) => r.changes.competition_level)).toEqual([{ before: 6, after: 5 }, { before: 5, after: 6 }, { before: 2, after: 5 }])
  expect(history[0].reason).toBe('合成撤回原因')
  expect(history[0].actor_name).toBe('e2e-levels-admin')
  await s.area.getByLabel('安排搜尋姓名／辨識註記').fill('卡片辨識0')
  await s.area.getByLabel('當次級數篩選').selectOption('5')
  await expect(s.area.getByText('篩選正取 1／全場正取 3 人')).toBeVisible()
  await expect(s.area.getByRole('region', { name: '當次 5 級正取' })).toContainText('篩選 1／安排 1 人')
  await s.area.getByLabel('當次級數篩選').selectOption('2')
  await expect(s.area.getByText('篩選正取 0／全場正取 3 人')).toBeVisible()
  const other = await (await page.request.get(`/api/admin/competitions/${s.other.id}`)).json()
  expect(other.registrations[0].competition_level).toBe(2)
  const member = (await (await page.request.get('/api/admin/members')).json()).find((m: { id: string }) => m.id === s.rows[0].member_id)
  expect(member.level).toBe(2)
  await page.reload(); await s.choose()
  await expect(s.card(0)).toContainText('當次級數 5 級')
  expect((await s.read(0)).hard_level_snapshot).toBe(2)
  await s.area.locator('.level-excluded').first().locator('summary').click()
  await expect(s.area.locator('.level-excluded').getByRole('button')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await s.area.screenshot({ path: info.outputPath('cards-saved.png') })
})

test('自動保存未知結果凍結原操作、其他卡片獨立與canonical重試', async ({ page }, info) => {
  const s = await setup(page, info, 'retry')
  await s.area.getByLabel('本次調整原因（必填）').fill('原始原因不可偷換')
  const url = `/api/admin/registrations/${s.rows[0].id}/level`
  const sent: Record<string, unknown>[] = []
  let first = true
  await page.route(`**${url}`, async route => {
    sent.push(route.request().postDataJSON())
    if (first) {
      first = false
      const committed = await route.fetch()
      expect(committed.status()).toBe(200)
      // The DB committed, but the client cannot know whether the response was lost.
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成回應中斷' }) })
    } else await route.continue()
  })
  await s.keyboardMove(0, 7)
  const pending = s.area.locator(`[data-pending-id="${s.rows[0].id}"]`)
  await expect(pending.getByRole('alert')).toContainText('合成回應中斷')
  await expect(s.card(0).getByRole('button', { name: '點選移動' })).toBeDisabled()
  await expect(pending.getByRole('button', { name: /放棄/ })).toHaveCount(0)
  await s.area.getByLabel('本次調整原因（必填）').fill('新的其他卡原因')
  await s.keyboardMove(1, 4)
  await expect.poll(async () => (await s.read(1)).competition_level).toBe(4)
  await expect(pending).toContainText('原始原因不可偷換')
  const newer = await page.request.put(url, { headers: s.headers, data: { version: 2, competition_level: 8, reason: '另一個操作', request_id: crypto.randomUUID() } })
  expect(newer.status()).toBe(200)
  await pending.getByRole('button', { name: '確認結果／原樣重試' }).click()
  await expect(pending).toHaveCount(0)
  await expect(s.card(0)).toContainText('當次級數 8 級')
  await expect(s.area.getByText(/最新紀錄已變更。目前 8 級／版本 3/)).toBeVisible()
  await expect(s.card(0).getByRole('button', { name: /撤回到/ })).toHaveCount(0)
  expect(sent).toHaveLength(2)
  expect(sent[1]).toEqual(sent[0])
  expect(sent[1].version).toBe(1)
  expect((await s.history()).filter((r: { registration_id: string }) => r.registration_id === s.rows[0].id)).toHaveLength(2)
  // Failure before a commit: a retry must keep the same key and version too.
  const thirdUrl = `/api/admin/registrations/${s.rows[2].id}/level`
  const failed: Record<string, unknown>[] = []
  await page.route(`**${thirdUrl}`, async route => {
    failed.push(route.request().postDataJSON())
    if (failed.length === 1) await route.abort('failed')
    else await route.continue()
  })
  await s.keyboardMove(2, 9)
  const thirdPending = s.area.locator(`[data-pending-id="${s.rows[2].id}"]`)
  await expect(thirdPending.getByRole('button', { name: '確認結果／原樣重試' })).toBeVisible()
  await s.choose(true); await s.choose()
  await expect(thirdPending).toContainText('4 → 9 級／原版本 1')
  await expect(s.area.getByLabel('本次調整原因（必填）')).toHaveValue('新的其他卡原因')
  await thirdPending.screenshot({ path: info.outputPath('cards-unknown.png') })
  await thirdPending.getByRole('button', { name: '確認結果／原樣重試' }).click()
  await expect(thirdPending).toHaveCount(0)
  expect(failed).toHaveLength(2)
  expect(failed[1]).toEqual(failed[0])
  await expect.poll(async () => (await s.read(2)).version).toBe(2)
})

test('真實409保留移動、切場遲回應不跳場與終態唯讀', async ({ page }, info) => {
  const s = await setup(page, info, 'race')
  await s.area.getByLabel('本次調整原因（必填）').fill('版本測試原因')
  expect((await page.request.put(`/api/admin/registrations/${s.rows[0].id}/level`, { headers: s.headers, data: { version: 1, competition_level: 9, reason: '先更新', request_id: crypto.randomUUID() } })).status()).toBe(200)
  await s.keyboardMove(0, 6)
  const conflict = s.area.locator(`[data-pending-id="${s.rows[0].id}"]`)
  await expect(conflict.getByRole('alert')).toContainText('其他管理員更新')
  await expect(conflict).toContainText('2 → 6 級／原版本 1')
  await expect(conflict.getByRole('button', { name: '確認結果／原樣重試' })).toHaveCount(0)
  await conflict.getByRole('button', { name: '讀取最新名單（保留未完成移動）' }).click()
  await expect(conflict).toContainText('最新讀取：9 級／版本 2')
  await s.choose(true); await s.choose()
  await expect(conflict).toContainText('原版本 1')
  await conflict.getByRole('button', { name: '放棄未完成移動並讀取最新名單' }).click()
  await expect(conflict).toHaveCount(0)
  await expect(s.card(0)).toContainText('當次級數 9 級')
  const url = `/api/admin/registrations/${s.rows[1].id}/level`
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let committed = false
  await page.route(`**${url}`, async route => {
    const response = await route.fetch(); committed = true
    await gate
    await route.fulfill({ response })
  })
  try {
    await s.keyboardMove(1, 7)
    await expect.poll(() => committed).toBe(true)
    await expect(s.card(1).getByRole('button', { name: '點選移動' })).toBeDisabled()
    await s.choose(true)
    expect((await page.request.put(url, { headers: s.headers, data: { version: 2, competition_level: 8, reason: '晚於第一次存檔', request_id: crypto.randomUUID() } })).status()).toBe(200)
    release()
    await expect(page.getByLabel('名稱', { exact: true })).toHaveValue(s.other.name)
    await s.choose()
    await expect(s.card(1)).toContainText('當次級數 8 級')
    await expect(s.card(1).getByRole('button', { name: /撤回到/ })).toHaveCount(0)
  } finally { release() }
  expect((await page.request.put(`/api/admin/competitions/${s.comp.id}`, { headers: s.headers, data: { ...s.payload, status: 'ended', version: 2 } })).status()).toBe(200)
  await page.reload(); await s.choose()
  await expect(s.area.getByText('此場次為唯讀，不能調整當次級數。')).toBeVisible()
  await expect(s.area.getByRole('button', { name: /^拖曳 |點選移動/ })).toHaveCount(0)
  await expect(s.area.getByLabel('本次調整原因（必填）')).toHaveCount(0)
  await expect(s.area.getByRole('button', { name: '移到 5 級', exact: true })).toBeDisabled()
})

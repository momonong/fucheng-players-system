import { test, expect, type Page } from '@playwright/test'
const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => prefix + path

async function fixture(page: Page, mode = 'individual') {
  const login = await page.request.post(url('/api/auth/login'), { data: { username: 'e2e-admin', password: process.env.FUCHENG_E2E_ADMIN_PASSWORD } })
  expect(login.status()).toBe(200)
  const headers = { 'X-CSRF-Token': (await login.json()).csrf_token }
  const response = await page.request.post(url('/api/admin/competitions'), { headers, data: {
    name: `同步測試-${crypto.randomUUID()}`, competition_date: '2099-12-20', registration_deadline: '2099-12-19T00:00:00+08:00', capacity: 1, status: 'open', registration_mode: mode,
  } })
  expect(response.status()).toBe(201)
  const competition = await response.json()
  const members = []
  for (const note of ['老師', '學生']) {
    const member = await page.request.post(url('/api/admin/members'), { headers, data: { name: `效能陳先生${competition.id.slice(0,4)}`, distinguishing_note: note, level: 5, diet: 'unset', is_active: true } })
    expect(member.status()).toBe(201); members.push(await member.json())
  }
  return { headers, competition, members }
}

test('公開切頁不重載、會員搜尋不發請求、返回與hash仍正常', async ({ page }) => {
  let documents = 0, membersRequests = 0
  page.on('request', request => {
    if (request.resourceType() === 'document') documents++
    if (new URL(request.url()).pathname === url('/api/public/members')) membersRequests++
  })
  await page.goto(url('/'))
  await expect(page.getByRole('heading', { name: '最新公告', exact: true })).toBeVisible()
  await page.evaluate(() => { (window as any).__documentIdentity = 'same-document' })
  await page.getByRole('link', { name: '會員分級表', exact: true }).click()
  await expect(page.locator('.level-member-list')).not.toHaveCount(0)
  expect(documents).toBe(1)
  expect(await page.evaluate(() => (window as any).__documentIdentity)).toBe('same-document')
  expect(membersRequests).toBe(1)
  await page.getByLabel('搜尋姓名或辨識註記').fill('東區')
  await expect(page.locator('.level-member-list')).toContainText(['東區'])
  await page.getByRole('combobox', { name: '級數', exact: true }).selectOption('2')
  await expect(page.locator('.level-card h2')).toHaveText(['2 級'])
  await page.waitForTimeout(400)
  expect(membersRequests).toBe(1)
  await page.getByRole('link', { name: '使用說明', exact: true }).click()
  await page.getByRole('link', { name: '管理員操作 ↓' }).click()
  await expect(page).toHaveURL(new RegExp('/help#admins-help$'))
  await page.goBack()
  await page.goBack()
  await expect(page).toHaveURL(new RegExp('/members$'))
  expect(documents).toBe(1)
  await page.getByLabel('更多選項').click()
  await page.getByRole('link', { name: '管理後台', exact: true }).click()
  await expect(page.getByLabel('帳號', { exact: true })).toBeVisible()
  expect(documents).toBe(2)
})

test('內容hash資產可重用，HTML與API保持no-store', async ({ page }) => {
  const response = await page.goto(url('/help'))
  expect(response?.headers()['cache-control']).toBe('no-store')
  const javascript = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('.js'))
  await page.reload()
  const asset = await javascript
  expect(asset.headers()['cache-control']).toBe('public, max-age=31536000, immutable')
  await expect(page.locator('.help-step img').first()).toBeVisible()
  const api = await page.request.get(url('/api/public/members'))
  expect(api.headers()['cache-control']).toBe('no-store')
  const transferSizes = await page.evaluate(() => performance.getEntriesByType('resource').filter(e => e.name.endsWith('.js')).map(e => (e as PerformanceResourceTiming).transferSize))
  expect(transferSizes.length).toBeGreaterThan(0)
  expect(transferSizes.every(size => size === 0)).toBe(true)
})

test('其他人報名、取消、截止在五秒同步週期內讀回', async ({ page, browser }, info) => {
  const { headers, competition, members } = await fixture(page)
  const context = await browser.newContext({ baseURL: info.project.use.baseURL })
  const viewer = await context.newPage()
  try {
    await viewer.goto(url(`/register/${competition.id}`))
    const confirmed = viewer.getByRole('region', { name: '正取名單', exact: true })
    const waiting = viewer.getByRole('region', { name: '候補名單', exact: true })
    await expect(confirmed).toContainText('目前沒有正取會員')
    const register = async (memberId: string) => {
      const response = await page.request.post(url(`/api/admin/competitions/${competition.id}/registrations`), { headers, data: { member_id: memberId, request_id: crypto.randomUUID() } })
      expect(response.status()).toBe(201); return response.json()
    }
    const first = await register(members[0].id)
    await expect(confirmed).toContainText('老師', { timeout: 7500 })
    await register(members[1].id)
    await expect(waiting).toContainText('學生', { timeout: 7500 })
    const cancel = await page.request.post(url(`/api/admin/registrations/${first.id}/cancel`), { headers, data: { version: first.version, request_id: crypto.randomUUID(), reason: '合成同步測試' } })
    expect(cancel.status()).toBe(200)
    await expect(confirmed).not.toContainText('老師', { timeout: 7500 })
    const close = await page.request.put(url(`/api/admin/competitions/${competition.id}`), { headers, data: { ...competition, status: 'closed' } })
    expect(close.status()).toBe(200)
    await expect(viewer.getByLabel('搜尋姓名', { exact: true })).toHaveCount(0, { timeout: 7500 })
  } finally { await context.close() }
})

test('成功報名強制新讀取，晚到的舊名單不能覆蓋成功結果', async ({ page, browser }, info) => {
  const { competition, members } = await fixture(page)
  const context = await browser.newContext({ baseURL: info.project.use.baseURL })
  const visitor = await context.newPage()
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  try {
    await visitor.goto(url(`/register/${competition.id}`))
    const roster = visitor.getByRole('region', { name: '正取名單', exact: true })
    await expect(roster).toContainText('目前沒有正取會員')
    let started!: () => void
    const ready = new Promise<void>(resolve => { started = resolve })
    let intercepted = false, posts = 0
    visitor.on('request', r => { if (r.method() === 'POST' && r.url().includes('/registrations')) posts++ })
    await visitor.route('**' + url(`/api/public/competitions/${competition.id}/registrations`), async route => {
      if (route.request().method() !== 'GET' || intercepted) { await route.continue(); return }
      intercepted = true
      const original = await route.fetch()
      const old = await original.json()
      started(); await held
      await route.fulfill({ response: original, json: old })
    })
    await visitor.getByRole('button', { name: '更新名單', exact: true }).click()
    await ready
    await visitor.getByLabel('搜尋姓名', { exact: true }).fill(members[0].name)
    await visitor.locator('.public-candidates button').filter({ hasText: '老師' }).click()
    await visitor.getByRole('button', { name: `確認以 ${members[0].name} 報名`, exact: true }).click()
    await expect(visitor.getByRole('region', { name: '報名結果', exact: true }).getByRole('status')).toBeVisible()
    await expect(roster).toContainText('老師')
    release()
    await visitor.waitForTimeout(300)
    await expect(roster).toContainText('老師')
    expect(posts).toBe(1)
  } finally { release(); await context.close() }
})

test('背景名單不輪詢，切回視窗立即讀回更新', async ({ page, browser }, info) => {
  const { headers, competition, members } = await fixture(page)
  const context = await browser.newContext({ baseURL: info.project.use.baseURL })
  const viewer = await context.newPage()
  try {
    let reads = 0
    viewer.on('request', r => { if (r.method() === 'GET' && r.url().includes(`/${competition.id}/registrations`)) reads++ })
    await viewer.goto(url(`/register/${competition.id}`))
    await expect(viewer.getByRole('region', { name: '正取名單', exact: true })).toContainText('目前沒有正取會員')
    await viewer.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }); document.dispatchEvent(new Event('visibilitychange')) })
    const before = reads
    const registered = await page.request.post(url(`/api/admin/competitions/${competition.id}/registrations`), { headers, data: { member_id: members[0].id, request_id: crypto.randomUUID() } })
    expect(registered.status()).toBe(201)
    await viewer.waitForTimeout(5300)
    expect(reads).toBe(before)
    await viewer.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus')) })
    await expect(viewer.getByRole('region', { name: '正取名單', exact: true })).toContainText('老師', { timeout: 2000 })
    expect(reads).toBe(before + 1)
  } finally { await context.close() }
})

test('雙打隊伍審核由另一個頁面自動同步', async ({ page, browser }, info) => {
  const { headers, competition, members } = await fixture(page, 'doubles')
  const context = await browser.newContext({ baseURL: info.project.use.baseURL })
  const viewer = await context.newPage()
  try {
    await viewer.goto(url(`/register/${competition.id}`))
    const section = (title: string) => viewer.locator('.doubles-section').filter({ has: viewer.getByRole('heading', { name: new RegExp('^' + title) }) })
    await expect(section('待管理員確認')).toBeVisible()
    const response = await page.request.post(url(`/api/admin/competitions/${competition.id}/doubles`), { headers, data: { member_ids: members.map(m => m.id), request_id: crypto.randomUUID() } })
    expect(response.status()).toBe(201)
    const entry = await response.json()
    await expect(section('待管理員確認')).toContainText('老師', { timeout: 7500 })
    const accept = await page.request.post(url(`/api/admin/doubles/${entry.id}/approve`), { headers, data: { version: entry.version, request_id: crypto.randomUUID() } })
    expect(accept.status()).toBe(200)
    await expect(section('正取')).toContainText('老師', { timeout: 7500 })
    await expect(section('待管理員確認')).not.toContainText('老師')
  } finally { await context.close() }
})

test('比賽清單舊讀取不能覆蓋focus後的新狀態', async ({ page, browser }, info) => {
  const { headers, competition } = await fixture(page)
  const context = await browser.newContext({ baseURL: info.project.use.baseURL })
  const viewer = await context.newPage()
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  try {
    await viewer.goto(url('/competitions'))
    const card = viewer.locator('.public-competitions article').filter({ has: viewer.getByRole('heading', { name: competition.name, exact: true }) })
    await expect(card).toContainText('報名／查看名單')
    let started!: () => void, once = false
    const ready = new Promise<void>(resolve => { started = resolve })
    await viewer.route('**' + url('/api/public/registration-rosters'), async route => {
      if (once) { await route.continue(); return }; once = true
      const original = await route.fetch(); const old = await original.json(); started(); await held
      await route.fulfill({ response: original, json: old })
    })
    await ready
    const close = await page.request.put(url(`/api/admin/competitions/${competition.id}`), { headers, data: { ...competition, status: 'closed' } })
    expect(close.status()).toBe(200)
    await viewer.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(card.getByRole('link', { name: `查看名單：${competition.name}`, exact: true })).toBeVisible()
    release(); await viewer.waitForTimeout(300)
    await expect(card.getByRole('link', { name: `查看名單：${competition.name}`, exact: true })).toBeVisible()
  } finally { release(); await context.close() }
})

for (const mode of ['individual', 'doubles']) {
  test(`${mode} 寫入結果未知時，舊背景404不得移除原樣重試入口`, async ({ page, browser }, info) => {
    const { competition, members } = await fixture(page, mode)
    const context = await browser.newContext({ baseURL: info.project.use.baseURL })
    const visitor = await context.newPage()
    const endpoint = url(`/api/public/competitions/${competition.id}/${mode === 'individual' ? 'registrations' : 'doubles'}`)
    let release!: () => void
    const held = new Promise<void>(resolve => { release = resolve })
    try {
      await visitor.goto(url(`/register/${competition.id}`))
      if (mode === 'doubles') await visitor.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
      await visitor.getByLabel('搜尋姓名', { exact: true }).fill(members[0].name)
      await visitor.locator('.public-candidates button').filter({ hasText: '老師' }).click()
      let started!: () => void, firstRead = false
      const ready = new Promise<void>(resolve => { started = resolve })
      const payloads: string[] = []
      await visitor.route('**' + endpoint, async route => {
        if (route.request().method() === 'POST') {
          payloads.push(route.request().postData()!)
          if (payloads.length === 1) { await route.abort('failed'); return }
          await route.continue(); return
        }
        if (!firstRead) { firstRead = true; started(); await held; await route.fulfill({ status: 404, json: { detail: '合成舊讀取404' } }); return }
        await route.continue()
      })
      await ready
      const submit = mode === 'individual' ? visitor.getByRole('button', { name: `確認以 ${members[0].name} 報名`, exact: true }) : visitor.getByRole('button', { name: '確認送出單人登記', exact: true })
      await submit.click()
      if (mode === 'doubles') await expect(visitor.getByRole('button', { name: '原樣重試並核對結果' })).toBeVisible()
      else await expect(visitor.getByRole('alert')).toContainText('連線')
      release(); await visitor.waitForTimeout(300)
      if (mode === 'doubles') await visitor.getByRole('button', { name: '原樣重試並核對結果' }).click()
      else await submit.click()
      await expect.poll(() => payloads.length).toBe(2)
      expect(payloads[1]).toBe(payloads[0])
      await expect(visitor.getByRole('status').filter({ hasText: mode === 'doubles' ? '已送出單人登記' : '報名完成' })).toBeVisible()
    } finally { release(); await context.close() }
  })
}

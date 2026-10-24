import { expect, test, type Page } from '@playwright/test'
const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => prefix + path
test.setTimeout(90_000)
test.use({ actionTimeout: 10_000 })
async function login(page: Page) {
  await page.goto(url('/admin/competitions'))
  await page.getByLabel('帳號', { exact: true }).fill(`e2e-grid-${test.info().project.name}`)
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.locator('input[type=password]').evaluateAll(inputs => inputs.forEach(input => { (input as HTMLInputElement).value = '' }))
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible()
  return (await (await page.request.get(url('/api/auth/me'))).json()).csrf_token as string
}
async function choose(page: Page, label: string, query: string, note?: string) {
  const picker = page.getByRole('group', { name: label, exact: true })
  await picker.getByLabel('搜尋姓名', { exact: true }).fill(query)
  await picker.getByRole('button', { name: note ? `${query} ${note}` : new RegExp(query), exact: !!note }).click()
}

test('雙打公開單人承接、直接雙人審核、取消拆隊候補及截止名單', async ({ page, browser }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const csrf = await login(page)
  await page.getByRole('button', { name: '報名與設定', exact: true }).click()
  const list = page.locator('.competition-list')
  if (await list.getAttribute('open') === null) await list.locator('summary').first().click()
  await page.getByRole('button', { name: '建立比賽', exact: true }).click()
  await page.getByRole('combobox', { name: '報名模式', exact: true }).selectOption('doubles')
  await page.getByLabel('名稱', { exact: true }).fill(`雙打合成-${info.project.name}-${prefix ? 'prefix' : 'root'}`)
  await page.getByLabel('比賽日期', { exact: true }).fill('2099-10-25')
  await page.getByLabel('隊數上限', { exact: true }).fill('1')
  await page.getByLabel('報名截止時間（台北時間）', { exact: true }).fill('2099-10-24T18:00')
  await page.getByRole('combobox', { name: '狀態', exact: true }).selectOption('open')
  await page.getByRole('button', { name: '儲存比賽', exact: true }).click()
  await expect(page.getByRole('region', { name: '雙打報名管理' })).toBeVisible()
  const id = await page.getByLabel('選擇比賽', { exact: true }).inputValue()
  const endpoint = url(`/api/admin/competitions/${id}/doubles`)
  const get = async () => (await page.request.get(endpoint)).json()
  const contexts = await Promise.all([browser.newContext(info.project.use), browser.newContext(info.project.use)])
  const [a, b] = await Promise.all(contexts.map(context => context.newPage()))
  a.on('pageerror', error => errors.push(error.message)); b.on('pageerror', error => errors.push(error.message))
  try {
    await a.goto(url(`/register/${id}`))
    await a.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
    await choose(a, '報名會員', '合成會員一')
    await a.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(a.getByRole('status')).toContainText('等待搭檔')
    await expect(a.locator('.doubles-section').filter({ has: a.getByRole('heading', { name: /^等待搭檔/ }) })).toContainText('合成會員一')
    await b.goto(url(`/register/${id}`))
    await b.getByRole('button', { name: '和 合成會員一 組隊', exact: true }).click()
    await choose(b, '第二位會員', '合成會員二')
    await expect(b.locator('.doubles-confirm')).toContainText('東區')
    await expect(b.locator('.doubles-confirm')).toContainText('西區')
    await b.screenshot({ path: info.outputPath('public-pair-confirmation.png'), fullPage: true })
    await b.locator('.registration-form').screenshot({ path: info.outputPath('public-pair-focused.png') })
    await b.getByRole('button', { name: '確認送出兩人組隊', exact: true }).click()
    await expect(b.getByRole('status')).toContainText('待管理員確認')
    await expect(b.locator('.doubles-section').filter({ has: b.getByRole('heading', { name: /^等待搭檔/ }) }).locator('.doubles-entry')).toHaveCount(0)
    await page.getByRole('button', { name: '更新雙打名單', exact: true }).click()
    const admin = page.getByRole('region', { name: '雙打報名管理' })
    const first = admin.locator('.doubles-entry').filter({ hasText: '合成會員一' }).filter({ has: page.getByRole('button', { name: '接受報名', exact: true }) })
    await expect(first).toContainText('低於門檻')
    await first.getByRole('button', { name: '接受報名', exact: true }).click()
    await expect(admin.locator('.doubles-section').filter({ has: page.getByRole('heading', { name: /^正取/ }) })).toContainText('合成會員二')
    await expect(page.locator('.competition-item.selected')).toContainText('正取 1/1 隊・候補 0 隊')
    await b.reload(); await expect(b.locator('.doubles-section').filter({ has: b.getByRole('heading', { name: /^正取/ }) })).toContainText('合成會員一')
    const current = await get()
    const ruleUpdate = await page.request.put(url(`/api/admin/competitions/${id}`), { headers: { 'X-CSRF-Token': csrf }, data: { version: current.competition.version, name: current.competition.name, competition_date: '2099-10-25', registration_deadline: '2099-10-24T18:00:00+08:00', capacity: 1, status: 'open', doubles_min_total_level: 20 } })
    expect(ruleUpdate.ok()).toBe(true)
    await b.getByRole('button', { name: '我們兩人一起報名', exact: true }).click()
    await choose(b, '第一位會員', '合成同名', '東區')
    await choose(b, '第二位會員', '合成同名', '西區')
    await b.getByRole('button', { name: '確認送出兩人組隊', exact: true }).click()
    await expect(b.getByRole('status')).toContainText('待管理員確認')
    await page.getByRole('button', { name: '更新雙打名單', exact: true }).click()
    await expect(admin.locator('.doubles-entry').filter({ hasText: '合成同名' })).toContainText('低於門檻')
    await admin.locator('.doubles-entry').filter({ hasText: '合成同名' }).getByRole('button', { name: '接受報名', exact: true }).click()
    await expect(admin.locator('.doubles-section').filter({ has: page.getByRole('heading', { name: /^候補/ }) })).toContainText('合成同名')
    await expect(page.locator('.competition-item.selected')).toContainText('正取 1/1 隊・候補 1 隊')
    if (await page.locator('.toast-close').isVisible()) await page.locator('.toast-close').click()
    await page.screenshot({ path: info.outputPath('admin-teams-confirmed-waitlisted.png'), fullPage: true })
    await admin.screenshot({ path: info.outputPath('admin-teams-focused.png') })
    const confirmed = admin.locator('.doubles-section').filter({ has: page.getByRole('heading', { name: /^正取/ }) }).locator('.doubles-entry')
    await confirmed.getByRole('button', { name: '取消登記', exact: true }).click()
    await page.getByRole('dialog', { name: '取消登記' }).getByLabel('操作原因').fill('合成取消驗證')
    await page.getByRole('dialog', { name: '取消登記' }).getByRole('button', { name: '確認取消登記', exact: true }).click()
    await admin.getByRole('button', { name: '確認遞補', exact: true }).click()
    await admin.getByRole('button', { name: '拆回等待搭檔', exact: true }).click()
    await page.getByRole('dialog', { name: '拆回等待搭檔' }).getByLabel('操作原因').fill('合成拆隊驗證')
    await page.getByRole('dialog', { name: '拆回等待搭檔' }).getByRole('button', { name: '確認拆回等待搭檔', exact: true }).click()
    await expect(admin.locator('.doubles-section').filter({ has: page.getByRole('heading', { name: /^等待搭檔/ }) }).locator('.doubles-entry')).toHaveCount(2)
    await expect(admin).toContainText('已取消 3 筆')
    await page.screenshot({ path: info.outputPath('admin-doubles.png'), fullPage: true })
    const data = await get()
    const close = await page.request.put(url(`/api/admin/competitions/${id}`), { headers: { 'X-CSRF-Token': csrf }, data: { version: data.competition.version, status: 'closed', name: data.competition.name, competition_date: '2099-10-25', registration_deadline: '2099-10-24T18:00:00+08:00', capacity: 1 } })
    expect(close.ok()).toBe(true)
    await b.reload()
    await expect(b.getByText('報名已截止，仍可查看名單。', { exact: true })).toBeVisible()
    await expect(b.getByRole('button', { name: '我們兩人一起報名', exact: true })).toHaveCount(0)
    await b.screenshot({ path: info.outputPath('public-doubles.png'), fullPage: true })
    await b.goto(url('/'))
    await expect(b.getByRole('link', { name: `查看雙打名單：${data.competition.name}`, exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await b.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(errors).toEqual([])
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

async function createDoubles(page: Page, name: string) {
  const csrf = await login(page)
  const response = await page.request.post(url('/api/admin/competitions'), { headers: { 'X-CSRF-Token': csrf }, data: { name, competition_date: '2099-11-01', registration_deadline: '2099-10-31T18:00:00+08:00', capacity: 2, status: 'open', registration_mode: 'doubles' } })
  expect(response.status()).toBe(201)
  return { competition: await response.json(), csrf }
}

test('公開衝突讀回只更新名單，保留兩位草稿且不假稱送出成功', async ({ page, browser }, info) => {
  const { competition, csrf } = await createDoubles(page, `衝突核對-${info.project.name}`)
  const members = await (await page.request.get(url('/api/admin/registration-members?search=合成會員'))).json()
  const existing = await page.request.post(url(`/api/admin/competitions/${competition.id}/doubles`), { headers: { 'X-CSRF-Token': csrf }, data: { member_ids: [members[0].id, members[1].id], request_id: crypto.randomUUID() } })
  expect(existing.status()).toBe(201)
  const context = await browser.newContext(info.project.use), visitor = await context.newPage()
  try {
    await visitor.goto(url(`/register/${competition.id}`))
    await visitor.getByRole('button', { name: '我們兩人一起報名', exact: true }).click()
    await choose(visitor, '第一位會員', members[0].name)
    await choose(visitor, '第二位會員', members[2].name)
    await visitor.getByRole('button', { name: '確認送出兩人組隊', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('名單已變更')
    await visitor.getByRole('button', { name: '重新讀取雙打名單', exact: true }).click()
    await expect(visitor.locator('.doubles-confirm')).toContainText(members[0].name)
    await expect(visitor.locator('.doubles-confirm')).toContainText(members[2].name)
    await expect(visitor.getByRole('status')).toHaveCount(0)
  } finally { await context.close() }
})

test('公開未知寫入以原key重試，成功receipt後讀回失敗只GET', async ({ page, browser }, info) => {
  const { competition } = await createDoubles(page, `未知核對-${info.project.name}`)
  const context = await browser.newContext(info.project.use), visitor = await context.newPage()
  const posts: string[] = []
  let rejectRead = false
  try {
    await visitor.goto(url(`/register/${competition.id}`))
    await visitor.route(`**/api/public/competitions/${competition.id}/doubles`, async route => {
      if (route.request().method() === 'POST') {
        posts.push(route.request().postData()!)
        if (posts.length === 1) { await route.fetch(); await route.abort('failed'); return }
        if (posts.length >= 2 && posts.length <= 4) { const status = [403, 429, 404][posts.length - 2]; await route.fulfill({ status, json: { detail: `合成恢復前置阻擋 ${status}` } }); return }
        rejectRead = true; await route.continue(); return
      }
      if (rejectRead) { rejectRead = false; await route.abort('failed'); return }
      await route.continue()
    })
    await visitor.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
    await choose(visitor, '報名會員', '合成會員一')
    await visitor.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true })).toBeVisible()
    await expect(visitor.getByRole('group', { name: '報名會員', exact: true }).getByLabel('搜尋姓名')).toBeDisabled()
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('原操作結果仍未知')
    for (let blocked = 0; blocked < 2; blocked++) {
      await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
      await expect(visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true })).toBeVisible()
      await expect(visitor.getByRole('group', { name: '報名會員', exact: true }).getByLabel('搜尋姓名')).toBeDisabled()
    }
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('button', { name: '重新讀取雙打名單', exact: true })).toBeVisible()
    expect(posts).toHaveLength(5); for (const body of posts) expect(body).toBe(posts[0])
    await visitor.getByRole('button', { name: '重新讀取雙打名單', exact: true }).click()
    await expect(visitor.getByRole('status')).toContainText('等待搭檔')
    expect(posts).toHaveLength(5)
    const roster = await (await page.request.get(url(`/api/admin/competitions/${competition.id}/doubles`))).json()
    expect(roster.entries).toHaveLength(1)
  } finally { await context.close() }
})

test('公開挑戰重驗只換安全token，原key與會員payload不變', async ({ page, browser }, info) => {
  const { competition } = await createDoubles(page, `挑戰核對-${info.project.name}`)
  const context = await browser.newContext(info.project.use), visitor = await context.newPage()
  const posts: any[] = []
  await visitor.addInitScript(() => {
    let count = 0, callback: ((token: string) => void) | null = null
    ;(window as any).turnstile = {
      render: (_: HTMLElement, options: any) => { callback = options.callback; queueMicrotask(() => callback?.(`synthetic-token-${++count}`)); return 'synthetic-widget' },
      reset: () => queueMicrotask(() => callback?.(`synthetic-token-${++count}`)), remove: () => {},
    }
  })
  await visitor.route('https://challenges.cloudflare.com/**', route => route.fulfill({ status: 200, body: '' }))
  await visitor.route('**/api/public/registration-session', async route => { const response = await route.fetch(); await route.fulfill({ response, json: { ...await response.json(), turnstile_sitekey: 'synthetic-sitekey' } }) })
  try {
    await visitor.goto(url(`/register/${competition.id}`))
    await visitor.route(`**/api/public/competitions/${competition.id}/doubles`, async route => {
      if (route.request().method() !== 'POST') { await route.continue(); return }
      posts.push(route.request().postDataJSON())
      if (posts.length === 1 || posts.length === 3) { await route.fulfill({ status: 422, json: { detail: '合成安全驗證失敗，請重試' } }); return }
      await route.continue()
    })
    await visitor.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
    await choose(visitor, '報名會員', '合成會員一')
    await visitor.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('安全驗證')
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('status')).toContainText('等待搭檔')
    expect(posts).toHaveLength(2)
    expect(posts[1].request_id).toBe(posts[0].request_id)
    expect(posts[1].member_ids).toEqual(posts[0].member_ids)
    expect(posts[1].turnstile_token).not.toBe(posts[0].turnstile_token)
    // A new, definitely rejected challenge must not turn a later business 409
    // into sticky transport uncertainty. The visitor can read and choose again.
    await visitor.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
    await choose(visitor, '報名會員', '合成會員一')
    await visitor.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('安全驗證')
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('button', { name: '重新讀取雙打名單', exact: true })).toBeVisible()
    await visitor.getByRole('button', { name: '重新讀取雙打名單', exact: true }).click()
    await expect(visitor.getByRole('group', { name: '報名會員', exact: true }).getByLabel('搜尋姓名')).toBeEnabled()
    await expect(visitor.getByRole('status')).toHaveCount(0)
    expect(posts[3].request_id).toBe(posts[2].request_id)
    await choose(visitor, '報名會員', '合成會員二')
    await visitor.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(visitor.getByRole('status')).toContainText('等待搭檔')
    expect(posts).toHaveLength(5)
    expect(posts[4].request_id).not.toBe(posts[3].request_id)
  } finally { await context.close() }
})

test('管理名單讀取中鎖住操作與切場，舊讀回不能覆蓋新寫入', async ({ page }, info) => {
  const { competition, csrf } = await createDoubles(page, `讀取鎖定-${info.project.name}`)
  const members = await (await page.request.get(url('/api/admin/registration-members?search=合成同名'))).json()
  await page.request.post(url(`/api/admin/competitions/${competition.id}/doubles`), { headers: { 'X-CSRF-Token': csrf }, data: { member_ids: members.map((member: any) => member.id), request_id: crypto.randomUUID() } })
  await page.reload(); await page.getByLabel('選擇比賽', { exact: true }).selectOption(competition.id)
  const admin = page.getByRole('region', { name: '雙打報名管理' })
  await expect(admin.getByRole('button', { name: '接受報名', exact: true })).toBeVisible()
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route(`**/api/admin/competitions/${competition.id}/doubles`, async route => {
    if (route.request().method() === 'GET') await held
    await route.continue()
  })
  await admin.getByRole('button', { name: '更新雙打名單', exact: true }).click()
  try {
    await expect(admin.getByRole('button', { name: '接受報名', exact: true })).toBeDisabled()
    await expect(page.getByLabel('選擇比賽', { exact: true })).toBeDisabled()
  } finally { release() }
  await expect(admin.getByRole('button', { name: '接受報名', exact: true })).toBeEnabled()
  await admin.getByRole('button', { name: '接受報名', exact: true }).click()
  await expect(admin.locator('.doubles-section').filter({ has: page.getByRole('heading', { name: /^正取/ }) })).toContainText('合成同名')
})


test('首次挑戰503後再遇403仍保留原key與更新後token直到成功', async ({ page, browser }, info) => {
  const { competition } = await createDoubles(page, `503恢復-${info.project.name}`)
  const context = await browser.newContext(info.project.use), visitor = await context.newPage()
  const posts: any[] = []
  await visitor.addInitScript(() => {
    let count = 0, callback: ((token: string) => void) | null = null
    ;(window as any).turnstile = {
      render: (_: HTMLElement, options: any) => { callback = options.callback; queueMicrotask(() => callback?.(`synthetic-token-${++count}`)); return 'synthetic-widget' },
      reset: () => queueMicrotask(() => callback?.(`synthetic-token-${++count}`)), remove: () => {},
    }
  })
  await visitor.route('https://challenges.cloudflare.com/**', route => route.fulfill({ status: 200, body: '' }))
  await visitor.route('**/api/public/registration-session', async route => { const response = await route.fetch(); await route.fulfill({ response, json: { ...await response.json(), turnstile_sitekey: 'synthetic-sitekey' } }) })
  try {
    await visitor.goto(url(`/register/${competition.id}`))
    await visitor.route(`**/api/public/competitions/${competition.id}/doubles`, async route => {
      if (route.request().method() !== 'POST') { await route.continue(); return }
      posts.push(route.request().postDataJSON())
      if (posts.length < 3) { const status = posts.length === 1 ? 503 : 403; await route.fulfill({ status, json: { detail: `合成安全驗證 ${status}` } }); return }
      await route.continue()
    })
    await visitor.getByRole('button', { name: '我先報名，等待搭檔', exact: true }).click()
    await choose(visitor, '報名會員', '合成會員一')
    await visitor.getByRole('button', { name: '確認送出單人登記', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('安全驗證')
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('alert')).toContainText('原操作結果仍未知')
    await visitor.getByRole('button', { name: '原樣重試並核對結果', exact: true }).click()
    await expect(visitor.getByRole('status')).toContainText('等待搭檔')
    expect(posts).toHaveLength(3)
    expect(posts[1].request_id).toBe(posts[0].request_id); expect(posts[2].request_id).toBe(posts[0].request_id)
    expect(posts[1].member_ids).toEqual(posts[0].member_ids); expect(posts[2].member_ids).toEqual(posts[0].member_ids)
    expect(posts[1].turnstile_token).not.toBe(posts[0].turnstile_token)
    expect(posts[2].turnstile_token).toBe(posts[1].turnstile_token)
    const roster = await (await page.request.get(url(`/api/admin/competitions/${competition.id}/doubles`))).json()
    expect(roster.entries).toHaveLength(1)
  } finally { await context.close() }
})

test('管理原因依entry與action保留，409讀回後須明確再次提交新version', async ({ page }, info) => {
  const { competition, csrf } = await createDoubles(page, `原因草稿-${info.project.name}`)
  const members = await (await page.request.get(url('/api/admin/registration-members?search=合成同名'))).json()
  const created = await page.request.post(url(`/api/admin/competitions/${competition.id}/doubles`), { headers: { 'X-CSRF-Token': csrf }, data: { member_ids: members.map((member: any) => member.id), request_id: crypto.randomUUID() } })
  const entry = await created.json()
  expect(created.status()).toBe(201)
  await page.reload(); await page.getByLabel('選擇比賽', { exact: true }).selectOption(competition.id)
  const admin = page.getByRole('region', { name: '雙打報名管理' })
  await admin.getByRole('button', { name: '取消登記', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '取消登記', exact: true })
  await dialog.getByLabel('操作原因').fill('合成取消原因草稿甲')
  const approved = await page.request.post(url(`/api/admin/doubles/${entry.id}/approve`), { headers: { 'X-CSRF-Token': csrf }, data: { version: entry.version, request_id: crypto.randomUUID() } })
  expect(approved.ok()).toBe(true)
  const current = (await approved.json()).entry
  const submitted: any[] = []
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith(`/api/admin/doubles/${entry.id}/cancel`)) submitted.push(request.postDataJSON()) })
  await dialog.getByRole('button', { name: '確認取消登記', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('名單已變更')
  await dialog.getByRole('button', { name: '重新讀取雙打名單', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(submitted).toHaveLength(1)
  await admin.getByRole('button', { name: '拆回等待搭檔', exact: true }).click()
  const splitDialog = page.getByRole('dialog', { name: '拆回等待搭檔', exact: true })
  await expect(splitDialog.getByLabel('操作原因')).toHaveValue('')
  await splitDialog.getByLabel('操作原因').fill('合成拆隊原因草稿乙')
  await splitDialog.getByRole('button', { name: '暫不操作', exact: true }).click()
  await admin.getByRole('button', { name: '取消登記', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '取消登記', exact: true })
  await expect(dialog.getByLabel('操作原因')).toHaveValue('合成取消原因草稿甲')
  expect(submitted).toHaveLength(1)
  await dialog.getByRole('button', { name: '確認取消登記', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(submitted).toHaveLength(2)
  expect(submitted[1].version).toBe(current.version)
  expect(submitted[1].reason).toBe('合成取消原因草稿甲')
  const history = await (await page.request.get(url(`/api/admin/competitions/${competition.id}/doubles/history`))).json()
  expect(history.filter((audit: any) => audit.action === 'cancel')).toHaveLength(1)
  expect(history.find((audit: any) => audit.action === 'cancel').reason).toBe('合成取消原因草稿甲')
})

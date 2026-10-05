import { expect, test, type Page } from '@playwright/test'

const base = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => `${base}${path}`

async function login(page: Page) {
  await page.goto(url('/admin/competitions'))
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible()
  const me = await (await page.request.get(url('/api/auth/me'))).json()
  return { 'X-CSRF-Token': me.csrf_token }
}

test('same build: deep links, public registration, arrangement and export stay within prefix', async ({ page, browser }, info) => {
  const escaped: string[] = []
  const inspect = (p: Page) => p.on('request', request => {
    const target = new URL(request.url())
    if (target.origin === new URL(info.project.use.baseURL!).origin && base && !target.pathname.startsWith(base + '/')) escaped.push(target.pathname)
  })
  inspect(page)
  const headers = await login(page)
  const name = `合成路徑賽-${info.project.name}`
  const created = await page.request.post(url('/api/admin/competitions'), { headers, data: {
    name, competition_date: '2099-10-03', registration_deadline: '2099-10-02T00:00:00+08:00', capacity: 8, status: 'open', notes: 'Synthetic path verification',
  } })
  expect(created.status()).toBe(201)
  const comp = await created.json()
  const visitorContext = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: info.project.use.viewport, isMobile: info.project.use.isMobile, hasTouch: info.project.use.hasTouch })
  const visitor = await visitorContext.newPage()
  inspect(visitor)
  try {
    await visitor.goto(url('/'))
    await visitor.getByRole('link', { name: '會員分級表', exact: true }).click()
    await expect(visitor).toHaveURL(new RegExp(`${base}/members$`))
    await visitor.reload()
    await expect(visitor.getByText('合成會員一', { exact: true })).toBeVisible()
    await visitor.getByRole('link', { name: '比賽報名', exact: true }).click()
    await visitor.getByRole('link', { name: `我要報名：${name}`, exact: true }).click()
    await visitor.reload()
    await visitor.getByLabel('搜尋姓名', { exact: true }).fill('合成會員一')
    await visitor.getByRole('button', { name: '合成會員一 東區', exact: true }).click()
    await visitor.getByRole('radio', { name: '素食', exact: true }).check()
    await visitor.getByRole('button', { name: '確認以 合成會員一 報名', exact: true }).click()
    await expect(visitor.getByRole('status')).toHaveText('報名完成')
    expect((await visitorContext.cookies()).find(cookie => cookie.name === 'fucheng_public_visit')?.path).toBe(base + '/')
    await visitor.getByRole('link', { name: '回比賽清單', exact: true }).click()
    await expect(visitor).toHaveURL(new RegExp(`${base}/competitions$`))

    await page.reload()
    await page.getByLabel('選擇比賽').selectOption(comp.id)
    await expect(page.locator('.arrangement-table')).toBeVisible()
    await expect(page.locator('.arrangement-table')).toContainText('合成會員一')
    await expect(page.getByRole('button', { name: '匯出 Excel', exact: true })).toBeEnabled()
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '匯出 Excel', exact: true }).click()])
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/)
    expect(await download.failure()).toBeNull()
    await page.getByRole('button', { name: '報名與設定', exact: true }).click()
    await page.getByRole('link', { name: '前往報名名單', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${base}/admin/competitions#registration-roster$`))
    const roster = info.project.name === 'mobile' ? page.locator('.mobile-registration-list') : page.getByRole('region', { name: '十級行政名單' })
    await expect(roster).toBeVisible()
    await expect(roster).toContainText('合成會員一')
    await page.locator('.admin-account').getByRole('link', { name: '會員分級表', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${base}/admin/roster$`))
    await page.goto(url('/admin/competitions'))
    await page.reload()
    await page.getByRole('button', { name: '登出', exact: true }).click()
    await expect(page.getByLabel('密碼', { exact: true })).toBeVisible()
    expect((await page.context().cookies()).filter(cookie => cookie.name === 'fucheng_session')).toHaveLength(0)
    expect(escaped).toEqual([])
  } finally {
    await visitorContext.close()
  }
})

test('same build: announcement editor and public inline images survive reload', async ({ page, browser }, info) => {
  await login(page)
  const title = `合成路徑公告-${info.project.name}`
  await page.getByRole('link', { name: '公告管理', exact: true }).click()
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  await page.getByLabel('公告標題').fill(title)
  await page.getByLabel('公告內容').fill('合成圖片與路徑測試')
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await page.getByRole('button', { name: '插入圖片', exact: true }).click()
  await page.getByLabel('選擇內文圖片').setInputFiles({ name: 'synthetic.png', mimeType: 'image/png', buffer: await page.screenshot() })
  const image = page.getByLabel('公告內容').locator('figure img')
  await expect(image).toHaveCount(1)
  expect(new URL(await image.getAttribute('src') ?? '', info.project.use.baseURL).pathname).toMatch(new RegExp(`^${base}/api/admin/announcement-media/`))
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  await page.getByLabel('發布到首頁').check()
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await page.reload()
  const visitorContext = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: info.project.use.viewport, isMobile: info.project.use.isMobile, hasTouch: info.project.use.hasTouch })
  const visitor = await visitorContext.newPage()
  try {
    await visitor.goto(url('/'))
    const card = visitor.locator('.news-card').filter({ has: visitor.getByRole('heading', { name: title, exact: true }) })
    const publicImage = card.locator('figure img')
    await expect(publicImage).toHaveCount(1)
    expect(new URL(await publicImage.getAttribute('src') ?? '', info.project.use.baseURL).pathname).toMatch(new RegExp(`^${base}/api/public/announcement-media/`))
    await expect.poll(() => publicImage.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
    await visitor.reload()
    await expect.poll(() => publicImage.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
    await visitor.screenshot({ path: info.outputPath('base-path-announcement.png'), fullPage: true })
  } finally {
    await visitorContext.close()
  }
})

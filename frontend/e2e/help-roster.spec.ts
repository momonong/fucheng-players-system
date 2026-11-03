import { expect, test } from '@playwright/test'
const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => prefix + path

test('公開使用說明、更多選單及所有截圖可閱讀', async ({ page }) => {
  await page.goto(url('/'))
  await expect(page.getByRole('link', { name: '使用說明', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '管理後台', exact: true })).toBeHidden()
  await page.getByLabel('更多選項').click()
  await expect(page.getByRole('link', { name: '管理後台', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('link', { name: '管理後台', exact: true })).toBeHidden()
  await expect(page.getByAltText('網站右上角的使用說明按鈕位置')).toBeVisible()
  await page.getByRole('link', { name: '使用說明', exact: true }).click()
  await expect(page.getByText('查名單、查看比賽與協助其他人報名。', { exact: true })).toBeVisible()
  await expect(page.locator('.help-step')).toHaveCount(10)
  for (const image of await page.locator('.help-step img').all()) {
    await image.scrollIntoViewIfNeeded()
    await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true)
  }
  await expect(page.getByRole('link', { name: '會員使用 ↓' })).toHaveAttribute('href', url('/help') + '#members-help')
  expect(await page.locator('main').innerText()).not.toMatch(/硬分級|硬實力/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
})

test('公開正候補名單、同名註記、截止後唯讀及手動更新', async ({ page }) => {
  await page.goto(url('/admin/competitions'))
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible()
  const auth = await (await page.request.get(url('/api/auth/me'))).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token }
  const create = await page.request.post(url('/api/admin/competitions'), { headers, data: {name:'名單示範', competition_date:'2099-12-20',registration_deadline:'2099-12-19T00:00:00+08:00',capacity:1,status:'open'} })
  expect(create.status()).toBe(201)
  const competition = await create.json()
  for (const note of ['老師', '學生']) {
    const member = await page.request.post(url('/api/admin/members'), { headers, data: { name:'陳先生',distinguishing_note:note,legacy_number:'',level:3,diet:'unset',is_active:true } })
    expect(member.status()).toBe(201)
    const registration = await page.request.post(url(`/api/admin/competitions/${competition.id}/registrations`), { headers, data: { member_id:(await member.json()).id,request_id:crypto.randomUUID() } })
    expect(registration.status()).toBe(201)
  }
  const closed = await page.request.put(url(`/api/admin/competitions/${competition.id}`), { headers, data: {...competition, status:'closed',version:competition.version} })
  expect(closed.status()).toBe(200)
  await page.request.post(url('/api/auth/logout'), { headers })
  await page.goto(url(`/register/${competition.id}`))
  const roster = page.getByRole('region', { name: '比賽報名名單', exact: true })
  await expect(roster.getByRole('region', { name: '正取名單', exact: true })).toContainText('老師')
  await expect(roster.getByRole('region', { name: '候補名單', exact: true })).toContainText('學生')
  await expect(page.getByLabel('搜尋姓名', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '更新名單', exact: true }).click()
  await expect(page.getByRole('button', { name: '更新名單', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
})

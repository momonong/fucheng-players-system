import { expect, test } from '@playwright/test'

test('整批八十人匯入後管理名單、級數篩選與列印', async ({ page }, testInfo) => {
  const name = `合成八十人匯入-${testInfo.project.name}`
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '比賽', exact: true })).toBeVisible()
  const me = await (await page.request.get('/api/auth/me')).json()
  const headers = { 'X-CSRF-Token': me.csrf_token }
  const created = await page.request.post('/api/admin/competitions', { headers, data: {
    name, status: 'draft', capacity: 80, competition_date: '2099-09-20', registration_deadline: '2099-09-19T12:00:00+08:00', notes: '合成資料'
  } })
  expect(created.status()).toBe(201)
  const competition = await created.json()
  const payload = { version: 1, request_id: crypto.randomUUID(), reason: '合成已確認八十人名單', rows: Array.from({ length: 80 }, (_, i) => ({ source_ref: `row-${i}`, create_member: true, name: `${name}-${String(i).padStart(2,'0')}`, level: i % 10 + 1, diet: i === 0 ? 'vegetarian' : 'omnivore' })) }
  const url = `/api/admin/competitions/${competition.id}/import-confirmed-roster`
  expect((await page.request.post(url, { headers, data: payload })).status()).toBe(200)
  expect((await page.request.post(url, { headers, data: payload })).status()).toBe(200)
  await page.reload()
  await page.locator('.competition-item').filter({ has: page.getByText(name, { exact: true }) }).click()
  await expect(page.locator('.summary-grid')).toContainText('80/80')
  await expect(page.locator('.summary-grid')).toContainText('79/1/0')
  await expect(page.locator('.roster-confirmed tbody tr')).toHaveCount(80)
  await expect(page.getByRole('combobox', { name: '狀態' })).toHaveValue('closed')
  await page.getByRole('combobox', { name: '硬實力快照' }).selectOption('7')
  await expect(page.locator('.roster-confirmed tbody tr')).toHaveCount(8)
  await expect(page.locator('.summary-grid')).toContainText('80/80')
  await page.getByRole('combobox', { name: '硬實力快照' }).selectOption('')
  await page.getByText('報名操作稽核', { exact: true }).click()
  await expect(page.locator('.registration-history li')).toHaveCount(80)
  await page.getByText('報名操作稽核', { exact: true }).click()
  await page.emulateMedia({ media: 'print' })
  await expect(page.locator('.print-title')).toBeVisible()
  await expect(page.locator('.roster-confirmed tbody tr')).toHaveCount(80)
  await page.emulateMedia({ media: 'screen' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('imported-eighty.png') })
})

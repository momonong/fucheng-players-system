import { expect, test } from '@playwright/test'

test('管理員建立比賽、維護候補與列印名單', async ({ page }, testInfo) => {
  const password = process.env.FUCHENG_E2E_ADMIN_PASSWORD
  if (!password) throw new Error('缺少動態 E2E 管理員密碼')
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號').fill('e2e-admin')
  await page.getByLabel('密碼').fill(password)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '比賽', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '報名與設定', exact: true }).click()

  await page.getByRole('button', { name: '建立比賽' }).click()
  const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const deadline = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000)
  const localDate = date.toISOString().slice(0, 10)
  const localDeadline = deadline.toISOString().slice(0, 16)
  await page.getByLabel('名稱').fill('合成 9/20 會內賽')
  await page.getByLabel('比賽日期').fill(localDate)
  await page.getByLabel('名額上限').fill('2')
  await page.getByLabel('報名截止時間（台北時間）').fill(localDeadline)
  await page.getByLabel('狀態').selectOption('open')
  await page.getByLabel('備註').fill('端到端測試資料')
  await page.getByRole('button', { name: '儲存比賽' }).click()
  await expect(page.getByText('比賽已建立')).toBeVisible()

  async function addMember(name: string) {
    const picker = page.locator('.candidate-picker')
    if (!(await picker.evaluate(element => (element as HTMLDetailsElement).open))) await picker.locator('summary').click()
    await page.getByLabel('搜尋姓名／辨識註記', { exact: true }).fill(name)
    await expect(page.getByRole('button', { name: new RegExp(name) })).toBeVisible()
    await page.getByRole('button', { name: new RegExp(name) }).click()
    await expect(page.getByText('名單已更新')).toBeVisible()
  }
  await addMember('合成會員一')
  await addMember('合成會員二')
  await addMember('合成會員三')
  await expect(page.locator('.summary-card').filter({ hasText: '正取／名額' })).toContainText('2/2')
  await expect(page.locator('.summary-card').filter({ hasText: '候補' })).toContainText('1')

  const confirmedRow = page.getByRole('row').filter({ hasText: '合成會員一' })
  await confirmedRow.getByRole('button', { name: '取消' }).click()
  await expect(page.locator('.summary-card').filter({ hasText: '待遞補' })).toContainText('1')
  await expect(page.locator('.summary-card').filter({ hasText: '正取／名額' })).toContainText('1/2')
  const waitingRow = page.getByRole('row').filter({ hasText: '合成會員三' })
  await waitingRow.getByRole('button', { name: '確認遞補' }).click()
  await expect(page.locator('.summary-card').filter({ hasText: '正取／名額' })).toContainText('2/2')
  await expect(page.locator('.summary-card').filter({ hasText: '葷／素／未設定' })).toContainText('1/1/0')

  await page.getByLabel('篩選名單').fill('合成會員三')
  await expect(page.getByText('篩選結果 1／全場 3 筆')).toBeVisible()
  await expect(page.locator('.summary-card').filter({ hasText: '正取／名額' })).toContainText('2/2')

  await page.route('**/api/admin/competitions/*', async route => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '此比賽已被其他管理員更新，請重新載入' }) })
    } else await route.continue()
  })
  await page.getByLabel('名稱').fill('衝突時保留的比賽名稱')
  await page.getByRole('button', { name: '儲存比賽' }).click()
  await expect(page.getByRole('alert')).toContainText('輸入已保留')
  await expect(page.getByLabel('名稱')).toHaveValue('衝突時保留的比賽名稱')
  await page.unroute('**/api/admin/competitions/*')

  const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noOverflow).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('competition-roster.png'), fullPage: true })
  if (testInfo.project.name === 'desktop') {
    await page.emulateMedia({ media: 'print' })
    await expect(page.locator('.competition-print')).toBeVisible()
    await page.pdf({ path: testInfo.outputPath('competition-roster.pdf'), format: 'A4', landscape: true, printBackground: true, preferCSSPageSize: true })
  }
})

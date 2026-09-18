import { expect, test } from '@playwright/test'

test('管理員新增修改，公開名單可搜尋篩選並支援列印', async ({ page }, testInfo) => {
  const suffix = testInfo.project.name === 'mobile' ? '手機' : '桌面'
  const e2ePassword = process.env.FUCHENG_E2E_ADMIN_PASSWORD
  if (!e2ePassword) throw new Error('缺少動態 E2E 管理員密碼')
  await page.goto('/admin')
  await page.getByLabel('帳號').fill('e2e-admin')
  await page.getByLabel('密碼').fill(e2ePassword)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '會員' })).toBeVisible()

  await page.getByRole('button', { name: '新增會員' }).click()
  await page.getByLabel('姓名（必填）').fill(`測試會員甲-${suffix}`)
  await page.getByLabel('重名辨識註記').fill(`${suffix}北區`)
  await page.getByLabel('球館原有會員編號').fill(`E2E-${suffix}`)
  await page.getByLabel('硬實力級數').selectOption('4')
  await page.getByLabel('預設葷素').selectOption('vegetarian')
  await page.getByRole('button', { name: '儲存會員' }).click()
  await expect(page.getByText('會員已新增', { exact: true })).toBeVisible()

  await page.getByLabel('姓名（必填）').fill(`測試會員乙-${suffix}`)
  await page.getByRole('button', { name: '儲存會員' }).click()
  await expect(page.getByText('會員資料已儲存', { exact: true })).toBeVisible()

  await page.route('**/api/admin/members/*', async route => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '此會員已被其他管理員更新，請重新載入後再編輯' }) })
    } else {
      await route.continue()
    }
  })
  await page.getByLabel('姓名（必填）').fill(`衝突時保留-${suffix}`)
  await page.getByRole('button', { name: '儲存會員' }).click()
  await expect(page.getByRole('alert')).toContainText('其他管理員更新')
  await expect(page.getByLabel('姓名（必填）')).toHaveValue(`衝突時保留-${suffix}`)
  await page.unroute('**/api/admin/members/*')

  await page.getByRole('link', { name: '會員分級名單' }).click()
  await expect(page.getByRole('heading', { name: '會員硬實力分級' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '1 級' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '5 級' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '10 級' })).toBeVisible()
  if (testInfo.project.name === 'mobile') {
    const mobileColumns = await page.locator('.level-card').first().locator('tbody').evaluate(element =>
      getComputedStyle(element).gridTemplateColumns.split(' ').length,
    )
    expect(mobileColumns).toBe(3)
    const namesAreNotClipped = await page.locator('.public-member-name').evaluateAll(elements =>
      elements.every(element => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight),
    )
    expect(namesAreNotClipped).toBe(true)
  }
  await page.screenshot({ path: testInfo.outputPath('all-levels.png'), fullPage: true })
  await page.getByLabel('搜尋姓名或辨識註記').fill(`${suffix}北區`)
  await expect(page.getByText(`測試會員乙-${suffix}`, { exact: true })).toBeVisible()
  await page.getByLabel('級數').selectOption('5')
  await expect(page.getByText('目前沒有符合條件的會員。')).toBeVisible()
  await page.getByLabel('級數').selectOption('4')
  await expect(page.getByText(`測試會員乙-${suffix}`, { exact: true })).toBeVisible()
  const noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noHorizontalOverflow).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('public-list.png'), fullPage: true })

  const levelCounts = [42, 42, 41, 42, 38, 25, 27, 22, 14, 34]
  const syntheticRoster = levelCounts.flatMap((count, levelIndex) =>
    Array.from({ length: count }, (_, memberIndex) => ({
      id: `synthetic-${levelIndex + 1}-${memberIndex + 1}`,
      name: `測試${levelIndex + 1}-${String(memberIndex + 1).padStart(2, '0')}`,
      distinguishing_note: memberIndex === 0 ? '同名' : null,
      level: levelIndex + 1,
      diet: memberIndex === 1 ? 'vegetarian' : 'omnivore',
    })),
  )
  await page.route('**/api/public/members*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(syntheticRoster),
  }))
  await page.reload()
  await expect(page.getByText('共 327 位會員')).toBeVisible()
  await page.emulateMedia({ media: 'print' })
  await expect(page.getByRole('button', { name: '列印／另存 PDF' })).toBeHidden()
  await expect(page.locator('.print-sheet')).toBeVisible()
  await expect(page.locator('.print-roster thead th')).toHaveCount(11)
  await expect(page.locator('.print-roster tbody tr')).toHaveCount(42)
  if (testInfo.project.name === 'desktop') {
    await page.pdf({
      path: testInfo.outputPath('a4-roster.pdf'),
      format: 'A4',
      landscape: true,
      printBackground: true,
      preferCSSPageSize: true,
    })
  }
})

import { expect, test } from '@playwright/test'

test('手機報名、公告圖片與管理入口寬度量測', async ({ browser }, testInfo) => {
  test.setTimeout(120_000)
  const admin = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true })
  const page = await admin.newPage()
  await page.goto('/admin')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.getByRole('link', { name: '比賽管理', exact: true }).click()
  await page.getByRole('button', { name: '報名與設定', exact: true }).click()
  await page.getByText('切換或建立比賽', { exact: true }).click()
  await page.getByRole('button', { name: '建立比賽' }).click()
  await page.getByLabel('名稱', { exact: true }).fill('合成手機長名稱比賽・兩位家人一起確認場次與餐食')
  await page.getByLabel('比賽日期').fill(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10))
  await page.getByLabel('名額上限').fill('2')
  await page.getByLabel('報名截止時間（台北時間）').fill(new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 16))
  await page.getByRole('combobox', { name: '狀態', exact: true }).selectOption('open')
  await page.getByRole('button', { name: '儲存比賽' }).click()
  await expect(page.getByText('比賽已建立', { exact: true })).toBeVisible()
  const competitionId = await page.getByRole('combobox', { name: '選擇比賽' }).inputValue()
  await page.getByRole('link', { name: '公告管理', exact: true }).click()
  await page.getByRole('button', { name: '新增公告' }).click()
  await page.getByLabel('公告標題').fill('合成手機閱讀與照片排列驗收公告')
  await page.getByLabel('公告內容').fill('這是手機閱讀的合成公告。')
  await page.getByRole('button', { name: '儲存公告' }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await page.getByRole('button', { name: '插入圖片' }).click()
  await page.getByLabel('選擇內文圖片').setInputFiles({ name: 'mobile-synthetic.png', mimeType: 'image/png', buffer: await page.screenshot() })
  await expect(page.getByLabel('公告內容').locator('figure img')).toHaveCount(1)
  await page.getByLabel('公告內容').locator('figure img').tap()
  await expect(page.getByRole('group', { name: '圖片操作' })).toBeVisible()
  await page.getByRole('button', { name: '完成', exact: true }).tap()
  await expect(page.getByRole('group', { name: '圖片操作' })).toHaveCount(0)
  await page.getByLabel('發布到首頁').check()
  await page.getByRole('button', { name: '儲存公告' }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')

  const visitor = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true })
  const publicPage = await visitor.newPage()
  const measures: unknown[] = []
  for (const width of [360, 390, 430, 768]) {
    await admin.setDefaultTimeout(5000)
    await page.setViewportSize({ width, height: 844 })
    await publicPage.setViewportSize({ width, height: 844 })
    for (const [name, target, url] of [
      ['home', publicPage, '/'],
      ['register', publicPage, `/register/${competitionId}`],
      ['competitions', page, '/admin/competitions'],
      ['announcements', page, '/admin/announcements'],
    ] as const) {
      await target.goto(url)
      if (name === 'home') await expect(target.getByRole('heading', { name: '最新公告', exact: true })).toBeVisible()
      if (name === 'home') await expect.poll(() => target.locator('.news-card img').first().evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0)
      if (name === 'register') await expect(target.getByLabel('搜尋姓名', { exact: true })).toBeVisible()
      if (name === 'competitions') {
        await target.getByRole('button', { name: '報名與設定', exact: true }).click()
        await expect(target.locator('#registration-roster')).toBeVisible()
      }
      if (name === 'announcements') {
        await target.getByRole('button', { name: /合成手機閱讀與照片排列驗收公告 已發布/ }).click()
        await expect(target.getByRole('button', { name: '插入圖片' })).toBeVisible()
      }
      const metric = await target.evaluate(() => ({
        width: innerWidth, documentWidth: document.documentElement.scrollWidth,
        bodyHeight: document.body.scrollHeight,
        headerHeight: document.querySelector('header.admin-header, header.hero')?.getBoundingClientRect().height ?? 0,
        rosterTop: document.querySelector('#registration-roster')?.getBoundingClientRect().top ?? null,
        toolbarHeight: document.querySelector('.rich-toolbar')?.getBoundingClientRect().height ?? null,
        imageWidth: document.querySelector('.news-card img')?.getBoundingClientRect().width ?? null,
      }))
      measures.push({ name, ...metric })
      expect(metric.documentWidth, `${name} at ${width}px should not scroll horizontally`).toBeLessThanOrEqual(width)
      await target.screenshot({ path: testInfo.outputPath(`${width}-${name}.png`), fullPage: true })
    }
  }
  console.log('MOBILE_UX_METRICS', JSON.stringify(measures))
  await visitor.close()
  await admin.close()
})

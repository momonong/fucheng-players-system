import { expect, test } from '@playwright/test'
import { randomUUID } from 'node:crypto'

test('公告內嵌圖片、段落順序、連結與公開顯示', async ({ page, browser }, testInfo) => {
  await page.goto('/admin/announcements')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('link', { name: '公告管理', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('button', { name: '新增公告' }).click()
  await expect(page.locator('.legacy-photo')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '插入圖片' })).toBeDisabled()
  await expect(page.getByText('先儲存草稿，即可在段落間插入圖片。')).toBeVisible()
  const title = `合成內嵌公告-${testInfo.project.name}`
  await page.getByLabel('公告標題').fill(title)
  const editor = page.getByRole('textbox', { name: '公告內容' })
  await editor.fill('前段')
  await editor.press('Enter')
  await editor.type('後段')
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')

  async function selectBlock(index: number, selectText = false) {
    await editor.evaluate((root, args) => {
      const block = root.children[args.index]
      const range = document.createRange()
      range.selectNodeContents(block)
      if (!args.selectText) range.collapse(false)
      const selection = window.getSelection()!
      selection.removeAllRanges(); selection.addRange(range)
    }, { index, selectText })
  }
  const photo = { name: 'synthetic.png', mimeType: 'image/png', buffer: await page.screenshot() }
  await selectBlock(0)
  await page.getByRole('button', { name: '插入圖片' }).click()
  await page.getByLabel('選擇內文圖片').setInputFiles(photo)
  await expect(editor.locator('figure img')).toHaveCount(1)
  await expect(editor.locator('figure img')).toHaveJSProperty('complete', true)
  await selectBlock(2)
  await page.getByRole('button', { name: '插入圖片' }).click()
  await page.getByLabel('選擇內文圖片').setInputFiles(photo)
  await expect(editor.locator('figure img')).toHaveCount(2)
  const firstId = await editor.locator('figure').first().getAttribute('data-media-id')
  const secondId = await editor.locator('figure').last().getAttribute('data-media-id')
  await editor.locator('figure').last().click()
  await page.getByRole('button', { name: '上移區塊' }).click()
  await expect.poll(() => editor.evaluate(root => [...root.children].map(node => node.tagName).join(','))).toContain('FIGURE,FIGURE')
  await editor.locator('figure').first().click()
  await page.getByRole('button', { name: '下移區塊' }).click()
  await expect.poll(() => editor.locator('figure').first().getAttribute('data-media-id')).toBe(secondId)
  await expect(editor.locator('figure').last()).toHaveAttribute('data-media-id', firstId!)
  await selectBlock(0, true)
  await page.getByRole('button', { name: '插入連結' }).click()
  await page.getByLabel('連結網址').fill('https://example.com/synthetic')
  await page.getByRole('button', { name: '套用連結' }).click()
  await expect(editor.locator('a')).toHaveAttribute('href', 'https://example.com/synthetic')
  await selectBlock(0, true)
  await page.getByRole('combobox', { name: '文字樣式' }).selectOption('h2')
  await expect(editor.locator('h2')).toContainText('前段')
  await page.getByLabel('發布到首頁').check()
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await page.reload()
  await page.getByRole('button', { name: new RegExp(title) }).click()
  await expect(editor.locator('figure img')).toHaveCount(2)
  await expect(editor.locator('a')).toHaveAttribute('href', 'https://example.com/synthetic')
  await expect(editor.locator('h2')).toContainText('前段')
  await page.screenshot({ path: testInfo.outputPath('editor-paragraph-images.png'), fullPage: true })
  const context = await browser.newContext({ viewport: testInfo.project.use.viewport, isMobile: testInfo.project.use.isMobile })
  const visitor = await context.newPage()
  await visitor.goto('/')
  const article = visitor.locator('.news-card').filter({ hasText: title })
  await expect(article.locator('figure img')).toHaveCount(2)
  await expect(article.locator('a[href="https://example.com/synthetic"]')).toHaveText('前段')
  await expect(article.locator('figure img').first()).toBeVisible()
  expect(await article.locator('.rich-body').evaluate(root => [...root.children].map(node => node.tagName).join(','))).toContain('FIGURE,FIGURE')
  await expect(article.locator('h2')).toContainText('前段')
  await visitor.screenshot({ path: testInfo.outputPath('public-paragraph-images.png'), fullPage: true })
  const previousId = await editor.locator('figure').first().getAttribute('data-media-id')
  await editor.locator('figure').first().click()
  await page.getByRole('button', { name: '插入圖片' }).click()
  await page.getByLabel('選擇內文圖片').setInputFiles(photo)
  await expect(editor.locator('figure')).toHaveCount(2)
  await expect.poll(() => editor.locator('figure').first().getAttribute('data-media-id')).not.toBe(previousId)
  await editor.locator('figure').last().click()
  await page.getByRole('button', { name: '移除圖片' }).click()
  await expect(editor.locator('figure')).toHaveCount(1)
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await visitor.reload()
  await expect(visitor.locator('.news-card').filter({ hasText: title }).locator('figure img')).toHaveCount(1)
  await context.close()
})

test('既有文末照片仍可查看、替換與移除', async ({ page }, testInfo) => {
  await page.goto('/admin/announcements')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.getByRole('button', { name: '新增公告' }).waitFor()
  const auth = await page.request.get('/api/auth/me')
  const { csrf_token: csrf } = await auth.json() as { csrf_token: string }
  const headers = { 'X-CSRF-Token': csrf }
  const title = `合成既有文末照片-${testInfo.project.name}`
  const created = await page.request.post('/api/admin/announcements', { headers, data: {
    title, body: '舊式文末照片相容檢查', body_format: 'plain', is_published: false, is_pinned: false, request_id: randomUUID(),
  } })
  expect(created.ok()).toBe(true)
  const item = await created.json() as { id: string; version: number }
  const photo = { name: 'synthetic.png', mimeType: 'image/png', buffer: await page.screenshot() }
  const first = await page.request.post(`/api/admin/announcements/${item.id}/photo`, { headers, multipart: {
    version: String(item.version), request_id: randomUUID(), photo,
  } })
  expect(first.ok()).toBe(true)
  const firstId = (await first.json() as { photo_id: string }).photo_id
  await page.reload()
  await page.getByRole('button', { name: new RegExp(title) }).click()
  const legacy = page.locator('.legacy-photo')
  await expect(legacy).toHaveCount(1)
  await legacy.locator('summary').click()
  await expect(legacy.getByRole('img', { name: '既有文末照片' })).toBeVisible()
  const chooser = page.waitForEvent('filechooser')
  await legacy.getByRole('button', { name: '替換文末照片' }).click()
  await (await chooser).setFiles(photo)
  await expect(legacy.getByRole('status')).toContainText('儲存後替換')
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect.poll(async () => {
    const response = await page.request.get('/api/admin/announcements')
    const photoId = (await response.json() as { id: string; photo_id: string | null }[]).find(row => row.id === item.id)?.photo_id
    return !!photoId && photoId !== firstId
  }).toBe(true)
  await legacy.locator('summary').click()
  await legacy.getByRole('button', { name: '移除文末照片' }).click()
  await expect(legacy.getByRole('status')).toContainText('儲存後移除')
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.locator('.legacy-photo')).toHaveCount(0)
  const afterRemove = await page.request.get('/api/admin/announcements')
  expect((await afterRemove.json() as { id: string; photo_id: string | null }[]).find(row => row.id === item.id)?.photo_id).toBeNull()
})

test('四種寬度的公開頁面與管理導覽', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  await page.goto('/admin')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('link', { name: '會員管理', exact: true })).toHaveAttribute('aria-current', 'page')
  for (const width of [390, 768, 1440, 3840]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [route, label] of [['/', 'home'], ['/members', 'members'], ['/competitions', 'registration'], ['/admin', 'admin']] as const) {
      await page.goto(route)
      await expect(page.locator('main')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: testInfo.outputPath(`${label}-${width}.png`), fullPage: true })
    }
    await expect(page.getByRole('link', { name: '會員管理', exact: true })).toHaveAttribute('aria-current', 'page')
    await page.getByRole('link', { name: '公告管理', exact: true }).click()
    await expect(page.getByRole('link', { name: '公告管理', exact: true })).toHaveAttribute('aria-current', 'page')
  }
})

test('公告工具列分組標籤在手機與桌面可辨識', async ({ page }, testInfo) => {
  await page.goto('/admin/announcements')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.getByRole('button', { name: '新增公告' }).click()
  const labels = page.locator('.rich-group-title')
  await expect(labels).toHaveText(['樣式', '文字', '段落', '插入', '區塊'])
  for (const width of testInfo.project.name === 'desktop' ? [390, 1440] : [390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const label of await labels.all()) await expect(label).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`toolbar-${width}.png`), fullPage: true })
  }
})

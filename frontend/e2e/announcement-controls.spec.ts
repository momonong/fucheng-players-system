import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'

const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
const url = (path: string) => prefix + path

async function login(page: Page) {
  await page.goto(url('/admin/announcements'))
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('button', { name: '新增公告', exact: true })).toBeVisible()
  const auth = await (await page.request.get(url('/api/auth/me'))).json()
  return { 'X-CSRF-Token': auth.csrf_token }
}

test('內容先儲存、狀態立即保存，未知結果鎖定並原樣重試', async ({ page }, info) => {
  await login(page)
  const title = `合成公告開關-${info.project.name}-${prefix || 'root'}`
  const publish = page.getByRole('switch', { name: '公開到首頁', exact: true })
  const pin = page.getByRole('switch', { name: '置頂公告', exact: true })
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  await page.getByLabel('公告標題').fill(title)
  await page.getByLabel('公告內容', { exact: true }).fill('第一版內容')
  await expect(publish).toBeDisabled(); await expect(pin).toBeDisabled()
  await expect(page.getByText('先儲存內容，再變更公開或置頂狀態', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await expect(publish).not.toBeChecked(); await expect(pin).not.toBeChecked()
  const rows = await (await page.request.get(url('/api/admin/announcements'))).json()
  const item = rows.find((row: { title: string }) => row.title === title)
  expect(item.is_published).toBe(false)
  const endpoint = url(`/api/admin/announcements/${item.id}`)
  const attempts: unknown[] = []
  await page.route(`**/api/admin/announcements/${item.id}`, async route => {
    if (route.request().method() !== 'PUT') { await route.continue(); return }
    attempts.push(route.request().postDataJSON())
    if (attempts.length === 1) { await route.fetch(); await route.abort('failed') }
    else await route.continue()
  })
  await publish.click()
  await expect(page.getByRole('alert')).toContainText('結果尚未確認')
  await expect(publish).toBeDisabled(); await expect(pin).toBeDisabled()
  await expect(publish).not.toBeChecked()
  await expect(page.getByLabel('公告標題')).toBeDisabled()
  await expect(page.getByRole('button', { name: '儲存公告', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '新增公告', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '原樣重試狀態變更', exact: true }).click()
  await expect(publish).toBeChecked()
  expect(attempts).toHaveLength(2); expect(attempts[1]).toEqual(attempts[0])
  await page.unroute(`**/api/admin/announcements/${item.id}`)
  await page.getByLabel('公告標題').fill(title + '尚未儲存')
  await expect(publish).toBeDisabled(); await expect(pin).toBeDisabled()
  const before = (await (await page.request.get(url('/api/admin/announcements'))).json()).find((row: { id: string }) => row.id === item.id)
  expect(before.title).toBe(title); expect(before.is_published).toBe(true)
  await page.getByLabel('公告標題').fill(title)
  await expect(pin).toBeEnabled()
  await pin.click(); await expect(pin).toBeChecked()
  await page.getByLabel('公告內容', { exact: true }).fill('第二版內容')
  await expect(publish).toBeDisabled(); await expect(pin).toBeDisabled()
  await expect(page.getByText('這則公告已公開到首頁；儲存內容會立即更新首頁。', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await expect(publish).toBeChecked(); await expect(pin).toBeChecked()
  await publish.click(); await expect(publish).not.toBeChecked()
  const audits = await (await page.request.get(endpoint + '/history')).json()
  expect(audits.filter((row: { action: string; changes: object }) => row.action === 'update' && 'is_published' in row.changes)).toHaveLength(2)
  expect(audits.filter((row: { action: string; changes: object }) => row.action === 'update' && 'is_pinned' in row.changes)).toHaveLength(1)
  const saveBox = await page.getByRole('button', { name: '儲存公告', exact: true }).boundingBox()
  const historyBox = await page.getByRole('button', { name: '公告修改歷史', exact: true }).boundingBox()
  const switchBox = await publish.boundingBox()
  expect(historyBox!.y).toBeGreaterThan(saveBox!.y)
  if (info.project.name === 'mobile') expect(switchBox!.y).toBeGreaterThan(historyBox!.y)
  else expect(switchBox!.x).toBeGreaterThan(saveBox!.x + saveBox!.width)
  if (info.project.name === 'mobile') {
    const add = page.getByRole('button', { name: '新增公告', exact: true })
    const addBox = await add.boundingBox()
    const hintBox = await page.locator('.announcement-main > .section-title > p').boundingBox()
    await expect(add).toHaveCSS('white-space', 'nowrap')
    expect(addBox!.height).toBeGreaterThanOrEqual(44)
    expect(addBox!.height).toBeLessThan(60)
    expect(addBox!.y).toBeGreaterThanOrEqual(hintBox!.y + hintBox!.height)
  }
  const deleteContrast = await page.getByRole('button', { name: '刪除公告', exact: true }).evaluate(button => {
    const style = getComputedStyle(button)
    const luminance = (color: string) => {
      const channels = color.match(/[\d.]+/g)!.slice(0, 3).map(value => {
        const component = Number(value) / 255
        return component <= .04045 ? component / 12.92 : ((component + .055) / 1.055) ** 2.4
      })
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]
    }
    const foreground = luminance(style.color), background = luminance(style.backgroundColor)
    return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05)
  })
  expect(deleteContrast).toBeGreaterThanOrEqual(4.5)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('announcement-save-and-switches.png'), fullPage: true })
})

test('狀態重試遇後續更新時核對 receipt，不宣告舊狀態為目前狀態', async ({ page }, info) => {
  const headers = await login(page)
  const title = `合成狀態交錯-${info.project.name}-${prefix || 'root'}`
  const original = { title, body: '已儲存內容', body_format: 'plain', is_published: false, is_pinned: false, request_id: randomUUID() }
  const item = await (await page.request.post(url('/api/admin/announcements'), { headers, data: original })).json()
  const endpoint = url(`/api/admin/announcements/${item.id}`)
  await page.reload()
  await page.locator('.announcement-row').filter({ hasText: title }).click()
  const attempts: unknown[] = []
  await page.route(`**/api/admin/announcements/${item.id}`, async route => {
    if (route.request().method() !== 'PUT') { await route.continue(); return }
    attempts.push(route.request().postDataJSON())
    if (attempts.length === 1) {
      const committed = await (await route.fetch()).json()
      expect((await page.request.put(endpoint, { headers, data: { ...original, version: committed.version, body: '另一管理員最新內容', request_id: randomUUID() } })).status()).toBe(200)
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('switch', { name: '公開到首頁', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('結果尚未確認')
  await page.getByRole('button', { name: '原樣重試狀態變更', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('公告後續又被變更')
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(page.getByLabel('公告內容', { exact: true })).toHaveText('已儲存內容')
  await expect(page.getByRole('switch', { name: '公開到首頁', exact: true })).toBeDisabled()
  expect(attempts).toHaveLength(2); expect(attempts[1]).toEqual(attempts[0])
  const current = (await (await page.request.get(url('/api/admin/announcements'))).json()).find((row: { id: string }) => row.id === item.id)
  expect(current.body).toBe('另一管理員最新內容'); expect(current.is_published).toBe(false); expect(current.version).toBe(3)
})

test('中英文選取斜體可儲存重載並公開顯示，工具列保留觸控空間', async ({ page, browser }, info) => {
  await login(page)
  const title = `合成中英斜體-${info.project.name}-${prefix || 'root'}`
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  await page.getByLabel('公告標題').fill(title)
  const editor = page.getByRole('textbox', { name: '公告內容', exact: true })
  await editor.fill('中文斜體 English italic')
  for (const text of ['中文斜體', 'English italic']) {
    await editor.evaluate((root, value) => {
      root.focus()
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
      let node: Node | null
      while ((node = walker.nextNode())) {
        const offset = node.textContent?.indexOf(value) ?? -1
        if (offset < 0) continue
        const range = document.createRange()
        range.setStart(node, offset); range.setEnd(node, offset + value.length)
        const selection = window.getSelection()!
        selection.removeAllRanges(); selection.addRange(range)
        root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
        return
      }
      throw new Error('Synthetic selection text was not found')
    }, text)
    await page.getByRole('button', { name: '斜體', exact: true }).click()
  }
  await expect(editor.locator('i, em')).toHaveText(['中文斜體', 'English italic'])
  await expect(page.getByRole('button', { name: '斜體', exact: true })).toHaveCSS('font-style', 'italic')
  for (const control of await page.locator('.rich-group button, .rich-group select').all()) {
    const box = await control.boundingBox()
    expect(box!.height).toBeGreaterThanOrEqual(44)
  }
  await page.getByRole('button', { name: '儲存公告', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('公告已儲存')
  await page.getByRole('switch', { name: '公開到首頁', exact: true }).click()
  await expect(page.getByRole('switch', { name: '公開到首頁', exact: true })).toBeChecked()
  await page.reload()
  await page.locator('.announcement-row').filter({ hasText: title }).click()
  await expect(editor.locator('i, em')).toHaveText(['中文斜體', 'English italic'])
  expect(await editor.evaluate(root => getComputedStyle(root).fontSynthesis)).toBe('style')
  const context = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: info.project.use.viewport, isMobile: info.project.use.isMobile })
  const visitor = await context.newPage()
  try {
    await visitor.goto(url('/'))
    const body = visitor.locator('.news-card').filter({ hasText: title }).locator('.rich-body')
    await expect(body.locator('i, em')).toHaveText(['中文斜體', 'English italic'])
    for (const italic of await body.locator('i, em').all()) await expect(italic).toHaveCSS('font-style', 'italic')
    expect(await body.evaluate(root => getComputedStyle(root).fontSynthesis)).toBe('style')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('announcement-italic-editor.png'), fullPage: true })
    await visitor.screenshot({ path: info.outputPath('announcement-italic-public.png'), fullPage: true })
  } finally { await context.close() }
})

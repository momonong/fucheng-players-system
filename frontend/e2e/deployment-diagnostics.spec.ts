import { expect, test } from '@playwright/test'
const prefix = (process.env.FUCHENG_BASE_PATH ?? '').replace(/\/$/, '')
async function login(page: import('@playwright/test').Page) {
  await page.goto(`${prefix}/admin`)
  await page.getByLabel('帳號', { exact: true }).fill(test.info().project.name === 'mobile' ? 'e2e-grid-mobile' : 'e2e-grid-desktop')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.getByRole('link', { name: '系統狀態' }).click()
}
test('啟動後一鍵檢查，顯示容器與未測項目並保留原報告', async ({ page }) => {
  await login(page)
  const [executed] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/admin/deployment-report/run') && response.request().method() === 'POST' && response.status() === 200),
    page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click(),
  ])
  const original = (await executed.json()).run.request_id as string
  await expect(page.locator('[data-run-id]')).toHaveAttribute('data-run-id', original)
  await expect(page.getByText('目前執行中的 app／Linux 容器', { exact: true })).toBeVisible()
  await expect(page.getByText('報告已保存；回傳憑證尚未配置或無法使用。', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'windows_edition NOT_TESTED' })).toBeVisible()
  expect(original).toBeTruthy()
  await page.reload()
  await expect(page.locator('[data-run-id]')).toHaveAttribute('data-run-id', original!)
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: '下載 JSON', exact: true }).click()])
  expect(download.suggestedFilename()).toBe('deployment-report.json')
  const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
  expect(sizes.document).toBeLessThanOrEqual(sizes.viewport + 2)
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: `../data/image-deployment-checks-20261024/diagnostics-${prefix ? 'prefix' : 'root'}-${test.info().project.name}.png` })
})

test('失去執行回應後讀回原 UUID，不產生第二個 POST', async ({ page }) => {
  await login(page)
  let posts = 0
  let original = ''
  await page.route('**/api/admin/deployment-report/run', async route => {
    posts++
    original = route.request().postDataJSON().request_id
    await route.fetch()
    await route.abort('failed')
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await expect(page.getByRole('button', { name: '讀回原執行結果', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '讀回原執行結果', exact: true }).click()
  await expect(page.locator('[data-run-id]')).toHaveAttribute('data-run-id', original)
  expect(posts).toBe(1)
})

test('已取得執行回覆但讀回失敗，只重讀 GET', async ({ page }) => {
  await login(page)
  let posts = 0
  let reads = 0
  await page.route('**/api/admin/deployment-report/run', async route => { posts++; await route.continue() })
  await page.route('**/api/admin/deployment-report/runs/*', async route => {
    if (route.request().method() === 'GET' && ++reads === 1) await route.abort('failed')
    else await route.continue()
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await expect(page.getByText('伺服器已回覆，只會重新讀取報告。', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '讀回原執行結果', exact: true }).click()
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  expect(posts).toBe(1)
  expect(reads).toBe(2)
})

test('原執行不存在時以同一 UUID 與 payload 重試', async ({ page }) => {
  await login(page)
  const payloads: unknown[] = []
  await page.route('**/api/admin/deployment-report/run', async route => {
    payloads.push(route.request().postDataJSON())
    if (payloads.length === 1) await route.abort('failed')
    else await route.continue()
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await expect(page.getByRole('button', { name: '讀回原執行結果', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: '讀回原執行結果', exact: true }).click()
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  expect(payloads).toHaveLength(2)
  expect(payloads[1]).toEqual(payloads[0])
})

test('版本衝突後讀回核對，不重試舊 version 或靜默產生新 ID', async ({ page }) => {
  await login(page)
  let posts = 0
  await page.route('**/api/admin/deployment-report/run', async route => {
    posts++
    await route.fulfill({ status: 409, json: { detail: '報告已更新；請重新載入並核對' } })
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await page.getByRole('button', { name: '讀回原執行結果', exact: true }).click()
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  expect(posts).toBe(1)
})

test('讀回舊 run 後下載綁定畫面原報告，不跟隨最新報告', async ({ page }) => {
  await login(page)
  const csrf = (await (await page.request.get(`${prefix}/api/auth/me`)).json()).csrf_token as string
  let original: { checked_at: string } | null = null
  let latest: { checked_at: string } | null = null
  let changed = false
  await page.route('**/api/admin/deployment-report/runs/*', async route => {
    const response = await route.fetch()
    const old = await response.json()
    if (!changed && route.request().method() === 'GET') {
      changed = true
      original = old.report
      const newer = await page.request.post(`${prefix}/api/admin/deployment-report/run`, {
        headers: { 'X-CSRF-Token': csrf }, data: { version: old.version, request_id: crypto.randomUUID(), probe_network: false },
      })
      expect(newer.ok()).toBeTruthy()
      latest = (await newer.json()).report
    }
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: '下載 JSON', exact: true }).click()])
  const fs = await import('node:fs/promises')
  const downloaded = JSON.parse(await fs.readFile((await download.path())!, 'utf8'))
  expect(original).not.toBeNull()
  expect(latest).not.toBeNull()
  expect(downloaded.checked_at).toBe((original as unknown as { checked_at: string }).checked_at)
  expect(downloaded.checked_at).not.toBe((latest as unknown as { checked_at: string }).checked_at)
  const [markdown] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: '下載 Markdown', exact: true }).click()])
  const text = await fs.readFile((await markdown.path())!, 'utf8')
  const checked = text.match(/檢查時間：([^\n]+)/)?.[1]
  expect(new Date(checked!).getTime()).toBe(new Date((original as unknown as { checked_at: string }).checked_at).getTime())
})

test('容量507明確未保存會解除pending，保留原報告與下載和手動控制', async ({ page }) => {
  await login(page)
  const [saved] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/admin/deployment-report/run') && response.request().method() === 'POST' && response.status() === 200),
    page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click(),
  ])
  const original = (await saved.json()).run.request_id as string
  await expect(page.locator('[data-run-id]')).toHaveAttribute('data-run-id', original)
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  let posts = 0
  await page.route('**/api/admin/deployment-report/run', async route => {
    posts++
    await route.fulfill({ status: 507, json: { detail: '本機檢查報告儲存已滿；舊報告保留，請聯絡管理者' } })
  })
  await page.getByRole('button', { name: '立即檢查並回傳', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('本次檢查未保存')
  await expect(page.locator('[data-run-id]')).toHaveAttribute('data-run-id', original)
  await expect(page.getByRole('button', { name: '立即檢查並回傳', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('fucheng-deployment-diagnostic:')))).toEqual([])
  await expect(page.getByRole('button', { name: '讀回原執行結果', exact: true })).toHaveCount(0)
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: '下載 JSON', exact: true }).click()])
  expect(download.suggestedFilename()).toBe('deployment-report.json')
  await page.getByText('額外 Windows 主機檢查／手動上傳', { exact: true }).click()
  await expect(page.getByLabel('選擇部署檢查 JSON')).toBeEnabled()
  await page.getByLabel('選擇部署檢查 JSON').setInputFiles({ name: 'synthetic.json', mimeType: 'application/json', buffer: Buffer.from('{}') })
  await expect(page.getByRole('button', { name: '上傳並取代最新報告', exact: true })).toBeEnabled()
  expect(posts).toBe(1)
})

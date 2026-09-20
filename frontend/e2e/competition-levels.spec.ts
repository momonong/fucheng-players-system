import { expect, test } from '@playwright/test'

test('當次級數安排、保存歷史、真實版本衝突與失敗草稿保留', async ({ page }, testInfo) => {
  await page.goto('/admin/competitions')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-levels-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '比賽', exact: true })).toBeVisible()
  const auth = await (await page.request.get('/api/auth/me')).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token }
  const name = `合成級數安排-${testInfo.project.name}`
  async function createCompetition(suffix: string) {
    const response = await page.request.post('/api/admin/competitions', { headers, data: {
      name: name + suffix, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: 3, status: 'open', notes: '只有合成資料',
    } })
    expect(response.status()).toBe(201)
    return response.json()
  }
  const competition = await createCompetition('甲場')
  const other = await createCompetition('乙場')
  const regs = []
  for (let i = 0; i < 4; i++) {
    const response = await page.request.post('/api/admin/members', { headers, data: {
      name: `${name}選手${i}`, distinguishing_note: `合成辨識${i}`, level: i + 2, diet: 'unset', is_active: true,
    } })
    expect(response.status()).toBe(201)
    const member = await response.json()
    const registered = await page.request.post(`/api/admin/competitions/${competition.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })
    expect(registered.status()).toBe(201)
    regs.push(await registered.json())
    if (i === 0) expect((await page.request.post(`/api/admin/competitions/${other.id}/registrations`, { headers, data: { member_id: member.id, request_id: crypto.randomUUID() } })).status()).toBe(201)
  }
  expect((await page.request.post(`/api/admin/registrations/${regs[2].id}/cancel`, { headers, data: { version: 1, request_id: crypto.randomUUID() } })).status()).toBe(200)
  await page.reload()
  await page.getByRole('button', { name: new RegExp(name + '甲場') }).click()
  const area = page.getByRole('region', { name: '當次比賽級數安排' })
  const person = area.locator(`[data-registration-id="${regs[0].id}"]`)
  await expect(area.getByText('全場正取安排 2 人・候補 1 人・取消 1 人')).toBeVisible()
  await expect(person).toContainText('報名快照 2 級')
  await person.getByRole('button', { name: '調整級數' }).click()
  await expect(area.getByLabel('調整後當次級數')).toBeFocused()
  await area.getByLabel('調整後當次級數').selectOption('7')
  await area.getByLabel('調級原因（必填）').fill('合成現場安排')
  await area.getByRole('button', { name: '儲存當次級數', exact: true }).click()
  await expect(person).toContainText('當次級數 7 級')
  await expect(person).toContainText('報名快照 2 級')
  await area.getByLabel('安排搜尋姓名／辨識註記').fill('合成辨識0')
  await area.getByLabel('當次級數篩選').selectOption('7')
  await expect(area.getByText('篩選正取 1／全場正取 2 人')).toBeVisible()
  await expect(area.getByRole('region', { name: '當次 7 級正取' })).toContainText('篩選 1／全場 1 人')
  await area.getByLabel('當次級數篩選').selectOption('2')
  await expect(area.getByText('篩選正取 0／全場正取 2 人')).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: new RegExp(name + '甲場') }).click()
  await expect(person).toContainText('當次級數 7 級')
  await page.getByText('報名操作稽核', { exact: true }).click()
  await expect(page.locator('.registration-history')).toContainText('當次級數：2 → 7 級')
  await expect(page.locator('.registration-history')).toContainText('原因：合成現場安排')
  await expect(page.locator('.registration-history')).toContainText('e2e-levels-admin')

  // A second editor really commits version 3; the browser still holds version 2.
  await person.getByRole('button', { name: '調整級數' }).click()
  await area.getByLabel('調整後當次級數').selectOption('9')
  await area.getByLabel('調級原因（必填）').fill('衝突保留原因')
  const mutationUrl = `/api/admin/registrations/${regs[0].id}/level`
  expect((await page.request.put(mutationUrl, { headers, data: { version: 2, competition_level: 8, reason: '另一位管理員先更新', request_id: crypto.randomUUID() } })).status()).toBe(200)
  await area.getByRole('button', { name: '儲存當次級數', exact: true }).click()
  await expect(area.getByRole('alert')).toContainText('輸入已保留')
  await expect(area.getByLabel('調整後當次級數')).toHaveValue('9')
  await expect(area.getByLabel('調級原因（必填）')).toHaveValue('衝突保留原因')
  await expect(area.getByRole('button', { name: '儲存當次級數', exact: true })).toBeDisabled()
  await area.getByRole('button', { name: '讀取最新名單（保留草稿）' }).click()
  await expect(area.getByText('伺服器目前為 8 級／版本 3，草稿仍保留原始版本。')).toBeVisible()
  await page.getByRole('button', { name: new RegExp(name + '乙場') }).click()
  await expect(area.getByText('待儲存調整', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: new RegExp(name + '甲場') }).click()
  await expect(area.getByLabel('調級原因（必填）')).toHaveValue('衝突保留原因')
  await expect(area.getByText('編輯基準：7 級／版本 2；報名快照 2 級')).toBeVisible()
  await area.getByRole('button', { name: '放棄本筆草稿並重新載入' }).click()
  await expect(area.getByText('待儲存調整', { exact: true })).toHaveCount(0)
  await person.getByRole('button', { name: '調整級數' }).click()
  await area.getByLabel('調整後當次級數').selectOption('10')
  await area.getByLabel('調級原因（必填）').fill('失敗後可重試')
  const requests: { version: number; request_id: string }[] = []
  let fail = true
  await page.route(`**${mutationUrl}`, async route => {
    requests.push(route.request().postDataJSON())
    if (fail) await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成暫時無法儲存' }) })
    else await route.continue()
  })
  await area.getByRole('button', { name: '儲存當次級數', exact: true }).click()
  await expect(area.getByRole('alert')).toContainText('合成暫時無法儲存')
  await expect(area.getByLabel('調整後當次級數')).toHaveValue('10')
  await expect(area.getByLabel('調級原因（必填）')).toHaveValue('失敗後可重試')
  await area.screenshot({ path: testInfo.outputPath('levels-failed-input.png') })
  fail = false
  await area.getByRole('button', { name: '儲存當次級數', exact: true }).click()
  await expect(person).toContainText('當次級數 10 級')
  expect(requests).toHaveLength(2)
  expect(requests[0].request_id).toBe(requests[1].request_id)
  expect(requests.map(r => r.version)).toEqual([3, 3])
  await expect(page.locator('.registration-history')).toContainText('當次級數：8 → 10 級')
  const otherData = await (await page.request.get(`/api/admin/competitions/${other.id}`)).json()
  expect(otherData.registrations[0].competition_level).toBe(2)
  const member = (await (await page.request.get('/api/admin/members')).json()).find((m: { id: string }) => m.id === regs[0].member_id)
  expect(member.level).toBe(2)
  await expect(area.locator('.level-excluded').first()).toContainText('候補（級數唯讀）')
  await area.locator('.level-excluded').first().locator('summary').click()
  await expect(area.locator('.level-excluded').first().getByRole('button')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await area.screenshot({ path: testInfo.outputPath('levels-saved.png') })
  // History load failures must never show entries from another competition.
  await page.route(`**/api/admin/competitions/${other.id}/history`, route => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '合成歷史讀取失敗' }),
  }))
  await page.getByRole('button', { name: new RegExp(name + '乙場') }).click()
  const history = page.locator('.registration-history')
  if (!(await history.evaluate(element => (element as HTMLDetailsElement).open))) await history.locator('summary').click()
  await expect(history.getByRole('alert')).toContainText('合成歷史讀取失敗')
  await expect(history.locator('li')).toHaveCount(0)
})

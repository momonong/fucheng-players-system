import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const evidence = resolve('data/deployment-evidence-20260919')
const credentials = JSON.parse(await readFile(resolve(evidence, 'synthetic-admin.json'), 'utf8'))
const origin = process.env.FUCHENG_DRILL_ORIGIN || 'https://localhost:8447'
const runLabel = new URL(origin).port || '443'
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport, ignoreHTTPSErrors: true })
    const page = await context.newPage()
    await page.goto(origin + '/admin/competitions')
    await page.getByLabel('帳號', { exact: true }).fill(credentials.username)
    await page.getByLabel('密碼', { exact: true }).fill(credentials.password)
    const loginResponse = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST')
    await page.getByRole('button', { name: '登入', exact: true }).click()
    const login = await loginResponse
    if (login.status() !== 200) throw new Error(`Login status ${login.status()}: ${(await login.json()).detail}`)
    await page.getByRole('heading', { name: '比賽', exact: true }).waitFor()
    const cookie = (await context.cookies()).find(x => x.name === 'fucheng_session')
    assert(cookie.secure && cookie.httpOnly && cookie.sameSite === 'Lax')
    const auth = await (await page.request.get(origin + '/api/auth/me')).json()
    const headers = { Origin: origin, 'X-CSRF-Token': auth.csrf_token }
    const suffix = Date.now().toString()
    const memberName = `部署合成${name}${suffix}`
    const memberResponse = await page.request.post(origin + '/api/admin/members', { headers, data: { name: memberName, level: 3, diet: 'unset', is_active: true, distinguishing_note: '容器驗證' } })
    assert.equal(memberResponse.status(), 201)
    const member = await memberResponse.json()
    const competitionResponse = await page.request.post(origin + '/api/admin/competitions', { headers, data: { name: `容器部署驗證${name}${suffix}`, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: 4, status: 'open', notes: '純合成資料' } })
    assert.equal(competitionResponse.status(), 201)
    const competition = await competitionResponse.json()
    const publicContext = await browser.newContext({ viewport, ignoreHTTPSErrors: true })
    const publicPage = await publicContext.newPage()
    await publicPage.goto(origin + '/')
    await publicPage.screenshot({ path: resolve(evidence, `https-${runLabel}-${name}-home.png`), fullPage: true })
    await publicPage.goto(origin + '/members')
    await publicPage.getByText(memberName, { exact: true }).waitFor()
    await publicPage.goto(origin + '/register/' + competition.id)
    await publicPage.getByLabel('搜尋姓名').fill(memberName)
    await publicPage.getByRole('button', { name: new RegExp(memberName + '.*容器驗證') }).click()
    await publicPage.getByLabel('素食', { exact: true }).check()
    await publicPage.getByRole('button', { name: `確認以 ${memberName} 報名`, exact: true }).click()
    await publicPage.getByRole('region', { name: '報名結果' }).waitFor()
    assert.match(await publicPage.getByRole('region', { name: '報名結果' }).innerText(), /正取/)
    await publicPage.screenshot({ path: resolve(evidence, `https-${runLabel}-${name}-registration.png`), fullPage: true })
    await page.reload()
    await page.getByRole('button', { name: new RegExp(competition.name) }).click()
    const area = page.getByRole('region', { name: '當次比賽級數安排' })
    await area.getByRole('button', { name: '調整級數' }).click()
    await area.getByLabel('調整後當次級數').selectOption('7')
    await area.getByLabel('調級原因（必填）').fill('容器 HTTPS 合成驗證')
    await area.getByRole('button', { name: '儲存當次級數', exact: true }).click()
    await area.getByText('當次級數 7 級', { exact: true }).waitFor()
    await page.screenshot({ path: resolve(evidence, `https-${runLabel}-${name}-admin.png`), fullPage: true })
    const detail = await (await page.request.get(origin + `/api/admin/competitions/${competition.id}`)).json()
    const registration = detail.registrations.find(x => x.member_id === member.id)
    assert.equal(registration.competition_level, 7)
    assert.equal(registration.hard_level_snapshot, 3)
    assert.equal((await page.request.post(origin + '/api/auth/logout', { headers: { Origin: 'https://evil.example', 'X-CSRF-Token': auth.csrf_token } })).status(), 403)
    assert.equal((await page.request.post(origin + '/api/auth/logout', { headers: { Origin: origin } })).status(), 403)
    assert.equal((await page.request.get(origin + '/api/health', { headers: { Host: 'evil.example' } })).status(), 400)
    // Actual proxy sanitizes attacker supplied forwarding headers before app rate limiting.
    assert.equal((await page.request.get(origin + '/api/public/registration-session', { headers: { 'X-Forwarded-For': '203.0.113.199', 'X-Forwarded-Proto': 'http', Forwarded: 'for=203.0.113.199', 'CF-Connecting-IP': '203.0.113.199' } })).status(), 200)
    assert.equal((await page.request.post(origin + '/api/auth/logout', { headers })).status(), 204)
    assert.equal((await page.request.get(origin + '/api/auth/me')).status(), 401)
    results.push({ viewport: name, login: true, secure_cookie: true, public_home_members_registration: true, admin_level_change: true, snapshot_preserved: true, csrf_origin_host_rejection: true, logout: true, horizontal_overflow: await publicPage.evaluate(() => document.documentElement.scrollWidth > innerWidth) })
    await publicContext.close()
    await context.close()
  }
} finally {
  await browser.close()
  await writeFile(resolve(evidence, `https-browser-results-${runLabel}.json`), JSON.stringify(results, null, 2))
}
console.log(JSON.stringify(results))

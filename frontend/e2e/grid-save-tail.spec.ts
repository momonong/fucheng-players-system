import { writeFile } from 'node:fs/promises'
import { expect, test, type Page, type TestInfo } from '@playwright/test'

async function setup(page: Page, info: TestInfo) {
  await page.goto('/admin/competitions')
  await page.locator('form.login input[autocomplete="username"]').fill(`e2e-grid-${info.project.name}`)
  await page.locator('form.login input[type="password"]').fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.locator('form.login button').click()
  await expect(page.locator('nav.competition-mode')).toBeVisible()
  const me = await (await page.request.get('/api/auth/me')).json()
  const headers = { 'X-CSRF-Token': me.csrf_token }
  const name = `save-tail-${info.project.name}`
  const payload = { name, competition_date: '2099-09-20', registration_deadline: '2099-09-19T00:00:00+08:00', capacity: 9, status: 'open', notes: 'synthetic save layout test' }
  const comp = await (await page.request.post('/api/admin/competitions', { headers, data: payload })).json()
  const other = await (await page.request.post('/api/admin/competitions', { headers, data: { ...payload, name: `${name}-other` } })).json()
  const levels = [...Array(8).fill(1), 2]
  const registrations: any[] = []
  for (let i = 0; i < levels.length; i++) {
    const member = await (await page.request.post('/api/admin/members', { headers, data: { name: `Synthetic ${info.project.name} ${i}`, distinguishing_note: `save-tail-${i}`, level: levels[i], diet: 'unset', is_active: true } })).json()
    const response = await page.request.post(`/api/admin/competitions/${comp.id}/registrations`, { headers, data: { member_id: member.id, diet: 'unset', request_id: crypto.randomUUID() } })
    expect(response.status()).toBe(201)
    registrations.push(await response.json())
  }
  await page.reload()
  const area = page.locator('.arrangement-workspace')
  const selector = page.locator('nav.competition-mode select')
  await page.locator('nav.competition-mode button').first().click()
  const choose = async (second = false) => {
    await expect(selector.locator(`option[value="${second ? other.id : comp.id}"]`)).toHaveCount(1)
    await selector.selectOption(second ? other.id : comp.id)
    await expect(area.locator('.arrangement-toolbar h2')).toHaveText(second ? other.name : comp.name)
  }
  await choose()
  const endpoint = `/api/admin/competitions/${comp.id}/arrangement`
  const state = async () => (await page.request.get(endpoint)).json()
  await expect.poll(async () => !!(await state()).layout).toBe(true)
  const op = async (operation: any) => {
    const current = await state()
    const response = await page.request.post(`${endpoint}/operations`, { headers, data: { request_id: crypto.randomUUID(), state_token: current.state_token, operation } })
    expect(response.status(), await response.text()).toBe(200)
    return response.json()
  }
  const refresh = async () => {
    await page.reload()
    await page.locator('nav.competition-mode button').first().click()
    await expect(selector.locator(`option[value="${other.id}"]`)).toHaveCount(1)
    if (await selector.inputValue() === comp.id) await selector.selectOption(other.id)
    await selector.selectOption(comp.id)
    await expect(area.locator('.arrangement-toolbar h2')).toHaveText(comp.name)
    await expect.poll(async () => (await state()).layout?.rows.length).toBeGreaterThan(0)
  }
  const domRows = async () => area.locator('.arrangement-table tbody tr[data-row-id]').evaluateAll(rows => rows.map(row => ({ id: row.getAttribute('data-row-id'), role: row.getAttribute('data-row-role'), cellCount: row.querySelectorAll('td').length, playerIds: Array.from(row.querySelectorAll<HTMLElement>('[data-registration-id]')).map(cell => cell.dataset.registrationId) })))
  return { page, info, headers, comp, other, registrations, area, endpoint, state, op, refresh, domRows }
}

const facts = (layout: any) => ({ rows: layout.rows, columns: layout.columns, cells: layout.cells, merges: layout.merges, cell_shades: layout.cell_shades ?? [], header_merges: layout.header_merges ?? [] })
const positions = (layout: any) => layout.cells.filter((cell: any) => cell.kind === 'registration').map((cell: any) => [cell.registration_id, cell.row_id, cell.column_id]).sort((a: any[], b: any[]) => a[0].localeCompare(b[0]))
const activate = async (info: TestInfo, target: any) => info.project.name === 'mobile' ? target.tap() : target.click()

test('large save keeps exact rows and history; version heading stays inline', async ({ page }, info) => {
    test.setTimeout(150000)
    const s = await setup(page, info)
    const initial = await s.state()
    expect(initial.layout.rows).toHaveLength(8)
    const levelOne = initial.layout.columns.find((column: any) => column.kind === 'level' && column.level === 1)
    const firstEightIds = new Set(s.registrations.slice(0, 8).map(row => row.id))
    expect(initial.layout.cells.filter((cell: any) => cell.kind === 'registration' && cell.column_id === levelOne.id && firstEightIds.has(cell.registration_id))).toHaveLength(8)
    const positionsBeforeMove = positions(initial.layout)

    // A legitimate move into a full level grows one row, and the new row must hold the player.
    const legalMove = await s.op({ action: 'move_bottom', registration_id: s.registrations[8].id, level: 1 })
    expect(legalMove.layout.rows).toHaveLength(9)
    const undoReceipt = await s.op({ action: 'undo', target_request_id: legalMove.request_id })
    expect(facts(undoReceipt.layout)).toEqual(facts(initial.layout))
    const redoReceipt = await s.op({ action: 'redo', target_request_id: legalMove.request_id })
    expect(facts(redoReceipt.layout)).toEqual(facts(legalMove.layout))
    const legalRowId = redoReceipt.layout.rows.at(-1).id
    expect(legalMove.layout.cells.find((cell: any) => cell.registration_id === s.registrations[8].id).row_id).toBe(legalRowId)
    for (const [id, rowId, columnId] of positionsBeforeMove.filter(([id]) => id !== s.registrations[8].id)) {
      const movedPosition = positions(legalMove.layout).find((entry: any[]) => entry[0] === id)
      expect(movedPosition).toEqual([id, rowId, columnId])
    }

    // Add an empty shaded row and a separate text/shade/merge row. Neither is expendable.
    await s.op({ action: 'insert_row', before_id: null })
    await s.op({ action: 'insert_row', before_id: null })
    let layout = (await s.state()).layout
    const emptyTailId = layout.rows.at(-2).id
    const contentTailId = layout.rows.at(-1).id
    await s.op({ action: 'shade_row', axis_id: emptyTailId, shade: 1 })
    await s.op({ action: 'insert_column', before_id: null })
    await s.op({ action: 'insert_column', before_id: null })
    layout = (await s.state()).layout
    const textColumns = layout.columns.filter((column: any) => column.kind === 'text')
    const anchor = { row_id: contentTailId, column_id: textColumns.at(-2).id }
    const end = { row_id: contentTailId, column_id: textColumns.at(-1).id }
    await s.op({ action: 'text', target: anchor, text: 'user-tail-text' })
    await s.op({ action: 'merge', start: anchor, end })
    await s.op({ action: 'shade_row', axis_id: contentTailId, shade: 2 })
    await s.op({ action: 'shade_cells', start: { row_id: contentTailId, column_id: layout.columns[4].id }, end: { row_id: contentTailId, column_id: layout.columns[4].id }, shade: 3 })
    await s.refresh()

    const before = await s.state()
    expect(before.layout.rows.map((row: any) => row.id)).toEqual([...initial.layout.rows.map((row: any) => row.id), legalRowId, emptyTailId, contentTailId])
    expect(before.layout.cells.some((cell: any) => cell.row_id === emptyTailId)).toBe(false)
    expect(before.layout.rows.at(-2)).toMatchObject({ id: emptyTailId, role: 'body', shade: 1 })
    expect(before.layout.rows.at(-1)).toMatchObject({ id: contentTailId, role: 'body', shade: 2 })
    expect(before.layout.cells.some((cell: any) => cell.row_id === contentTailId && cell.text === 'user-tail-text')).toBe(true)
    expect(before.layout.merges.some((merge: any) => merge.start.row_id === contentTailId && merge.end.column_id === end.column_id)).toBe(true)
    expect(before.layout.cell_shades.some((shade: any) => shade.row_id === contentTailId && shade.shade === 3)).toBe(true)
    const beforeFacts = facts(before.layout)
    const beforePositions = positions(before.layout)
    const beforeDom = await s.domRows()
    expect(beforeDom).toHaveLength(before.layout.rows.length)
    await s.area.locator('.arrangement-table tbody tr[data-row-id]').last().scrollIntoViewIfNeeded()
    await page.screenshot({ path: info.outputPath('large-save-before.png'), fullPage: true })

    const firstPost = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/arrangement/versions'))
    const saveButton = s.area.locator('.arrangement-tools > button').nth(4)
    await expect(saveButton).toBeEnabled()
    await saveButton.click()
    const dialog = s.area.locator('dialog.arrangement-dialog')
    await dialog.locator('input').first().fill('tail-save-one')
    await dialog.locator('button').first().click()
    const postResponse = await firstPost
    const postRequest = postResponse.request().postDataJSON()
    const receipt = await postResponse.json()
    expect(postResponse.status()).toBe(200)
    await expect(s.area.locator('.arrangement-status')).toContainText('tail-save-one')
    await expect(s.area.locator('.arrangement-recovery')).toHaveCount(0)
    const afterPostGet = await s.state()
    const firstHistory = await (await page.request.get(`${s.endpoint}/versions/${receipt.id}`)).json()
    expect(facts(receipt.layout)).toEqual(beforeFacts)
    expect(facts(afterPostGet.layout)).toEqual(beforeFacts)
    expect(facts(firstHistory.layout)).toEqual(beforeFacts)
    expect(positions(afterPostGet.layout)).toEqual(beforePositions)
    expect(await s.domRows()).toEqual(beforeDom)
    await s.area.locator('.arrangement-table tbody tr[data-row-id]').last().scrollIntoViewIfNeeded()
    await page.screenshot({ path: info.outputPath('large-save-after-post-get.png'), fullPage: true })

    // An unchanged large save is rejected; it must not change current or history geometry.
    const noChangeResponse = await page.request.post(`${s.endpoint}/versions`, { headers: s.headers, data: { request_id: crypto.randomUUID(), state_token: afterPostGet.state_token, base_version_id: afterPostGet.latest.id } })
    expect(noChangeResponse.status()).toBe(422)
    const afterNoChange = await s.state()
    expect(facts(afterNoChange.layout)).toEqual(beforeFacts)
    expect(afterNoChange.latest.id).toBe(receipt.id)
    expect(afterNoChange.versions).toHaveLength(afterPostGet.versions.length)

    // A real subsequent edit and save still preserves the same row IDs and keeps v1 immutable.
    await s.op({ action: 'text', target: anchor, text: 'user-tail-text-two' })
    await s.op({ action: 'shade_row', axis_id: contentTailId, shade: 1 })
    await s.refresh()
    const beforeSecond = await s.state()
    const secondFacts = facts(beforeSecond.layout)
    const secondPost = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/arrangement/versions'))
    const secondSaveButton = s.area.locator('.arrangement-tools > button').nth(4)
    await expect(secondSaveButton).toBeEnabled()
    await secondSaveButton.click()
    const secondDialog = s.area.locator('dialog.arrangement-dialog')
    await secondDialog.locator('input').first().fill('tail-save-two')
    await secondDialog.locator('button').first().click()
    const secondPostResponse = await secondPost
    const secondReceipt = await secondPostResponse.json()
    expect(secondPostResponse.status()).toBe(200)
    await expect(s.area.locator('.arrangement-status')).toContainText('tail-save-two')
    const afterSecondGet = await s.state()
    const secondHistory = await (await page.request.get(`${s.endpoint}/versions/${secondReceipt.id}`)).json()
    const firstHistoryAgain = await (await page.request.get(`${s.endpoint}/versions/${receipt.id}`)).json()
    expect(facts(secondReceipt.layout)).toEqual(secondFacts)
    expect(facts(afterSecondGet.layout)).toEqual(secondFacts)
    expect(facts(secondHistory.layout)).toEqual(secondFacts)
    expect(facts(firstHistoryAgain.layout)).toEqual(beforeFacts)
    expect(afterSecondGet.layout.rows.map((row: any) => row.id)).toEqual(before.layout.rows.map((row: any) => row.id))
    expect(await s.domRows()).toHaveLength(beforeDom.length)

    // Browser refresh is a separate readback boundary.
    await s.refresh()
    const afterRefresh = await s.state()
    expect(facts(afterRefresh.layout)).toEqual(secondFacts)
    expect(await s.domRows()).toHaveLength(beforeDom.length)

    // Keep version history controls usable on desktop and mobile in the same header row.
    await activate(info, s.area.locator('.history-toggle'))
    const panel = s.area.locator('.arrangement-history')
    await expect(panel).toBeVisible()
    const header = panel.locator('.arrangement-panel-heading')
    const heading = header.locator('h3')
    const current = header.locator('button')
    await expect(current).toHaveAttribute('aria-pressed', 'true')
    const headingBox = await heading.boundingBox()
    const currentBox = await current.boundingBox()
    expect(headingBox).not.toBeNull()
    expect(currentBox).not.toBeNull()
    expect(Math.abs((headingBox!.y + headingBox!.height / 2) - (currentBox!.y + currentBox!.height / 2))).toBeLessThanOrEqual(4)
    expect(headingBox!.x + headingBox!.width).toBeLessThan(currentBox!.x)
    expect(currentBox!.height).toBeGreaterThanOrEqual(44)
    const firstVersion = panel.locator('.version-item').filter({ hasText: 'tail-save-one' })
    await activate(info, firstVersion)
    await expect(current).toHaveAttribute('aria-pressed', 'false')
    await activate(info, current)
    await expect(current).toHaveAttribute('aria-pressed', 'true')
    await page.screenshot({ path: info.outputPath('version-header-current.png'), fullPage: true })

    await writeFile(info.outputPath('large-save-observations.json'), JSON.stringify({
      database: process.env.FUCHENG_E2E_DATABASE_URL,
      project: info.project.name,
      initial: facts(initial.layout),
      legal_bottom_move: { rows: facts(legalMove.layout).rows, registration_positions: positions(legalMove.layout) },
      before_save_one: { layout: beforeFacts, positions: beforePositions, dom_rows: beforeDom },
      save_one: { status: postResponse.status(), request: { request_id: postRequest.request_id, base_version_id: postRequest.base_version_id, label: postRequest.label, state_token_present: !!postRequest.state_token }, receipt: facts(receipt.layout), get: facts(afterPostGet.layout), history: facts(firstHistory.layout), no_change_status: noChangeResponse.status() },
      before_save_two: secondFacts,
      save_two: { status: secondPostResponse.status(), receipt: facts(secondReceipt.layout), get: facts(afterSecondGet.layout), history: facts(secondHistory.layout), first_history_after_second_save: facts(firstHistoryAgain.layout) },
      refresh: facts(afterRefresh.layout),
    }, null, 2))
})

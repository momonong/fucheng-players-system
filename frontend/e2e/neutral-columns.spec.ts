import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
import { unzipSync, strFromU8 } from 'fflate'

const prefix=(process.env.FUCHENG_BASE_PATH??'').replace(/\/$/,'')
const url=(path:string)=>prefix+path
const pos=(state:any,id:string)=>{const c=state.layout.cells.find((v:any)=>v.registration_id===id);return {row_id:c.row_id,column_id:c.column_id}}

async function drag(page:Page,info:TestInfo,from:any,to:any) {
  await to.scrollIntoViewIfNeeded();await from.scrollIntoViewIfNeeded()
  const a=(await from.boundingBox())!,b=(await to.boundingBox())!
  const start={x:a.x+a.width/2,y:a.y+a.height/2},finish={x:b.x+b.width/2,y:b.y+b.height/2}
  if(info.project.name==='mobile') {
    const cdp=await page.context().newCDPSession(page)
    try {
      await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]})
      await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[finish]})
      await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent','move_empty')
      await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
    } finally { await cdp.detach() }
  } else {
    await page.mouse.move(start.x,start.y);await page.mouse.down()
    await page.mouse.move(finish.x,finish.y,{steps:10})
    await expect(page.locator('[data-drag-intent]')).toHaveAttribute('data-drag-intent','move_empty')
    await page.mouse.up()
  }
}

test('直接增空白欄放人保留級數、回數字欄調級、復原與完整歷史匯出',async({page},info)=>{
  test.setTimeout(90_000)
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message))
  await page.goto(url('/admin/competitions'))
  await page.getByLabel('帳號',{exact:true}).fill('e2e-admin')
  await page.getByLabel('密碼',{exact:true}).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button',{name:'登入',exact:true}).click()
  await expect(page.getByRole('button',{name:'登出',exact:true})).toBeVisible()
  const me=await(await page.request.get(url('/api/auth/me'))).json(),headers={'X-CSRF-Token':me.csrf_token}
  const compResponse=await page.request.post(url('/api/admin/competitions'),{headers,data:{name:`合成普通欄-${info.project.name}`,competition_date:'2099-10-22',registration_deadline:'2099-10-21T00:00:00+08:00',capacity:5,status:'open',notes:'合成空白欄驗證'}})
  expect(compResponse.status()).toBe(201);const comp=await compResponse.json()
  const members:any[]=[],people:any[]=[]
  for(const [i,level] of [10,9].entries()) {
    const created=await page.request.post(url('/api/admin/members'),{headers,data:{name:`合成空白欄選手${i+1}`,distinguishing_note:'純合成資料',level,diet:i===0?'vegetarian':'omnivore',is_active:true}})
    expect(created.status()).toBe(201);const member=await created.json();members.push(member)
    const registered=await page.request.post(url(`/api/admin/competitions/${comp.id}/registrations`),{headers,data:{member_id:member.id,diet:i===0?'vegetarian':'omnivore',request_id:crypto.randomUUID()}})
    expect(registered.status()).toBe(201);people.push(await registered.json())
  }
  await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(comp.id)
  const area=page.getByRole('region',{name:'當次比賽級數安排'}),endpoint=url(`/api/admin/competitions/${comp.id}/arrangement`)
  const state=async()=>await(await page.request.get(endpoint)).json()
  const idle=async()=>{await expect(area.locator('.cell-grip').first()).toBeEnabled();await expect(area.locator('.arrangement-recovery')).toHaveCount(0)}
  await expect.poll(async()=>!!(await state()).layout).toBe(true)
  const initial=await state()
  await expect(area.getByLabel('加回級數欄',{exact:true})).toHaveCount(0)
  await area.getByRole('button',{name:'＋ 新增空白欄',exact:true}).click();await idle()
  const inserted=await state(),column=inserted.layout.columns.at(-1)
  expect(column).toMatchObject({kind:'text',level:null,title:''})
  expect(inserted.layout.columns).toHaveLength(11);expect(inserted.layout.schema_version).toBe(2)
  expect(inserted.rows).toEqual(initial.rows)
  const heading=area.locator(`[data-grid-header="${column.id}"]`)
  await heading.getByRole('button').dblclick();await page.getByLabel('直接編輯文字').fill('自由安排')
  await page.getByLabel('直接編輯文字').press('Enter');await idle();await expect(heading).toHaveText('自由安排')
  const target={row_id:inserted.layout.rows[2].id,column_id:column.id}
  const slot=(point:any)=>area.locator(`td[data-grid-cell="${point.row_id}/${point.column_id}"]`)
  const grip=()=>area.locator(`[data-registration-id="${people[0].id}"] ${info.project.name==='mobile'?'.cell-name':'.cell-grip'}`)
  await drag(page,info,grip(),slot(target));await idle()
  await expect.poll(async()=>pos(await state(),people[0].id)).toEqual(target)
  const neutral=await state();expect(neutral.rows.find((r:any)=>r.registration_id===people[0].id).competition_level).toBe(10)
  // A deliberate level edit in a neutral column preserves the spatial arrangement.
  const person=neutral.rows.find((r:any)=>r.registration_id===people[0].id)
  const adjusted=await page.request.put(url(`/api/admin/registrations/${person.registration_id}/level`),{headers,data:{version:person.version,competition_level:3,request_id:crypto.randomUUID()}})
  expect(adjusted.status()).toBe(200)
  expect(pos(await state(),people[0].id)).toEqual(target)
  await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(comp.id);await idle()
  // Moving back to a numeric column keeps its established explicit adjustment behavior.
  const numeric={row_id:inserted.layout.rows[3].id,column_id:inserted.layout.columns.find((c:any)=>c.level===10).id}
  await drag(page,info,grip(),slot(numeric));await idle()
  await expect.poll(async()=>(await state()).rows.find((r:any)=>r.registration_id===people[0].id).competition_level).toBe(10)
  await page.keyboard.press('Control+z');await idle()
  await expect.poll(async()=>pos(await state(),people[0].id)).toEqual(target)
  expect((await state()).rows.find((r:any)=>r.registration_id===people[0].id).competition_level).toBe(3)
  await page.keyboard.press('Control+Shift+z');await idle()
  await expect.poll(async()=>pos(await state(),people[0].id)).toEqual(numeric)
  await page.keyboard.press('Control+z');await idle()
  const savedState=await state();expect(pos(savedState,people[0].id)).toEqual(target)
  await area.getByRole('button',{name:'保存完整安排',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'保存完整安排'})
  await dialog.getByLabel('版本名稱',{exact:true}).fill('空白欄完整快照')
  await dialog.getByRole('button',{name:'保存',exact:true}).click()
  await expect.poll(async()=>(await state()).latest?.label).toBe('空白欄完整快照')
  const saved=await state();await page.reload();await page.getByLabel('選擇比賽',{exact:true}).selectOption(comp.id)
  await idle();expect((await state()).layout).toEqual(saved.layout)
  await area.getByRole('button',{name:'歷史',exact:true}).click()
  await page.locator('.version-item').filter({hasText:'空白欄完整快照'}).click()
  await expect(area.getByRole('button',{name:'＋ 新增空白欄',exact:true})).toHaveCount(0)
  await expect(area.locator(`[data-registration-id="${people[0].id}"]`)).toBeVisible()
  expect(await slot(target).getAttribute('data-drop-enabled')).toBe('false')
  await page.evaluate(()=>window.print=()=>{})
  await area.getByRole('button',{name:'列印安排',exact:true}).click()
  await expect(page.locator('[data-print-header]')).toHaveCount(11)
  await expect(page.locator('[data-print-registration]')).toHaveCount(2)
  await expect(page.locator(`[data-print-cell="${target.row_id}/${target.column_id}"]`)).toContainText(members[0].name)
  await expect(page.locator('.print-vegetarian')).toHaveCount(1)
  if(info.project.name==='desktop')await page.pdf({path:info.outputPath('neutral-columns.pdf'),preferCSSPageSize:true})
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')))
  const downloading=page.waitForEvent('download');await area.getByRole('button',{name:'匯出 Excel',exact:true}).click()
  const file=await downloading;expect(await file.failure()).toBeNull()
  const xlsx=info.outputPath('neutral-columns.xlsx');await file.saveAs(xlsx)
  const archive=unzipSync(await readFile(xlsx)),xml=Object.values(archive).map(bytes=>strFromU8(bytes)).join('\n')
  expect(xml).toContain(members[0].name);expect(xml).toContain(members[1].name);expect(xml).toContain('自由安排')
  expect(xml).toContain('[素]')
  const detail=await(await page.request.get(url(`/api/admin/competitions/${comp.id}`))).json()
  for(const [i,person] of people.entries())expect(detail.registrations.find((r:any)=>r.id===person.id).hard_level_snapshot).toBe(members[i].level)
  expect((await(await page.request.get(url('/api/admin/members'))).json()).filter((m:any)=>members.some(member=>member.id===m.id)).map((m:any)=>[m.id,m.level]).sort()).toEqual(members.map(m=>[m.id,m.level]).sort())
  expect(errors).toEqual([])
  await writeFile(info.outputPath('neutral-columns-state.json'),JSON.stringify({initial,final:saved,position:target,memberLevelsPreserved:true,hardSnapshotsPreserved:true,errors},null,2))
  await page.screenshot({path:info.outputPath('neutral-columns.png'),fullPage:true})
})

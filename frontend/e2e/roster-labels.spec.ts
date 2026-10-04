import { expect, test } from '@playwright/test'
import { rosterLocations } from '../src/arrangementRoster'
import type { ArrangementRow, GridLayout } from '../src/types'

function fixture() {
  const rows: ArrangementRow[] = [
    { registration_id: 'a', member_id: 'ma', member_name: '周文軒', distinguishing_note: null, competition_level: 3, member_level: 9, queue_sequence: 2, version: 1, diet: 'omnivore' },
    { registration_id: 'b', member_id: 'mb', member_name: '合成乙', distinguishing_note: '東區', competition_level: 7, member_level: 1, queue_sequence: 1, version: 1, diet: 'vegetarian' },
  ]
  const layout: GridLayout = {
    schema_version: 1,
    rows: [{ id: 'h1', role: 'header' }, { id: 'h2', role: 'header' }, { id: 'r1', role: 'body' }, { id: 'r2', role: 'body' }],
    columns: [
      { id: 'left', kind: 'text', level: null },
      ...Array.from({ length: 10 }, (_, i) => ({ id: `c${i + 1}`, kind: 'level' as const, level: i + 1 })),
      { id: 'right', kind: 'text', level: null },
    ],
    cells: [
      { kind: 'registration', row_id: 'r1', column_id: 'c3', registration_id: 'a' },
      { kind: 'registration', row_id: 'r1', column_id: 'c7', registration_id: 'b' },
    ], merges: [],
  }
  return { rows, layout }
}

test('欄名保留多層及非 anchor 合併文字，固定表頭遵循自訂／空白／預設語意', () => {
  const { rows, layout } = fixture()
  layout.cells.push({ kind: 'text', row_id: 'h1', column_id: 'c8', text: '乙組' }, { kind: 'text', row_id: 'h2', column_id: 'c7', text: '下午場' })
  layout.merges.push({ id: 'group', start: { row_id: 'h1', column_id: 'c3' }, end: { row_id: 'h1', column_id: 'c8' } })
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '下午場'])
  layout.columns.find(c => c.id === 'c7')!.title = '自由組'
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '下午場', '自由組'])
  layout.header_merges = [{ id: 'fixed', start_column_id: 'c7', end_column_id: 'c8', title: '決賽' }]
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '下午場', '決賽'])
  layout.header_merges[0].title = ''
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '下午場'])
  layout.header_merges[0].title = null
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '下午場', '自由組 8 級'])
})

test('跨列合併欄名只出現一次；相同文字的不同層仍各自保留', () => {
  const { rows, layout } = fixture()
  layout.cells.push({ kind: 'text', row_id: 'h2', column_id: 'c7', text: '乙組' })
  layout.merges.push({ id: 'group', start: { row_id: 'h1', column_id: 'c7' }, end: { row_id: 'h2', column_id: 'c7' } })
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組'])
  layout.merges = []
  layout.cells.push({ kind: 'text', row_id: 'h1', column_id: 'c7', text: '乙組' })
  expect(rosterLocations(rows, layout).get('b')?.columnNames).toEqual(['乙組', '乙組'])
})

test('隊名依左側最近非空文字欄，否則右側；跨列合併覆蓋整段', () => {
  const { rows, layout } = fixture()
  layout.columns.splice(5, 0, { id: 'middle', kind: 'text', level: null })
  layout.cells.push(
    { kind: 'text', row_id: 'r2', column_id: 'left', text: '釋教甲隊' },
    { kind: 'text', row_id: 'r1', column_id: 'middle', text: '自組乙隊' },
    { kind: 'text', row_id: 'r1', column_id: 'right', text: '右側隊' },
    { kind: 'text', row_id: 'r1', column_id: 'c6', text: '一般備註不當隊名' },
  )
  layout.merges.push({ id: 'team', start: { row_id: 'r1', column_id: 'left' }, end: { row_id: 'r2', column_id: 'left' } })
  expect(rosterLocations(rows, layout).get('a')?.teamName).toBe('釋教甲隊')
  expect(rosterLocations(rows, layout).get('b')?.teamName).toBe('自組乙隊')
  layout.cells = layout.cells.filter(c => c.column_id !== 'middle')
  expect(rosterLocations(rows, layout).get('b')?.teamName).toBe('釋教甲隊')
  layout.cells = layout.cells.filter(c => c.column_id !== 'left')
  expect(rosterLocations(rows, layout).get('b')?.teamName).toBe('右側隊')
})

test('無隊名由最高當次級數取姓名末兩字，姓名重複仍以 ID 區分，換列不沿用隊長', () => {
  const { rows, layout } = fixture(), original = structuredClone({ rows, layout })
  expect(rosterLocations(rows, layout).get('b')).toMatchObject({ teamName: '文軒隊', teamSource: 'captain' })
  expect({ rows, layout }).toEqual(original)
  layout.cells.find(c => c.kind === 'registration' && c.registration_id === 'a')!.row_id = 'r2'
  expect(rosterLocations(rows, layout).get('b')?.teamName).toBe('成乙隊')
  rows[1].member_name = '李'
  expect(rosterLocations(rows, layout).get('b')?.teamName).toBe('李隊')
  rows[1].member_name = rows[0].member_name
  expect(rosterLocations(rows, layout).size).toBe(2)
  expect(rosterLocations(original.rows, original.layout).get('b')?.teamName).toBe('文軒隊')
})

test('舊版或沒有格位的選手保持未知，不從目前隊伍回填', () => {
  const { rows, layout } = fixture()
  expect(rosterLocations(rows, null).get('b')).toEqual({ columnNames: [], teamName: null, teamSource: 'unknown' })
  layout.cells = layout.cells.filter(c => c.kind !== 'registration' || c.registration_id !== 'b')
  expect(rosterLocations(rows, layout).get('b')).toEqual({ columnNames: [], teamName: null, teamSource: 'unknown' })
})

import { headerCells } from './gridHeader'
import type { ArrangementRow, GridLayout } from './types'

type TextRegion = { id: string; top: number; bottom: number; left: number; right: number; text: string }
export type RosterLocation = { columnNames: string[]; teamName: string | null; teamSource: 'written' | 'captain' | 'unknown' }

// Read labels from the displayed snapshot only. A merge's text may live away from its anchor.
export function rosterLocations(rows: ArrangementRow[], layout: GridLayout | null): Map<string, RosterLocation> {
  const result = new Map(rows.map(row => [row.registration_id, { columnNames: [], teamName: null, teamSource: 'unknown' } as RosterLocation]))
  if (!layout) return result
  const rowIndex = new Map(layout.rows.map((row, i) => [row.id, i]))
  const columnIndex = new Map(layout.columns.map((column, i) => [column.id, i]))
  const people = new Map(rows.map(row => [row.registration_id, row]))
  const textCells = new Map<string, string>(layout.cells.flatMap(cell => cell.kind === 'text' ? [[`${cell.row_id}/${cell.column_id}`, cell.text] as const] : []))
  const covered = new Set<string>(), regions: TextRegion[] = []
  for (const merge of layout.merges) {
    const top = rowIndex.get(merge.start.row_id), bottom = rowIndex.get(merge.end.row_id)
    const left = columnIndex.get(merge.start.column_id), right = columnIndex.get(merge.end.column_id)
    if (top === undefined || bottom === undefined || left === undefined || right === undefined) continue
    const parts: string[] = []
    for (let r = top; r <= bottom; r++) for (let c = left; c <= right; c++) {
      const key = `${layout.rows[r].id}/${layout.columns[c].id}`
      covered.add(key)
      const text = textCells.get(key)?.trim()
      if (text) parts.push(text)
    }
    if (parts.length) regions.push({ id: merge.id, top, bottom, left, right, text: parts.join(' ') })
  }
  for (const cell of layout.cells) {
    if (cell.kind !== 'text' || !cell.text.trim() || covered.has(`${cell.row_id}/${cell.column_id}`)) continue
    const r = rowIndex.get(cell.row_id), c = columnIndex.get(cell.column_id)
    if (r !== undefined && c !== undefined) regions.push({ id: `${cell.row_id}/${cell.column_id}`, top: r, bottom: r, left: c, right: c, text: cell.text.trim() })
  }
  const headers = new Map<number, TextRegion[]>(), rowNames = new Map<number, TextRegion[]>()
  for (const region of regions) {
    const axes = layout.rows.slice(region.top, region.bottom + 1)
    if (axes.every(row => row.role === 'header')) {
      for (let c = region.left; c <= region.right; c++) headers.set(c, [...(headers.get(c) ?? []), region])
    } else if (axes.every(row => row.role === 'body') && layout.columns.slice(region.left, region.right + 1).some(c => c.kind === 'text')) {
      for (let r = region.top; r <= region.bottom; r++) rowNames.set(r, [...(rowNames.get(r) ?? []), region])
    }
  }
  const positions = layout.cells.flatMap(cell => cell.kind === 'registration' && people.has(cell.registration_id) ? [cell] : [])
  const captains = new Map<string, ArrangementRow>()
  for (const cell of positions) {
    if (layout.rows[rowIndex.get(cell.row_id) ?? -1]?.role !== 'body') continue
    const person = people.get(cell.registration_id)!, captain = captains.get(cell.row_id)
    if (!captain || person.competition_level < captain.competition_level || person.competition_level === captain.competition_level && person.queue_sequence < captain.queue_sequence) captains.set(cell.row_id, person)
  }
  const headings = headerCells(layout)
  for (const cell of positions) {
    const r = rowIndex.get(cell.row_id), c = columnIndex.get(cell.column_id), person = people.get(cell.registration_id)!
    if (r === undefined || c === undefined || layout.rows[r].role !== 'body') continue
    const columnNames = (headers.get(c) ?? []).filter(region => region.bottom < r).sort((a, b) => a.top - b.top || a.left - b.left).map(region => region.text)
    const heading = headings[c].title.trim()
    // Level is shown separately; retain custom names without repeating an unchanged level label.
    if (heading && heading.replace(/\s/g, '') !== `${person.competition_level}級`) columnNames.push(heading)
    const names = rowNames.get(r) ?? []
    const written = names.filter(name => name.right < c).sort((a, b) => b.right - a.right)[0]
      ?? names.filter(name => name.left > c).sort((a, b) => a.left - b.left)[0]
    const captain = captains.get(cell.row_id)
    const name = captain?.member_name.trim()
    result.set(cell.registration_id, {
      columnNames,
      teamName: written?.text ?? (name ? `${Array.from(name).slice(-2).join('')}隊` : null),
      teamSource: written ? 'written' : name ? 'captain' : 'unknown',
    })
  }
  return result
}

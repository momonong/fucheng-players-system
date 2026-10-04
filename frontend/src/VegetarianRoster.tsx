import { useEffect, useRef, useState } from 'react'
import type { ArrangementRow, GridLayout } from './types'

// Derive teams only from this displayed layout; historical rows must never use today's positions.
export function VegetarianRoster({ rows, layout, historical }: { rows: ArrangementRow[]; layout: GridLayout | null; historical: boolean }) {
  const [open, setOpen] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (open) dialog.current?.showModal() }, [open])
  const people = new Map(rows.map(row => [row.registration_id, row]))
  const positions = new Map(layout?.cells.flatMap(cell => cell.kind === 'registration' ? [[cell.registration_id, cell] as const] : []))
  const captainColumn = layout?.columns.find(column => column.kind === 'level' && column.level === 1)
  const captains = new Map(layout?.cells.flatMap(cell => cell.kind === 'registration' && cell.column_id === captainColumn?.id ? [[cell.row_id, people.get(cell.registration_id)] as const] : []))
  const vegetarians = rows.filter(row => row.diet === 'vegetarian').sort((a, b) => a.competition_level - b.competition_level || a.queue_sequence - b.queue_sequence)
  const unknown = rows.filter(row => row.diet === null).length
  const label = (row: ArrangementRow) => `${row.member_name}${row.distinguishing_note ? `（${row.distinguishing_note}）` : ''}`
  return <>
    <button className="secondary vegetarian-roster-trigger" type="button" aria-label="查看素食人員名單" title="查看素食人員名單" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="7" cy="7" r="3"/><path d="M2 19v-2a5 5 0 0 1 10 0v2M15 6h7M15 11h7M15 16h7"/></svg>
    </button>
    {open && <dialog ref={dialog} className="arrangement-dialog vegetarian-roster-dialog" aria-labelledby="vegetarian-roster-title" onCancel={() => setOpen(false)}>
      <div className="section-title"><h3 id="vegetarian-roster-title">{historical ? '此版本' : '本場'}素食名單・{vegetarians.length} 人</h3><button className="secondary" autoFocus onClick={() => setOpen(false)}>關閉名單</button></div>
      <p>隊長依同一橫列的 1 級選手顯示；名單不受姓名搜尋影響。</p>
      {!layout && <p className="notice">此版本未記錄格位，無法判定隊長。</p>}
      {!!unknown && <p>{unknown} 人的餐食未記錄，未列入素食名單。</p>}
      <ul className="vegetarian-roster-list">{vegetarians.map(row => {
        const position = positions.get(row.registration_id)
        const captain = position ? captains.get(position.row_id) : undefined
        const captainText = captain ? `${label(captain)} 隊長` : layout && position ? '隊長未安排' : '隊長未知'
        return <li key={row.registration_id}><span>{row.competition_level} 級</span><span>{captainText}</span><strong>{label(row)}</strong></li>
      })}</ul>
      {!vegetarians.length && <p>沒有已記錄的素食人員。</p>}
    </dialog>}
  </>
}

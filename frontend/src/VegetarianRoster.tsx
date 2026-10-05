import { useEffect, useRef, useState } from 'react'
import type { ArrangementRow, GridLayout } from './types'
import { rosterLocations } from './arrangementRoster'

// Derive teams only from this displayed layout; historical rows must never use today's positions.
export function VegetarianRoster({ rows, layout, historical }: { rows: ArrangementRow[]; layout: GridLayout | null; historical: boolean }) {
  const [open, setOpen] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (open) dialog.current?.showModal() }, [open])
  const locations = rosterLocations(rows, layout)
  const vegetarians = rows.filter(row => row.diet === 'vegetarian').sort((a, b) => a.competition_level - b.competition_level || a.queue_sequence - b.queue_sequence)
  const unknown = rows.filter(row => row.diet === null).length
  const label = (row: ArrangementRow) => `${row.member_name}${row.distinguishing_note ? `（${row.distinguishing_note}）` : ''}`
  return <>
    <button className="secondary vegetarian-roster-trigger" type="button" aria-label="查看素食人員名單" title="查看素食人員名單" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <span className="vegetarian-roster-badge"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="7" cy="7" r="3"/><path d="M2 19v-2a5 5 0 0 1 10 0v2M15 6h7M15 11h7M15 16h7"/></svg></span>
    </button>
    {open && <dialog ref={dialog} className="arrangement-dialog vegetarian-roster-dialog" aria-labelledby="vegetarian-roster-title" onCancel={() => setOpen(false)}>
      <div className="section-title"><h3 id="vegetarian-roster-title">{historical ? '此版本' : '本場'}素食名單・{vegetarians.length} 人</h3><button className="secondary vegetarian-roster-close" aria-label="關閉名單" title="關閉名單" autoFocus onClick={() => setOpen(false)}>×</button></div>
      <p className="vegetarian-roster-help">依表格欄名與隊名列出，不受姓名搜尋影響。</p>
      {!layout && <p className="notice">此版本未記錄格位，欄名與隊伍未知。</p>}
      {!!unknown && <p>{unknown} 人的餐食未記錄，未列入素食名單。</p>}
      <ul className="vegetarian-roster-list">{vegetarians.map(row => {
        const location = locations.get(row.registration_id)!
        return <li key={row.registration_id}><strong className="vegetarian-roster-person">{label(row)}</strong><div className="vegetarian-roster-columns"><span>{row.competition_level} 級</span>{location.columnNames.map((name, i) => <span key={i}>{name}</span>)}</div><span className="vegetarian-roster-team">{location.teamName ?? '隊伍未知'}</span></li>
      })}</ul>
      {!vegetarians.length && <p>沒有已記錄的素食人員。</p>}
    </dialog>}
  </>
}

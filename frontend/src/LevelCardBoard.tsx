import { useEffect, useRef, useState } from 'react'
import type { ArrangementRow } from './types'
import { useLevelCardDrag } from './useLevelCardDrag'
import type { PendingMove } from './useArrangementWorkspace'

export type ArrangementChange = { kind: 'level' | 'added' | 'removed'; row: ArrangementRow; before?: number; after?: number }
export function arrangementChanges(rows: ArrangementRow[], baseline: ArrangementRow[]): ArrangementChange[] {
  const old = new Map(baseline.map(row => [row.registration_id, row]))
  const current = new Map(rows.map(row => [row.registration_id, row]))
  const result: ArrangementChange[] = []
  for (const row of rows) {
    const before = old.get(row.registration_id)
    if (!before) result.push({ kind: 'added', row, after: row.competition_level })
    else if (before.competition_level !== row.competition_level) result.push({ kind: 'level', row, before: before.competition_level, after: row.competition_level })
  }
  for (const row of baseline) if (!current.has(row.registration_id)) result.push({ kind: 'removed', row, before: row.competition_level })
  return result
}
export const changeText = (change: ArrangementChange) => change.kind === 'level' ? `${change.before} → ${change.after} 級` : change.kind === 'added' ? `新增至 ${change.after} 級` : `移出（原 ${change.before} 級）`
const levels = Array.from({ length: 10 }, (_, index) => index + 1)

export function LevelCardBoard({ rows, changes, search, readonly, pending, onMove }: {
  rows: ArrangementRow[]; changes: ArrangementChange[]; search: string; readonly: boolean
  pending: Record<string, PendingMove>; onMove: (row: ArrangementRow, level: number) => void
}) {
  const [selected, setSelected] = useState<ArrangementRow | null>(null)
  const [target, setTarget] = useState('1')
  const [recent, setRecent] = useState<string | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const changeMap = new Map(changes.map(change => [change.row.registration_id, change]))
  const picked = selected ? rows.find(row => row.registration_id === selected.registration_id) : null
  const displayLevel = (row: ArrangementRow) => pending[row.registration_id]?.level ?? row.competition_level
  function pick(id: string) {
    const row = rows.find(item => item.registration_id === id)
    if (row) { setSelected(row); setTarget(String(displayLevel(row))) }
  }
  function move(id: string, level: number) {
    const row = rows.find(item => item.registration_id === id)
    if (!row || readonly || pending[id]) return
    if (row.competition_level !== level) { setRecent(id); onMove(row, level) }
    setSelected(null)
  }
  useEffect(() => { if (selected) dialog.current?.showModal() }, [selected])
  useEffect(() => { if (recent) { const timer = setTimeout(() => setRecent(null), 900); return () => clearTimeout(timer) } }, [recent])
  const { drag, holding, start } = useLevelCardDrag(move, pick, !readonly)
  const columns = levels.map(level => rows.filter(row => displayLevel(row) === level && `${row.member_name} ${row.distinguishing_note ?? ''}`.includes(search.trim())).sort((a, b) => a.queue_sequence - b.queue_sequence))
  const height = Math.max(8, ...columns.map(column => column.length))
  return <>
    <div className={`arrangement-table-scroll ${drag ? 'is-dragging' : ''}`} tabIndex={0} role="region" aria-label="級數表格，可水平捲動">
      <table className="arrangement-table" aria-label="當次級數表"><thead><tr>{levels.map(level => <th scope="col" key={level} data-drop-level={level} data-drop-enabled={!readonly}>{level} 級</th>)}</tr></thead>
        <tbody>{Array.from({ length: height }, (_, index) => <tr key={index}>{levels.map((level, column) => {
          const row = columns[column][index]
          const change = row && changeMap.get(row.registration_id)
          const operation = row && pending[row.registration_id]
          return <td key={level} data-drop-level={level} data-drop-enabled={!readonly} className={drag?.target === level ? 'drop-target-active' : ''}>
            {row && <div data-registration-id={row.registration_id} className={`arrangement-cell ${change ? `net-${change.kind}` : ''} ${operation ? 'cell-pending' : ''} ${recent === row.registration_id ? 'just-moved' : ''}`}>
              {!readonly && <button className="cell-grip" type="button" disabled={!!operation} aria-label={`拖曳 ${row.member_name} ${row.distinguishing_note || ''}`}
                onPointerDown={event => start(event, { id: row.registration_id, name: row.member_name })}
                onClick={event => { if (event.detail === 0) pick(row.registration_id) }} onContextMenu={event => event.preventDefault()}>{holding === row.registration_id ? '…' : '⠿'}</button>}
              <button className="cell-name" type="button" aria-label={`${row.member_name}${row.distinguishing_note ? `・${row.distinguishing_note}` : ''}${change ? `・${changeText(change)}` : ''}，查看或移動`}
                title={`${row.member_name}${row.distinguishing_note ? `・${row.distinguishing_note}` : ''}${change ? `・${changeText(change)}` : ''}`}
                onPointerDown={event => { if (event.pointerType === 'mouse' && !readonly && !operation) start(event, { id: row.registration_id, name: row.member_name }) }}
                onClick={event => { if (event.detail === 0 || readonly || event.nativeEvent instanceof PointerEvent && event.nativeEvent.pointerType === 'touch') pick(row.registration_id) }}>
                <span>{row.member_name}</span>{row.distinguishing_note && <small>{row.distinguishing_note}</small>}
              </button>
              {change && <span className="cell-change" aria-label={changeText(change)}>{change.kind === 'added' ? '+' : `${change.before}→${change.after}`}</span>}
              {operation && <span className="cell-save-state" aria-label={operation.status === 'saving' ? '儲存中' : '尚未確認儲存'}>{operation.status === 'saving' ? '…' : '!'}</span>}
            </div>}
          </td>
        })}</tr>)}</tbody></table>
    </div>
    {drag && <div className="level-drag-ghost" aria-hidden="true" style={{ left: Math.min(drag.x + 12, window.innerWidth - 200), top: Math.max(8, Math.min(drag.y + 12, window.innerHeight - 90)) }}><strong>{drag.card.name}</strong><span>{drag.target ? `放到 ${drag.target} 級` : '移到目的欄'}</span></div>}
    {selected && <dialog ref={dialog} className="arrangement-dialog" aria-labelledby="cell-detail-title" onCancel={() => setSelected(null)}>
      <h3 id="cell-detail-title">{selected.member_name}</h3><p>{selected.distinguishing_note || '無辨識註記'}</p><p>順位 {selected.queue_sequence}・目前 {picked ? displayLevel(picked) : selected.competition_level} 級</p>
      {picked && !readonly && !pending[picked.registration_id] && <><label>移到級數<select value={target} onChange={event => setTarget(event.target.value)}>{levels.map(level => <option key={level} value={level}>{level} 級</option>)}</select></label><button onClick={() => move(picked.registration_id, Number(target))}>移動</button></>}
      <button className="secondary" onClick={() => setSelected(null)}>關閉</button>
    </dialog>}
  </>
}

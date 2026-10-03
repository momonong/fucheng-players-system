import { useEffect, useRef, useState } from 'react'
import { MemberLevelHistory } from './MemberLevelHistory'
import type { ArrangementRow, GridLayout, GridOperation, GridPoint } from './types'

const identity = (row: ArrangementRow) => `${row.member_name}${row.distinguishing_note ? `・${row.distinguishing_note}` : ''}（順位 ${row.queue_sequence}）`
const key = (point: GridPoint) => `${point.row_id}/${point.column_id}`
type Method = 'move_bottom' | 'swap' | 'insert' | 'move_empty'
type Selection = { row: ArrangementRow; rows: ArrangementRow[]; layout: GridLayout | null; token: string }

export function MobileArrangement({ rows, layout, stateToken, search, vegetarian, readonly, busy, competitionId, historical, onOperate, confirmedRequest, canUndo, canRedo, onUndo, onRedo }: {
  rows: ArrangementRow[]; layout: GridLayout | null; stateToken: string; search: string; vegetarian: boolean
  readonly: boolean; busy: boolean; competitionId: string; historical: boolean
  onOperate: (operation: GridOperation, token: string) => void; confirmedRequest?: string
  canUndo: boolean; canRedo: boolean; onUndo: () => void; onRedo: () => void
}) {
  const [level, setLevel] = useState('')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [method, setMethod] = useState<Method>('move_bottom')
  const [destinationLevel, setDestinationLevel] = useState('1')
  const [person, setPerson] = useState('')
  const [empty, setEmpty] = useState('')
  const [side, setSide] = useState<'before' | 'after'>('before')
  const submitted = useRef<{ receipt?: string } | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const blocked = readonly || busy || !layout
  useEffect(() => { if (selection) dialog.current?.showModal() }, [selection])
  useEffect(() => {
    if (submitted.current && confirmedRequest && confirmedRequest !== submitted.current.receipt) {
      submitted.current = null
      setSelection(null)
    }
  }, [confirmedRequest])
  function choose(row: ArrangementRow) {
    submitted.current = null
    setMethod('move_bottom'); setDestinationLevel(String(row.competition_level)); setPerson(''); setEmpty(''); setSide('before')
    // Freeze both the intent and its version until explicitly closed/reselected.
    setSelection({ row, rows, layout, token: stateToken })
  }
  const frozen = selection?.layout
  const stale = !!selection && selection.token !== stateToken
  const positions = new Map(layout?.cells.flatMap(cell => cell.kind === 'registration' ? [[cell.registration_id, cell] as const] : []))
  function address(point: GridPoint | undefined, grid: GridLayout | null | undefined) {
    if (!point || !grid) return '此版本未記錄格位'
    const column = grid.columns.find(c => c.id === point.column_id)
    return `第 ${grid.rows.findIndex(r => r.id === point.row_id) + 1} 列・${column?.title ?? `${column?.level} 級`}`
  }
  const visible = rows.filter(row => (!level || row.competition_level === Number(level)) && `${row.member_name} ${row.distinguishing_note ?? ''}`.includes(search.trim()))
    .sort((a, b) => a.competition_level - b.competition_level || (layout?.rows.findIndex(r => r.id === positions.get(a.registration_id)?.row_id) ?? 0) - (layout?.rows.findIndex(r => r.id === positions.get(b.registration_id)?.row_id) ?? 0) || a.queue_sequence - b.queue_sequence)
  const candidates = selection?.rows.filter(row => row.registration_id !== selection.row.registration_id) ?? []
  const targetPerson = candidates.find(row => row.registration_id === person)
  const targetCell = frozen?.cells.find(cell => cell.kind === 'registration' && cell.registration_id === person)
  const emptyCells: GridPoint[] = []
  if (frozen && selection) {
    const occupied = new Set(frozen.cells.map(key))
    for (const merge of frozen.merges) {
      const top = frozen.rows.findIndex(r => r.id === merge.start.row_id), bottom = frozen.rows.findIndex(r => r.id === merge.end.row_id)
      const left = frozen.columns.findIndex(c => c.id === merge.start.column_id), right = frozen.columns.findIndex(c => c.id === merge.end.column_id)
      for (let r = top; r <= bottom; r++) for (let c = left; c <= right; c++) occupied.add(key({ row_id: frozen.rows[r].id, column_id: frozen.columns[c].id }))
    }
    for (const row of frozen.rows.filter(r => r.role === 'body')) for (const column of frozen.columns.filter(c => c.kind === 'level' && c.level === Number(destinationLevel))) {
      const point = { row_id: row.id, column_id: column.id }
      if (!occupied.has(key(point))) emptyCells.push(point)
    }
  }
  const targetEmpty = emptyCells.find(point => key(point) === empty)
  let operation: GridOperation | null = null
  let preview = ''
  if (selection) {
    const registration_id = selection.row.registration_id
    if (method === 'move_bottom') {
      operation = { action: method, registration_id, level: Number(destinationLevel) }
      preview = `將 ${identity(selection.row)} 移到 ${destinationLevel} 級欄底，原位置留空。`
    } else if (method === 'swap' && targetPerson) {
      operation = { action: method, registration_id, target_registration_id: targetPerson.registration_id }
      preview = `將 ${identity(selection.row)} 與 ${identity(targetPerson)} 交換位置；跨級時兩人的當次級數一起更新。`
    } else if (method === 'insert' && targetCell && targetPerson) {
      operation = { action: method, registration_id, target: { row_id: targetCell.row_id, column_id: targetCell.column_id }, side }
      preview = `將 ${identity(selection.row)} 插到 ${identity(targetPerson)} ${side === 'before' ? '上方' : '下方'}，下方選手依原規則讓位。`
    } else if (method === 'move_empty' && targetEmpty) {
      operation = { action: method, registration_id, target: targetEmpty }
      preview = `將 ${identity(selection.row)} 移到 ${address(targetEmpty, frozen)} 的空格，原位置留空。`
    }
  }
  function submit() {
    if (!selection || !operation || blocked || stale || submitted.current) return
    submitted.current = { receipt: confirmedRequest }
    onOperate(operation, selection.token)
  }
  return <section className="mobile-arrangement no-print" aria-label="點選安排選手">
    <div className="mobile-arrangement-filters"><label>查看當次級數<select value={level} onChange={e => setLevel(e.target.value)}><option value="">全部級數</option>{Array.from({ length: 10 }, (_, i) => <option key={i} value={i + 1}>{i + 1} 級</option>)}</select></label><span>顯示 {visible.length}／{rows.length} 人</span></div>
    <details className="mobile-list-help"><summary>操作說明</summary><p>點姓名查看資料、移動或交換。列號對應完整表格；文字、合併及底色請切換「完整表格」。</p></details>
    {!readonly && <div className="mobile-undo" role="group" aria-label="名單復原"><button className="secondary" disabled={blocked || !canUndo} onClick={onUndo}>復原上一個動作</button><button className="secondary" disabled={blocked || !canRedo} onClick={onRedo}>重做</button></div>}
    <div className="mobile-player-list">{visible.map(row => <button key={row.registration_id} className={`mobile-player ${vegetarian && row.diet === 'vegetarian' ? 'diet-highlight' : ''}`} disabled={busy} onClick={() => choose(row)} aria-label={`操作 ${identity(row)}`}>
      <span><strong>{row.member_name}</strong><small>{row.distinguishing_note || '無辨識註記'}・順位 {row.queue_sequence}</small><small>{address(positions.get(row.registration_id), layout)}</small></span><span>{row.competition_level} 級{vegetarian && row.diet === 'vegetarian' && <small>素</small>}</span>
    </button>)}</div>
    {!visible.length && <p>沒有符合條件的選手。</p>}
    {selection && <dialog ref={dialog} className="arrangement-dialog mobile-operation-dialog" aria-labelledby="mobile-player-title" onCancel={() => setSelection(null)}>
      <div className="section-title"><h3 id="mobile-player-title">{selection.row.member_name}・安排操作</h3><button autoFocus className="secondary" onClick={() => setSelection(null)}>返回名單</button></div>
      <p>{identity(selection.row)}</p><p>當次 {selection.row.competition_level} 級・長期 {selection.row.member_level ?? '未知'} 級・餐食 {selection.row.diet === null ? '此版本未記錄' : selection.row.diet === 'vegetarian' ? '素食' : selection.row.diet === 'omnivore' ? '葷食' : '未設定'}</p>
      <MemberLevelHistory competitionId={competitionId} memberId={selection.row.member_id} historical={historical} />
      {!readonly && <><fieldset disabled={blocked || stale || !!submitted.current}>
        <label>調整方式<select value={method} onChange={e => setMethod(e.target.value as Method)}><option value="move_bottom">移到級數欄底</option><option value="swap">與另一位選手交換</option><option value="insert">插入另一位選手前後</option><option value="move_empty">移到指定空格</option></select></label>
        {(method === 'move_bottom' || method === 'move_empty') && <label>目標級數<select value={destinationLevel} onChange={e => { setDestinationLevel(e.target.value); setEmpty('') }}>{Array.from({ length: 10 }, (_, i) => <option key={i} value={i + 1}>{i + 1} 級</option>)}</select></label>}
        {(method === 'swap' || method === 'insert') && <label>目標選手<select value={person} onChange={e => setPerson(e.target.value)}><option value="">請選擇選手</option>{candidates.map(row => <option key={row.registration_id} value={row.registration_id}>{identity(row)}・{row.competition_level} 級</option>)}</select></label>}
        {method === 'insert' && <label>插入位置<select value={side} onChange={e => setSide(e.target.value as 'before' | 'after')}><option value="before">目標上方</option><option value="after">目標下方</option></select></label>}
        {method === 'move_empty' && <label>目標空格<select value={empty} onChange={e => setEmpty(e.target.value)}><option value="">請選擇空格</option>{emptyCells.map(point => <option key={key(point)} value={key(point)}>{address(point, frozen)}</option>)}</select></label>}
      </fieldset>
      {preview && <p className="notice info" aria-label="調整預覽">{preview}</p>}
      {stale && !busy && <p role="alert">名單已更新，請返回名單重新選擇，不會套用舊的位置。</p>}
      {busy && <p role="status">正在處理或等待確認；可返回名單查看保存狀態，請勿重複操作。</p>}
      <button disabled={blocked || stale || !operation || !!submitted.current} onClick={submit}>確認調整</button></>}
      {readonly && <p>此版本唯讀，可返回完整表格檢視。</p>}
    </dialog>}
  </section>
}

import { useEffect, useRef, useState } from 'react'
import type { CompetitionRegistration } from './types'
import { useLevelCardDrag } from './useLevelCardDrag'
import type { LevelMove } from './useCompetitionLevelMoves'

const levels = Array.from({ length: 10 }, (_, index) => index + 1)
type Props = {
  rows: CompetitionRegistration[]; search: string; filter: string; readonly: boolean
  displayLevel: (row: CompetitionRegistration) => number
  canMove: (row: CompetitionRegistration) => boolean
  onMove: (id: string, level: number) => void
  pending: Record<string, LevelMove>
  undoLevel: (row: CompetitionRegistration) => number | null
  onUndo: (row: CompetitionRegistration) => void
}

export function LevelCardBoard({ rows, search, filter, readonly, displayLevel, canMove, onMove, pending, undoLevel, onUndo }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const targets = useRef<HTMLDivElement>(null)
  const picked = rows.find(row => row.id === selected)
  function pick(id: string) {
    const row = rows.find(item => item.id === id)
    if (!row || !canMove(row)) return
    setSelected(id)
  }
  useEffect(() => {
    if (selected) targets.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
  }, [selected])
  function move(id: string, level: number) {
    const row = rows.find(item => item.id === id)
    if (!row || !canMove(row)) return
    const before = displayLevel(row)
    onMove(id, level)
    setSelected(null)
    setAnnouncement(before === level ? `${row.member_name} 留在 ${level} 級` : `${row.member_name}：${before} → ${level} 級，移動已送出`)
  }
  const { drag, holding, start } = useLevelCardDrag(move, pick, !readonly)
  const counts = (level: number) => rows.filter(row => displayLevel(row) === level).length
  const matches = (row: CompetitionRegistration) => `${row.member_name} ${row.distinguishing_note ?? ''}`.includes(search.trim()) && (!filter || displayLevel(row) === Number(filter))
  return <div className={`level-card-board ${drag ? 'is-dragging' : ''}`} onKeyDown={event => { if (event.key === 'Escape') setSelected(null) }}>
    <p id="level-drag-help">拖住卡片把手移到級數區；手機長按把手後拖曳。卡片其餘位置可正常捲動。也可點「點選移動」，再選目的級數；鍵盤用 Tab、Enter 操作，Escape 取消拖曳。</p>
    <div className="level-drop-shortcuts" ref={targets} role="group" aria-label="級數移動快捷區">
      <p>{picked ? `已選取 ${picked.member_name}（${picked.distinguishing_note || '無辨識註記'}），請選目的級數` : drag ? `正在移動 ${drag.card.name}` : '級數快捷區：可放下卡片，或先點選一張卡片'}</p>
      <div>{levels.map(level => <button key={level} type="button" className={`secondary ${drag?.target === level ? 'drop-target-active' : ''}`}
        data-drop-level={level} data-drop-enabled={!readonly} aria-label={`移到 ${level} 級`}
        aria-disabled={readonly || (!picked && !drag)} disabled={readonly}
        onClick={() => { if (picked) move(picked.id, level) }}>
        <strong>{level} 級</strong><small>{counts(level)} 人</small>
      </button>)}</div>
      {picked && <button type="button" className="secondary" onClick={() => setSelected(null)}>取消選取</button>}
    </div>
    <p role="status" className="level-drag-announcement">{announcement}</p>
    <div className="level-groups level-card-groups">{levels.map(level => {
      const visible = rows.filter(row => displayLevel(row) === level && matches(row)).sort((a, b) => a.queue_sequence - b.queue_sequence)
      const stored = rows.filter(row => row.competition_level === level).length
      return <section key={level} className={`competition-level-group ${drag?.target === level ? 'drop-target-active' : ''}`}
        aria-label={`當次 ${level} 級正取`} data-drop-level={level} data-drop-enabled={!readonly}>
        <h3><strong>{level} 級</strong><span>篩選 {visible.length}／安排 {counts(level)} 人<small>已儲存 {stored} 人</small></span></h3>
        <div className="level-zone-cards">
          {!visible.length && <p className="level-empty-drop">{filter || search ? '無符合的卡片，仍可放到此級' : '拖曳卡片到這裡'}</p>}
          {visible.map(row => {
            const current = displayLevel(row)
            const changed = current !== row.competition_level
            return <article key={row.id} data-registration-id={row.id} className={`level-person level-name-card ${changed ? 'has-local-move' : ''} ${selected === row.id ? 'is-selected' : ''}`}>
              <div className="level-card-name"><strong>{row.member_name}</strong><small>{row.distinguishing_note || '無辨識註記'}・順位 {row.queue_sequence}</small></div>
              <div className="level-values"><span>報名快照 <b>{row.hard_level_snapshot} 級</b></span><span>當次級數 <b>{current} 級</b></span></div>
              {pending[row.id] && <p className="level-card-state">{pending[row.id].status === 'saving' ? '儲存中' : '尚未確認儲存'}：{pending[row.id].base.competition_level} → {current} 級</p>}
              {!readonly && <div className="level-card-actions">
                <button type="button" className="secondary level-drag-handle" aria-label={`拖曳 ${row.member_name} 順位 ${row.queue_sequence}`} aria-describedby="level-drag-help"
                  disabled={!canMove(row)} onPointerDown={event => start(event, { id: row.id, name: row.member_name })}
                  onClick={event => { if (event.detail === 0) pick(row.id) }} onContextMenu={event => event.preventDefault()}>
                  {holding === row.id ? '長按中…' : '⠿ 拖曳'}
                </button>
                <button type="button" className="secondary" disabled={!canMove(row)} aria-pressed={selected === row.id} onClick={() => pick(row.id)}>點選移動</button>
                {undoLevel(row) !== null && <button type="button" className="secondary" disabled={!canMove(row)} onClick={() => onUndo(row)}>撤回到 {undoLevel(row)} 級</button>}
              </div>}
            </article>
          })}
        </div>
      </section>
    })}</div>
    {drag && <div className="level-drag-ghost" aria-hidden="true" style={{ left: Math.min(drag.x + 12, window.innerWidth - 200), top: Math.max(8, Math.min(drag.y + 12, window.innerHeight - 90)) }}><strong>{drag.card.name}</strong><span>{drag.target ? `放到 ${drag.target} 級` : '移到級數區域'}</span></div>}
  </div>
}

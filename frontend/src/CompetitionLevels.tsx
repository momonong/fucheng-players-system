import { useState } from 'react'
import { LevelCardBoard } from './LevelCardBoard'
import type { CompetitionDetail, CompetitionRegistration } from './types'
import type { LevelMovesController } from './useCompetitionLevelMoves'

const levels = Array.from({ length: 10 }, (_, i) => i + 1)

export function CompetitionLevels({ detail, controller, reload }: {
  detail: CompetitionDetail; controller: LevelMovesController; reload: () => void
}) {
  const { competition, registrations } = detail
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const readonly = !!competition.deleted_at || !['open', 'closed'].includes(competition.status)
  const { moves, reasons, notices, undos, move, retry, discard, setReason } = controller
  const reason = reasons[competition.id] ?? ''
  const pending = Object.values(moves).filter(item => item.base.competition_id === competition.id)
  const confirmed = registrations.filter(row => row.status === 'confirmed')
  const displayLevel = (row: CompetitionRegistration) => moves[row.id]?.level ?? row.competition_level
  const matches = (row: CompetitionRegistration) => `${row.member_name} ${row.distinguishing_note ?? ''}`.includes(search.trim()) && (!filter || displayLevel(row) === Number(filter))
  const canMove = (row: CompetitionRegistration) => !readonly && !!reason.trim() && !moves[row.id] && row.status === 'confirmed'
  function onMove(id: string, level: number) {
    const row = registrations.find(item => item.id === id)
    if (row && canMove(row)) move(row, level)
  }
  return <section className="panel competition-levels no-print" aria-label="當次比賽級數安排">
    <div className="section-title"><div><p className="eyebrow">當次比賽</p><h2>級數與人員安排</h2></div><a href="#registration-roster">報名與操作歷史 ↓</a></div>
    <p>會員長期級數、報名快照與當次級數各自獨立。卡片只調整本場，依 1～10 升冪排列。</p>
    <p className="notice info">每次放下卡片會自動儲存並記錄原因；同一卡片完成後才能再移動。候補待遞補後才能安排；取消保留歷史，重新報名需重新確認級數。</p>
    {readonly ? <p role="status">此場次為唯讀，不能調整當次級數。</p> : <div className="level-session-reason">
      <label>本次調整原因（必填）<input maxLength={500} value={reason} onChange={event => setReason(competition.id, event.target.value)} placeholder="先填原因，再移動卡片" /></label>
      <p>{reason.trim() ? '後續每次移動使用當下原因；修改此欄不影響已送出的操作。' : '請先填寫原因，才能拖曳或點選移動。'} 未完成操作與原因在頁內切換場次後保留。</p>
    </div>}
    <p className="level-totals">全場正取安排 {confirmed.length} 人・候補 {competition.summary.waitlisted} 人・取消 {competition.summary.cancelled} 人</p>
    <p>全場已儲存當次級數：{levels.map(n => `${n}級 ${competition.summary.competition_level_counts[n] ?? 0}人`).join('、')}</p>
    <div className="roster-filters"><label>安排搜尋姓名／辨識註記<input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><label>當次級數篩選<select value={filter} onChange={event => setFilter(event.target.value)}><option value="">全部級數</option>{levels.map(n => <option key={n} value={n}>{n} 級</option>)}</select></label><p>篩選正取 {confirmed.filter(matches).length}／全場正取 {confirmed.length} 人</p></div>
    <p className="muted">畫面分區與篩選包含未完成移動；各區另列已儲存人數。每人獨立儲存，其他卡片不會隨同送出。</p>
    {notices[competition.id] && <p role="status">{notices[competition.id]}</p>}
    {!!pending.length && <div className="level-pending"><h3>未完成移動（{pending.length}）</h3>{pending.map(item => {
      const current = registrations.find(row => row.id === item.base.id)
      return <article className="level-pending-item" key={item.base.id} data-pending-id={item.base.id}>
        <h4>{item.base.member_name}・{item.base.distinguishing_note || '無辨識註記'}・順位 {item.base.queue_sequence}</h4>
        <p>這次移動：{item.base.competition_level} → {item.level} 級／原版本 {item.base.version}</p><p>送出原因：{item.reason}</p>
        {item.status === 'saving' && <p role="status">正在儲存，請稍候。同一卡片暫停移動。</p>}
        {item.error && <p className="notice error" role="alert">{item.error}（移動、原因與原始版本已保留）</p>}
        {current && current.version !== item.base.version && <p>最新讀取：{current.competition_level} 級／版本 {current.version}。未完成操作仍保留原始版本。</p>}
        {item.status === 'unknown' && <><p>結果尚未確認，可能已儲存。請以原操作確認結果；不能改原因、改目的級數或直接撤回這筆。</p><button onClick={() => retry(item.base.id)}>確認結果／原樣重試</button></>}
        {item.status === 'conflict' && <p>已有其他更新或目前狀態不允許移動。不會自動覆寫；先讀取最新名單核對。</p>}
        {item.status !== 'saving' && <button className="secondary" onClick={reload}>讀取最新名單（保留未完成移動）</button>}
        {['conflict', 'rejected'].includes(item.status) && <button className="secondary" onClick={() => { discard(item.base.id); reload() }}>放棄未完成移動並讀取最新名單</button>}
      </article>
    })}</div>}
    <LevelCardBoard key={competition.id} rows={confirmed} search={search} filter={filter} readonly={readonly}
      displayLevel={displayLevel} canMove={canMove} onMove={onMove} pending={moves}
      undoLevel={row => { const undo = undos[row.id]; return undo && undo.version === row.version && undo.after === row.competition_level ? undo.before : null }}
      onUndo={row => { const undo = undos[row.id]; if (undo && canMove(row)) move(row, undo.before, true) }} />
    {(['waitlisted', 'cancelled'] as const).map(status => <details className="level-excluded" key={status}><summary>{status === 'waitlisted' ? '候補（級數唯讀）' : '取消（歷史唯讀）'}：篩選 {registrations.filter(row => row.status === status && matches(row)).length} 人，不計入正取安排</summary>{registrations.filter(row => row.status === status && matches(row)).map(row => <article className="level-person" key={row.id}><strong>{row.member_name}</strong><small>{row.distinguishing_note || '無辨識註記'}・順位 {row.queue_sequence}</small><span>報名快照 {row.hard_level_snapshot} 級／當次級數 {row.competition_level} 級</span></article>)}</details>)}
  </section>
}

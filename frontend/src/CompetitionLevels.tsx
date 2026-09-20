import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { updateRegistrationLevel } from './api'
import type { CompetitionDetail, CompetitionRegistration } from './types'

type LevelDraft = { base: CompetitionRegistration; level: number; reason: string; requestId: string; error: string; conflict: boolean }
export type LevelDrafts = Record<string, LevelDraft>
const levels = Array.from({ length: 10 }, (_, i) => i + 1)

export function CompetitionLevels({ detail, drafts, setDrafts, reload }: {
  detail: CompetitionDetail; drafts: LevelDrafts; setDrafts: Dispatch<SetStateAction<LevelDrafts>>; reload: () => void
}) {
  const { competition, registrations } = detail
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const lock = useRef(false)
  const focusDraft = useRef<string | null>(null)
  const [notice, setNotice] = useState('')
  const readonly = !!competition.deleted_at || !['open', 'closed'].includes(competition.status)
  const activeDrafts = Object.values(drafts).filter(d => d.base.competition_id === competition.id)
  useEffect(() => {
    if (!focusDraft.current) return
    const form = document.getElementById(`level-edit-${focusDraft.current}`)
    if (form) {
      form.scrollIntoView({ block: 'center' })
      form.querySelector('select')?.focus({ preventScroll: true })
      focusDraft.current = null
    }
  }, [drafts])
  useEffect(() => {
    if (!Object.keys(drafts).length) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [drafts])
  const matches = (item: CompetitionRegistration) => `${item.member_name} ${item.distinguishing_note ?? ''}`.includes(search.trim()) && (!filter || item.competition_level === Number(filter))
  const confirmed = registrations.filter(item => item.status === 'confirmed')
  const visible = confirmed.filter(matches)
  function edit(item: CompetitionRegistration) {
    setNotice('')
    focusDraft.current = item.id
    setDrafts(current => ({ ...current, [item.id]: current[item.id] ?? { base: { ...item }, level: item.competition_level, reason: '', requestId: crypto.randomUUID(), error: '', conflict: false } }))
  }
  function change(id: string, patch: Partial<LevelDraft>) {
    setDrafts(current => ({ ...current, [id]: { ...current[id], ...patch, requestId: crypto.randomUUID() } }))
  }
  function discard(id: string) {
    setDrafts(current => { const next = { ...current }; delete next[id]; return next })
  }
  async function save(event: React.FormEvent, draft: LevelDraft) {
    event.preventDefault()
    if (lock.current || draft.conflict) return
    lock.current = true; setBusy(draft.base.id); setNotice('')
    try {
      await updateRegistrationLevel(draft.base, draft.level, draft.reason, draft.requestId)
      discard(draft.base.id)
      setNotice(`${draft.base.member_name} 的當次級數已儲存`)
      reload()
    } catch (error) {
      const conflict = (error as Error & { status?: number }).status === 409
      // Keep both the original version and request key. A network retry may already have committed.
      setDrafts(current => ({ ...current, [draft.base.id]: { ...current[draft.base.id], error: (error as Error).message, conflict } }))
    } finally { lock.current = false; setBusy('') }
  }
  function person(item: CompetitionRegistration, editable: boolean) {
    return <article className="level-person" key={item.id} data-registration-id={item.id}>
      <div><strong>{item.member_name}</strong><small>{item.distinguishing_note || '無辨識註記'}・順位 {item.queue_sequence}</small></div>
      <div className="level-values"><span>報名快照 <b>{item.hard_level_snapshot} 級</b></span><span>當次級數 <b>{item.competition_level} 級</b></span></div>
      {editable && <button className="secondary" disabled={!!busy} onClick={() => edit(item)}>{drafts[item.id] ? '編輯草稿保留中' : '調整級數'}</button>}
    </article>
  }
  return <section className="panel competition-levels no-print" aria-label="當次比賽級數安排">
    <div className="section-title"><div><p className="eyebrow">當次比賽</p><h2>級數與人員安排</h2></div><a href="#registration-roster">報名與操作歷史 ↓</a></div>
    <p>報名快照保留報名當下級數；當次級數只用於這一場安排，不修改會員長期級數。數字依升冪顯示。</p>
    <p className="notice info">候補遞補後才能安排級數。取消保留歷史；重新報名會建立新紀錄，依新的報名快照初始化，請重新確認當次級數。</p>
    {readonly && <p role="status">此場次為唯讀，不能調整當次級數。</p>}
    <p className="level-totals">全場正取安排 {confirmed.length} 人・候補 {competition.summary.waitlisted} 人・取消 {competition.summary.cancelled} 人</p>
    <p>全場正取當次級數：{levels.map(n => `${n}級 ${competition.summary.competition_level_counts[n] ?? 0}人`).join('、')}</p>
    <div className="roster-filters"><label>安排搜尋姓名／辨識註記<input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><label>當次級數篩選<select value={filter} onChange={event => setFilter(event.target.value)}><option value="">全部級數</option>{levels.map(n => <option key={n} value={n}>{n} 級</option>)}</select></label><p>篩選正取 {visible.length}／全場正取 {confirmed.length} 人</p></div>
    {notice && <p role="status">{notice}</p>}
    {!!activeDrafts.length && <div className="level-drafts"><h3>待儲存調整</h3><p>草稿不受名單篩選影響，切換場次後再回來仍保留。關閉頁面前請先儲存。</p>{activeDrafts.map(draft => {
      const current = registrations.find(row => row.id === draft.base.id)
      const changed = !!current && current.version !== draft.base.version
      const disabled = readonly || !current || current.status !== 'confirmed'
      return <form className="level-edit" id={`level-edit-${draft.base.id}`} key={draft.base.id} aria-label={`調整 ${draft.base.member_name} 順位 ${draft.base.queue_sequence}`} onSubmit={event => save(event, draft)}>
        <h4>{draft.base.member_name}・{draft.base.distinguishing_note || '無辨識註記'}・順位 {draft.base.queue_sequence}</h4>
        <p>編輯基準：{draft.base.competition_level} 級／版本 {draft.base.version}；報名快照 {draft.base.hard_level_snapshot} 級</p>
        {changed && <p className="notice info">伺服器目前為 {current.competition_level} 級／版本 {current.version}，草稿仍保留原始版本。</p>}
        {draft.error && <p className="notice error" role="alert">{draft.error}（級數與原因輸入已保留）</p>}
        {draft.conflict && <p>請先核對最新名單。需要修改時，明確放棄本筆草稿並重新開啟調整，不會自動覆寫。</p>}
        {disabled && <p role="status">這筆目前不能調級，輸入保留供核對。</p>}
        <div className="form-row"><label>調整後當次級數<select value={draft.level} disabled={!!busy || disabled || draft.conflict} onChange={event => change(draft.base.id, { level: Number(event.target.value) })}>{levels.map(n => <option key={n} value={n}>{n} 級</option>)}</select></label><label>調級原因（必填）<input required maxLength={500} value={draft.reason} disabled={!!busy || disabled || draft.conflict} onChange={event => change(draft.base.id, { reason: event.target.value })} /></label></div>
        <div className="header-actions"><button disabled={!!busy || disabled || draft.conflict || draft.level === draft.base.competition_level || !draft.reason.trim()}>{busy === draft.base.id ? '儲存中…' : '儲存當次級數'}</button><button type="button" className="secondary" disabled={!!busy} onClick={() => reload()}>讀取最新名單（保留草稿）</button><button type="button" className="secondary" disabled={!!busy} onClick={() => { discard(draft.base.id); reload() }}>放棄本筆草稿並重新載入</button></div>
      </form>
    })}</div>}
    <div className="level-groups">{levels.filter(n => !filter || n === Number(filter)).map(n => {
      const rows = visible.filter(item => item.competition_level === n).sort((a, b) => a.queue_sequence - b.queue_sequence)
      return <section className="competition-level-group" key={n} aria-label={`當次 ${n} 級正取`}><h3>{n} 級 <span>篩選 {rows.length}／全場 {competition.summary.competition_level_counts[n] ?? 0} 人</span></h3>{rows.length ? rows.map(item => person(item, !readonly)) : <p className="muted">沒有符合的正取。</p>}</section>
    })}</div>
    {(['waitlisted', 'cancelled'] as const).map(status => <details className="level-excluded" key={status}><summary>{status === 'waitlisted' ? '候補（級數唯讀）' : '取消（歷史唯讀）'}：篩選 {registrations.filter(row => row.status === status && matches(row)).length} 人，不計入正取安排</summary>{registrations.filter(row => row.status === status && matches(row)).map(item => person(item, false))}</details>)}
  </section>
}

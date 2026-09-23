import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from './api'
import { RegistrationHistory } from './PublicRegistrationPortal'
import { CompetitionLevels } from './CompetitionLevels'
import { useArrangementWorkspace } from './useArrangementWorkspace'
import type {
  Competition,
  CompetitionDetail,
  CompetitionDraft,
  CompetitionRegistration,
  CompetitionStatus,
  Diet,
  RegistrationMember,
  RegistrationStatus,
} from './types'

const dietText: Record<Diet, string> = { unset: '未設定', omnivore: '葷食', vegetarian: '素食' }
const statusText: Record<CompetitionStatus, string> = {
  draft: '草稿', open: '報名中', closed: '報名截止', ended: '已結束', cancelled: '已取消',
}
const registrationText: Record<RegistrationStatus, string> = {
  confirmed: '正取', waitlisted: '候補', cancelled: '已取消',
}
const emptyDraft: CompetitionDraft = {
  name: '', competition_date: '', capacity: 1, registration_deadline: '', notes: '', status: 'draft', reason: '',
}

export function CompetitionManager({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [items, setItems] = useState<Competition[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CompetitionDetail | null>(null)
  const [creating, setCreating] = useState(false)
  const arrangements = useArrangementWorkspace(username)
  const [view, setView] = useState<'arrangement' | 'management'>('arrangement')
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  const [deleted, setDeleted] = useState(false)
  const [confirmation, setConfirmation] = useState<Competition | null>(null)
  const requestSequence = useRef(0)

  async function loadList(selectId?: string) {
    const sequence = ++requestSequence.current
    try {
      const result = await api.competitions(deleted)
      if (sequence !== requestSequence.current) return
      setItems(result)
      const preferred = selectId ?? selectedId
      const next = result.find(item => item.id === preferred)?.id ?? result[0]?.id ?? null
      setSelectedId(next)
      const loaded = next ? await api.competition(next) : null
      if (sequence === requestSequence.current) setDetail(loaded)
    } catch (error) {
      setNotice({ kind: 'error', text: (error as Error).message })
    }
  }
  async function loadDetail(id: string) {
    const sequence = ++requestSequence.current
    setSelectedId(id); setCreating(false); setDetail(null)
    try { const loaded = await api.competition(id); if (sequence === requestSequence.current) setDetail(loaded) }
    catch (error) { setNotice({ kind: 'error', text: (error as Error).message }) }
  }
  useEffect(() => { setCreating(false); setDetail(null); loadList(); return () => { requestSequence.current++ } }, [deleted])
  async function signOut() {
    try { await api.logout(); onLogout() }
    catch (error) { setNotice({ kind: 'error', text: (error as Error).message }) }
  }

  return <>
    <header className="admin-header no-print">
      <div><p className="eyebrow">比賽管理</p><h1>府城球館</h1></div>
      <div className="header-actions"><span>{username}</span><a href="/admin">會員管理</a><a href="/admin/announcements">公告管理</a><a href="/admin/roster">會員分級名單</a><button className="secondary" onClick={signOut}>登出</button></div>
    </header>
    {notice && <div className={`toast ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><span>{notice.text}</span><button className="toast-close" onClick={() => setNotice(null)}>×</button></div>}
    <nav className="competition-mode no-print" aria-label="比賽工作區"><h2>比賽</h2><select aria-label="選擇比賽" value={selectedId ?? ''} onChange={event => loadDetail(event.target.value)}>{!items.length && <option value="">尚無比賽</option>}{items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="secondary" aria-pressed={view === 'arrangement'} onClick={() => { setView('arrangement'); if (selectedId) void loadDetail(selectedId) }}>排級數</button><button className="secondary" aria-pressed={view === 'management'} onClick={() => { setView('management'); if (selectedId) void loadDetail(selectedId) }}>報名與設定</button></nav>
    {view === 'arrangement' && <main className="arrangement-main">{detail ? <CompetitionLevels key={detail.competition.id} competition={detail.competition} controller={arrangements} username={username} /> : <p>請選擇比賽，或到「報名與設定」建立比賽。</p>}</main>}
    {view === 'management' && <main className="competition-layout">
      <aside className="panel competition-list no-print">
        <div className="section-title"><div><h2>比賽清單</h2><p>共 {items.length} 場</p></div><button disabled={deleted} onClick={() => { requestSequence.current++; setCreating(true); setSelectedId(null); setDetail(null) }}>建立比賽</button></div>
        <div className="competition-view-switch" aria-label="比賽清單範圍"><button className="secondary" aria-pressed={!deleted} onClick={() => setDeleted(false)}>目前比賽</button><button className="secondary" aria-pressed={deleted} onClick={() => setDeleted(true)}>已刪除</button></div>
        <div className="competition-items">{items.map(item => <button key={item.id} className={`competition-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => loadDetail(item.id)}>
          <strong>{item.name}</strong><span>{item.competition_date}・{item.deleted_at ? '已刪除' : statusText[item.status]}</span><small>正取 {item.summary.confirmed}/{item.capacity}・候補 {item.summary.waitlisted}</small>
        </button>)}</div>
      </aside>
      <section className="competition-workspace">
        {creating && <CompetitionEditor onSaved={competition => { setNotice({ kind: 'success', text: '比賽已建立' }); setCreating(false); loadList(competition.id) }} />}
        {detail && <>
          <div className="panel competition-delete-actions no-print"><div>{detail.competition.deleted_at ? <p>已於 {taipei(detail.competition.deleted_at)} 刪除，名單保留且暫停所有操作。</p> : <p>不需要的比賽可移到「已刪除」，日後仍可還原。</p>}</div><button className={detail.competition.deleted_at ? 'secondary' : 'danger'} onClick={() => setConfirmation(detail.competition)}>{detail.competition.deleted_at ? '還原比賽' : '刪除比賽'}</button></div>
          <CompetitionEditor competition={detail.competition} onSaved={competition => { setNotice({ kind: 'success', text: '比賽設定已儲存' }); loadList(competition.id) }} />
          <CompetitionRoster detail={detail} reload={() => loadList(detail.competition.id)} notify={setNotice} />
        </>}
        {!creating && !detail && <div className="panel empty">請選擇比賽，或建立一場比賽。</div>}
      </section>
    </main>}
    {confirmation && <DeletionDialog competition={confirmation} onClose={() => setConfirmation(null)} onDone={() => { setConfirmation(null); setNotice({ kind: 'success', text: confirmation.deleted_at ? '比賽已還原，請到「目前比賽」查看' : '比賽已刪除，可到「已刪除」還原' }); loadList() }} />}
  </>
}

function DeletionDialog({ competition, onClose, onDone }: { competition: Competition; onClose: () => void; onDone: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const safeButton = useRef<HTMLButtonElement>(null)
  const submitting = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const restore = !!competition.deleted_at
  useEffect(() => { dialog.current?.showModal(); safeButton.current?.focus() }, [])
  async function confirm() {
    if (submitting.current) return
    submitting.current = true; setBusy(true); setError('')
    try { await api.changeCompetitionDeletion(competition, restore); onDone() }
    catch (caught) { setError((caught as Error).message) }
    finally { submitting.current = false; setBusy(false) }
  }
  return <dialog ref={dialog} className="competition-confirm-dialog" aria-labelledby="delete-dialog-title" aria-describedby="delete-dialog-description" onCancel={event => { event.preventDefault(); if (!submitting.current) onClose() }}>
    <h2 id="delete-dialog-title">{restore ? '確認還原比賽？' : '確認刪除比賽？'}</h2>
    <p className="competition-confirm-name">{competition.name}</p>
    <p>{competition.competition_date}・名額 {competition.capacity} 人</p>
    <p>正取 {competition.summary.confirmed} 人・候補 {competition.summary.waitlisted} 人・已取消 {competition.summary.cancelled} 人</p>
    <p id="delete-dialog-description">{restore ? `將恢復為「${statusText[competition.status]}」。若原本報名中且尚未截止，還原後會重新開放報名。` : '刪除後會從首頁、報名入口與目前比賽清單移除。所有報名與操作紀錄都會保留，可從「已刪除」還原。'}</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="competition-confirm-buttons"><button ref={safeButton} className="secondary" disabled={busy} onClick={onClose}>{restore ? '暫不還原' : '保留比賽'}</button><button className={restore ? '' : 'danger'} disabled={busy} onClick={confirm}>{busy ? '處理中…' : restore ? '確認還原' : '確認刪除'}</button></div>
  </dialog>
}

function CompetitionEditor({ competition, onSaved }: { competition?: Competition; onSaved: (value: Competition) => void }) {
  const [draft, setDraft] = useState<CompetitionDraft>(() => competition ? fromCompetition(competition) : emptyDraft)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (competition) setDraft(fromCompetition(competition)) }, [competition?.id, competition?.version])
  const readonly = !!competition?.deleted_at || competition?.status === 'ended' || competition?.status === 'cancelled'
  const allowedStatuses = competition ? legalStatuses(competition.status) : ['draft', 'open'] as CompetitionStatus[]
  function set<K extends keyof CompetitionDraft>(key: K, value: CompetitionDraft[K]) { setDraft(current => ({ ...current, [key]: value })) }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError('')
    try { onSaved(await api.saveCompetition(draft, competition?.id)) }
    catch (caught) { setError((caught as Error).message) }
    finally { setSaving(false) }
  }
  return <section className="panel competition-editor no-print">
    <div className="section-title"><div><h2>{competition ? '比賽設定' : '建立比賽'}</h2>{competition && <p>版本 {competition.version}・最後更新 {taipei(competition.updated_at)}</p>}</div>{readonly && <span className="status inactive">唯讀</span>}</div>
    {error && <div className="notice error" role="alert">{error}（輸入已保留）</div>}
    <form onSubmit={submit}>
      <label>名稱<input required maxLength={120} value={draft.name} disabled={readonly} onChange={event => set('name', event.target.value)} /></label>
      <div className="form-row"><label>比賽日期<input type="date" required value={draft.competition_date} disabled={readonly} onChange={event => set('competition_date', event.target.value)} /></label>
      <label>名額上限<input type="number" min={1} max={10000} required value={draft.capacity} disabled={readonly} onChange={event => set('capacity', Number(event.target.value))} /></label></div>
      <div className="form-row"><label>報名截止時間（台北時間）<input type="datetime-local" required value={draft.registration_deadline} disabled={readonly} onChange={event => set('registration_deadline', event.target.value)} /></label>
      <label>狀態<select value={draft.status} disabled={readonly} onChange={event => set('status', event.target.value as CompetitionStatus)}>{allowedStatuses.map(status => <option key={status} value={status}>{statusText[status]}</option>)}</select></label></div>
      <label>備註<textarea rows={3} maxLength={5000} value={draft.notes} disabled={readonly} onChange={event => set('notes', event.target.value)} /></label>
      {competition && !readonly && <label>設定異動原因（建議填寫）<input maxLength={500} value={draft.reason ?? ''} onChange={event => set('reason', event.target.value)} /></label>}
      {!readonly && <button disabled={saving}>{saving ? '儲存中…' : '儲存比賽'}</button>}
    </form>
  </section>
}

function CompetitionRoster({ detail, reload, notify }: {
  detail: CompetitionDetail
  reload: () => void
  notify: (value: { kind: 'success' | 'error'; text: string }) => void
}) {
  const { competition, registrations } = detail
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState('')
  const [reason, setReason] = useState('')
  const [candidateSearch, setCandidateSearch] = useState('')
  const [candidateLevel, setCandidateLevel] = useState('')
  const [candidates, setCandidates] = useState<RegistrationMember[]>([])
  const [dietOverride, setDietOverride] = useState<'' | Diet>('')
  const [busy, setBusy] = useState('')
  const readonly = !!competition.deleted_at || competition.status === 'ended' || competition.status === 'cancelled' || competition.status === 'draft'
  useEffect(() => {
    let active = true
    const timer = window.setTimeout(() => api.registrationMembers(candidateSearch, candidateLevel).then(result => { if (active) setCandidates(result) }).catch(error => notify({ kind: 'error', text: error.message })), 150)
    return () => { active = false; window.clearTimeout(timer) }
  }, [candidateSearch, candidateLevel])
  const filtered = useMemo(() => registrations.filter(item => {
    const text = `${item.member_name} ${item.distinguishing_note ?? ''}`
    return text.includes(search) && (!level || item.hard_level_snapshot === Number(level))
  }), [registrations, search, level])
  const firstWaiting = registrations.filter(item => item.status === 'waitlisted').sort((a, b) => a.queue_sequence - b.queue_sequence)[0]
  const registeredMemberIds = new Set(registrations.filter(item => item.status !== 'cancelled').map(item => item.member_id))
  async function act(label: string, action: () => Promise<unknown>) {
    setBusy(label)
    try { await action(); notify({ kind: 'success', text: '名單已更新' }); reload() }
    catch (error) { notify({ kind: 'error', text: (error as Error).message }) }
    finally { setBusy('') }
  }
  async function add(member: RegistrationMember) {
    await act(`add-${member.id}`, () => api.createRegistration(competition.id, member.id, dietOverride || null, reason, crypto.randomUUID()))
  }
  async function mutate(registration: CompetitionRegistration, action: 'cancel' | 'promote') {
    await act(`${action}-${registration.id}`, () => api.mutateRegistration(registration, action, reason, crypto.randomUUID()))
  }
  async function changeDiet(registration: CompetitionRegistration, diet: Diet) {
    await act(`diet-${registration.id}`, () => api.updateRegistrationDiet(registration, diet, reason, crypto.randomUUID()))
  }

  return <section id="registration-roster" className="panel roster-panel competition-print">
    <div className="section-title no-print"><div><h2>報名名單</h2><p>摘要固定顯示全場總數，不隨下方篩選改變</p></div><button className="secondary" onClick={() => window.print()}>列印管理名單</button></div>
    <div className="print-only print-title"><h1>{competition.name}</h1><p>{competition.competition_date}・管理用名單</p></div>
    <div className="summary-grid" aria-label="全場總數">
      <Summary label="正取／名額" value={`${competition.summary.confirmed}/${competition.capacity}`} />
      <Summary label="候補" value={competition.summary.waitlisted} />
      <Summary label="剩餘名額" value={competition.summary.remaining} />
      <Summary label="待遞補" value={competition.summary.pending_promotions} />
      <Summary label="葷／素／未設定" value={`${competition.summary.diet_counts.omnivore}/${competition.summary.diet_counts.vegetarian}/${competition.summary.diet_counts.unset}`} />
    </div>
    <p className="level-summary">正取級數：{Object.entries(competition.summary.level_counts).sort(([a], [b]) => Number(a) - Number(b)).map(([key, value]) => `${key}級 ${value}人`).join('、') || '尚無'}</p>
    {competition.summary.pending_promotions > 0 && <div className="notice info no-print">有 {competition.summary.pending_promotions} 個名額可遞補；系統不會自動升為正取。</div>}
    {!readonly && <div className="late-reason no-print"><label>截止後操作原因<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} placeholder="截止後補登、取消、遞補或修改餐食時必填" /></label></div>}
    {!readonly && <details className="candidate-picker no-print"><summary>加入啟用會員</summary>
      <div className="filters compact"><label>搜尋姓名／辨識註記<input type="search" value={candidateSearch} onChange={event => setCandidateSearch(event.target.value)} /></label>
      <label>級數<select value={candidateLevel} onChange={event => setCandidateLevel(event.target.value)}><option value="">全部</option>{range(1, 10).map(n => <option key={n}>{n}</option>)}</select></label>
      <label>當次餐食<select value={dietOverride} onChange={event => setDietOverride(event.target.value as '' | Diet)}><option value="">沿用會員預設</option>{Object.entries(dietText).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label></div>
      <div className="candidate-list">{candidates.map(member => <button key={member.id} disabled={registeredMemberIds.has(member.id) || !!busy} className="candidate" onClick={() => add(member)}><span><strong>{member.name}</strong>{member.distinguishing_note && <small>{member.distinguishing_note}</small>}</span><span>{member.level}級・{dietText[member.diet]}</span><span>{registeredMemberIds.has(member.id) ? '已報名' : '加入'}</span></button>)}</div>
    </details>}
    <div className="roster-filters no-print"><label>篩選名單<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="姓名或辨識註記" /></label><label>硬實力快照<select value={level} onChange={event => setLevel(event.target.value)}><option value="">全部級數</option>{range(1, 10).map(n => <option key={n}>{n}</option>)}</select></label><p>篩選結果 {filtered.length}／全場 {registrations.length} 筆</p></div>
    <RegistrationHistory competitionId={competition.id} registrations={registrations} />
    {(['confirmed', 'waitlisted', 'cancelled'] as RegistrationStatus[]).map(status => <RosterSection key={status} status={status} rows={filtered.filter(item => item.status === status)} firstWaiting={firstWaiting} readonly={readonly} busy={busy} onMutate={mutate} onDiet={changeDiet} />)}
  </section>
}

function RosterSection({ status, rows, firstWaiting, readonly, busy, onMutate, onDiet }: {
  status: RegistrationStatus
  rows: CompetitionRegistration[]
  firstWaiting?: CompetitionRegistration
  readonly: boolean
  busy: string
  onMutate: (item: CompetitionRegistration, action: 'cancel' | 'promote') => void
  onDiet: (item: CompetitionRegistration, diet: Diet) => void
}) {
  return <section className={`roster-section roster-${status}`}><h3>{registrationText[status]} <span>{rows.length} 人（篩選結果）</span></h3>
    {!rows.length ? <p className="muted">沒有符合篩選條件的紀錄。</p> : <div className="roster-table-wrap"><table><thead><tr><th>順位</th><th>姓名</th><th>硬實力快照</th><th>當次餐食</th><th>操作者／時間</th><th className="no-print">操作</th></tr></thead><tbody>{rows.sort((a, b) => a.queue_sequence - b.queue_sequence).map(item => <tr key={item.id}>
      <td>{item.queue_sequence}</td><td><strong>{item.member_name}</strong>{item.distinguishing_note && <small>{item.distinguishing_note}</small>}</td><td>{item.hard_level_snapshot} 級</td>
      <td>{!readonly && status !== 'cancelled' ? <select aria-label={`${item.member_name}當次餐食`} value={item.diet} disabled={!!busy} onChange={event => onDiet(item, event.target.value as Diet)}>{Object.entries(dietText).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select> : dietText[item.diet]}</td>
      <td>{item.updated_by_username}<small>{taipei(item.updated_at)}</small></td>
      <td className="row-actions no-print">{!readonly && status !== 'cancelled' && <button className="danger" disabled={!!busy} onClick={() => onMutate(item, 'cancel')}>取消</button>}{!readonly && status === 'waitlisted' && firstWaiting?.id === item.id && <button disabled={!!busy} onClick={() => onMutate(item, 'promote')}>確認遞補</button>}</td>
    </tr>)}</tbody></table></div>}
  </section>
}

function Summary({ label, value }: { label: string; value: string | number }) { return <div className="summary-card"><span>{label}</span><strong>{value}</strong></div> }
function fromCompetition(value: Competition): CompetitionDraft { return { name: value.name, competition_date: value.competition_date, capacity: value.capacity, registration_deadline: taipeiInput(value.registration_deadline), notes: value.notes ?? '', status: value.status, version: value.version, reason: '' } }
function legalStatuses(status: CompetitionStatus): CompetitionStatus[] { return status === 'draft' ? ['draft', 'open', 'cancelled'] : status === 'open' ? ['open', 'closed', 'cancelled'] : status === 'closed' ? ['closed', 'ended', 'cancelled'] : [status] }
function taipeiInput(value: string) { return new Date(new Date(value).getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16) }
function taipei(value: string) { return new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value)) }
const range = (start: number, end: number) => Array.from({ length: end - start + 1 }, (_, index) => start + index)

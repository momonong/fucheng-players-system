import { useEffect, useRef, useState } from 'react'
import { doublesRequest, refreshArrangementSession } from './api'
import { appUrl } from './paths'
import type { AdminDoublesEntry, Competition, DoublesAudit, DoublesEntry, DoublesRoster, DoublesStatus, PublicCompetition } from './types'

type Candidate = { id: string; name: string; distinguishing_note: string | null }
const states: Record<DoublesStatus, string> = { waiting_partner: '等待搭檔', pending: '待管理員確認', confirmed: '正取', waitlisted: '候補', cancelled: '已取消' }
const time = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))
const display = (member: Candidate | DoublesEntry['members'][number]) => `${member.name}（${member.distinguishing_note || '無辨識註記'}）`

// The exact serialized request survives uncertain transport. Once a receipt is
// received, recovery only reads; it must never submit another POST.
function useDoublesWrite(refresh: (receivedReceipt: boolean) => Promise<void>, csrf?: string, resetChallenge?: () => void) {
  const [phase, setPhase] = useState<'idle' | 'writing' | 'unknown' | 'refresh' | 'reading' | 'conflict'>('idle')
  const [message, setMessage] = useState('')
  const [needsChallenge, setNeedsChallenge] = useState(false)
  const pending = useRef<{ url: string; body: string } | null>(null)
  const busy = useRef(false)
  const uncertain = useRef(false)
  const receivedReceipt = useRef(false)
  async function read() {
    if (busy.current) return
    busy.current = true; setPhase('reading')
    try {
      await refresh(receivedReceipt.current)
      pending.current = null; uncertain.current = false; receivedReceipt.current = false
      setPhase('idle'); setMessage('')
    } catch (error) {
      setPhase('refresh')
      setMessage(`${receivedReceipt.current ? '已收到成功回執，請只重新讀取名單' : '名單讀取失敗，請重新讀取'}：${(error as Error).message}`)
    } finally { busy.current = false }
  }
  async function send(url?: string, payload?: Record<string, unknown>, challengeToken?: string) {
    if (busy.current || receivedReceipt.current) return
    if (!pending.current && url && payload) {
      pending.current = { url, body: JSON.stringify({ ...payload, request_id: crypto.randomUUID() }) }
      uncertain.current = false
    }
    if (!pending.current) return
    if (needsChallenge) {
      if (!challengeToken) { setMessage('請完成新的安全驗證，原登記內容與請求編號均已保留。'); return }
      // The server excludes the challenge token from its business fingerprint.
      pending.current.body = JSON.stringify({ ...JSON.parse(pending.current.body), turnstile_token: challengeToken })
      setNeedsChallenge(false)
    }
    busy.current = true; setPhase('writing'); setMessage('')
    try {
      await doublesRequest(pending.current.url, { method: 'POST', body: pending.current.body }, csrf)
      receivedReceipt.current = true
      setPhase('refresh'); busy.current = false; await read()
    } catch (error) {
      const status = (error as Error & { status?: number }).status
      // Once a write can have committed, no later rejection proves it did not.
      if (!status || status >= 500) uncertain.current = true
      if (resetChallenge && (status === 422 || status === 503)) {
        setPhase('unknown'); setNeedsChallenge(true); resetChallenge()
        setMessage(`安全驗證需要重試：${(error as Error).message}。完成新驗證後原樣重試，登記內容與請求編號不變。`)
      } else if (uncertain.current) {
        uncertain.current = true; setPhase('unknown')
        setMessage(status === 401 || status === 403
          ? '身分或安全驗證已失效，原操作結果仍未知，請保留此頁。管理員請在另一分頁以原帳號登入；公開訪客請聯絡管理員核對，不要重新登記。'
          : `結果尚未確認：${(error as Error).message}。原操作已鎖定，請原樣重試。`)
      } else if (status === 409) {
        pending.current = null; setPhase('conflict'); setMessage(`${(error as Error).message}。名單已變更，請先更新再決定操作。`)
      } else {
        pending.current = null; setPhase('idle'); setMessage((error as Error).message)
      }
    } finally { busy.current = false }
  }
  return { phase, message, needsChallenge, locked: phase !== 'idle', isBusy: () => busy.current, send, read }
}
function Recovery({ write, retry, canRetry = true }: { write: ReturnType<typeof useDoublesWrite>; retry?: () => void; canRetry?: boolean }) {
  return <>{write.message && <div className="notice error" role="alert">{write.message}</div>}
    {write.phase === 'unknown' && <button type="button" disabled={!canRetry} onClick={retry || (() => void write.send())}>原樣重試並核對結果</button>}
    {(write.phase === 'refresh' || write.phase === 'conflict') && <button type="button" onClick={() => void write.read()}>重新讀取雙打名單</button>}
    {(write.phase === 'writing' || write.phase === 'reading') && <p role="status">{write.phase === 'writing' ? '正在送出，請稍候…' : '正在讀回名單，請稍候…'}</p>}</>
}
export function DoublesMemberPicker({ label, member, onChange, disabled, admin = false }: { label: string; member: Candidate | null; onChange: (member: Candidate | null) => void; disabled: boolean; admin?: boolean }) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<Candidate[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setRows([]); setSearched(false); setError('')
    if (!query.trim()) { setSearching(false); return }
    setSearching(true)
    const timer = window.setTimeout(() => {
      doublesRequest<Candidate[]>(`/api/${admin ? 'admin' : 'public'}/registration-members?search=${encodeURIComponent(query.trim())}`)
        .then(data => { if (active) { setRows(data); setSearched(true) } })
        .catch(error => { if (active) setError(error.message) })
        .finally(() => { if (active) setSearching(false) })
    }, 250)
    return () => { active = false; window.clearTimeout(timer) }
  }, [query, admin])
  return <fieldset className="doubles-picker" disabled={disabled}><legend>{label}</legend>
    {member && <p className="doubles-selected">已選：<strong>{display(member)}</strong></p>}
    <label>搜尋姓名<input type="search" value={query} maxLength={100} placeholder="輸入姓名，同名請核對註記" onChange={event => { setQuery(event.target.value); onChange(null) }} /></label>
    {searching && <p role="status">搜尋中…</p>}{error && <p role="alert">{error}</p>}
    {searched && !rows.length && <p>找不到名字，請洽管理員協助。</p>}
    {rows.length === 20 && <p>符合的名字較多，請輸入更完整姓名。</p>}
    <div className="public-candidates">{rows.map(row => <button type="button" key={row.id} aria-pressed={member?.id === row.id} onClick={() => onChange(row)}><strong>{row.name}</strong><span>{row.distinguishing_note || '無辨識註記'}</span></button>)}</div>
  </fieldset>
}
function EntryMembers({ entry }: { entry: DoublesEntry }) {
  return <><div className="doubles-members">{entry.members.map((member, index) => <div key={member.member_id}><span className="doubles-member-order">{entry.members.length === 2 ? `第 ${index + 1} 位` : '報名會員'}</span><strong>{member.name}</strong><span>{member.distinguishing_note || '無辨識註記'}</span><span>登記級數 {member.level_snapshot} 級</span></div>)}</div>
    {entry.total_level !== null && <p className={entry.meets_level_rule === false ? 'doubles-rule-warning' : 'doubles-rule'}>兩人合計 {entry.total_level} 級{entry.min_total_level !== null ? `／至少 ${entry.min_total_level} 級` : '・未設門檻'}{entry.meets_level_rule === false ? '・低於門檻，仍可由管理員接受' : entry.meets_level_rule ? '・達到門檻' : ''}</p>}</>
}
function Summary({ competition: c }: { competition: PublicCompetition | Competition }) {
  const s = c.doubles_summary
  return s && <div className="doubles-summary"><span>正取／隊數上限<strong>{s.confirmed}／{c.capacity} 隊</strong></span><span>等待搭檔<strong>{s.waiting_partner} 人</strong></span><span>待管理員確認<strong>{s.pending} 隊</strong></span><span>候補<strong>{s.waitlisted} 隊</strong></span><span>剩餘名額<strong>{s.remaining} 隊</strong></span>{s.pending_promotions > 0 && <span>待遞補<strong>{s.pending_promotions} 隊</strong></span>}</div>
}
function useChallenge(sitekey: string | null, enabled: boolean) {
  const widget = useRef<HTMLDivElement>(null)
  const widgetId = useRef<string | null>(null)
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!sitekey || !enabled) return
    let active = true
    if (!document.getElementById('fucheng-turnstile-script')) {
      const script = document.createElement('script'); script.id = 'fucheng-turnstile-script'
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'; script.async = true
      script.onerror = () => { if (active) setError('安全驗證暫時無法載入，請檢查連線後重試') }; document.head.append(script)
    }
    const timer = window.setInterval(() => {
      if (!active || !widget.current || !window.turnstile || widgetId.current) return
      window.clearInterval(timer)
      widgetId.current = window.turnstile.render(widget.current, { sitekey, action: 'public_registration', appearance: 'interaction-only', callback: (value: string) => { setToken(value); setError('') }, 'expired-callback': () => setToken(''), 'error-callback': () => { setToken(''); setError('安全驗證暫時無法完成，請稍後重試') } })
    }, 100)
    return () => { active = false; window.clearInterval(timer); if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current); widgetId.current = null; setToken('') }
  }, [sitekey, enabled])
  function reset() { setError(''); setToken(''); if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current) }
  return { widget, token, error, reset }
}
export function PublicDoublesRegistration({ competitionId, csrf, sitekey }: { competitionId: string; csrf: string; sitekey: string | null }) {
  const [roster, setRoster] = useState<DoublesRoster | null>(null)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<1 | 2 | null>(null)
  const [first, setFirst] = useState<Candidate | null>(null)
  const [second, setSecond] = useState<Candidate | null>(null)
  const [success, setSuccess] = useState('')
  const [formError, setFormError] = useState('')
  const challenge = useChallenge(sitekey, !!mode && !!first && (mode === 1 || !!second))
  const submittedMode = useRef<1 | 2>(1)
  async function refresh() {
    const data = await doublesRequest<DoublesRoster>(`/api/public/competitions/${competitionId}/doubles`)
    setRoster(data); setError('')
  }
  const write = useDoublesWrite(async receivedReceipt => {
    await refresh(); if (!receivedReceipt) return; setSuccess(submittedMode.current === 1 ? '已送出單人登記：等待搭檔。' : '已送出兩人組隊：待管理員確認。')
    setMode(null); setFirst(null); setSecond(null)
  }, csrf, sitekey ? challenge.reset : undefined)
  useEffect(() => { refresh().catch(error => setError(error.message)) }, [competitionId])
  function start(value: 1 | 2, member?: Candidate) { setMode(value); setFirst(member || null); setSecond(null); setSuccess(''); setFormError('') }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (write.locked || !first || (mode === 2 && !second)) return
    if (mode === 2 && first.id === second?.id) { setFormError('請選擇兩位不同會員，同名時請核對辨識註記。'); return }
    if (sitekey && !challenge.token) { setFormError('請完成安全驗證後再送出。'); return }
    setFormError(''); submittedMode.current = mode || 1
    await write.send(`/api/public/competitions/${competitionId}/doubles`, { member_ids: mode === 2 ? [first.id, second!.id] : [first.id], ...(sitekey ? { turnstile_token: challenge.token } : {}) })
  }
  if (!roster) return <>{error ? <div role="alert">{error}<button onClick={() => refresh().catch(error => setError(error.message))}>重新載入雙打名單</button></div> : <p role="status">載入雙打名單中…</p>}</>
  const c = roster.competition
  return <div className="doubles-public"><a href={appUrl('/competitions')}>← 回比賽清單</a>
    <section className="panel public-competition-info"><p className="section-kicker">雙打組隊</p><h2>{c.name}</h2><p>比賽日期：{c.competition_date}</p><p>報名截止：{time(c.registration_deadline)}</p>{c.notes && <p>{c.notes}</p>}<Summary competition={c} /><p>{c.doubles_min_total_level === null ? '本場未設級數合計門檻。' : `兩人級數合計至少 ${c.doubles_min_total_level} 級；未達門檻仍可送出，由管理員確認。`}</p></section>
    {success && <p className="notice success" role="status">{success}</p>}
    <Recovery write={write} canRetry={!write.needsChallenge || !!challenge.token} retry={() => void write.send(undefined, undefined, challenge.token)} />
    {c.effective_registration_open ? <section className="panel registration-form"><h2>選擇報名方式</h2><p>可請親友代報；請先與搭檔說好，送出後更正請洽管理員。</p>
      <div className="doubles-actions"><button type="button" disabled={write.locked} aria-pressed={mode === 1} onClick={() => start(1)}>我先報名，等待搭檔</button><button type="button" disabled={write.locked} aria-pressed={mode === 2} onClick={() => start(2)}>我們兩人一起報名</button></div>
      {mode && <form onSubmit={submit}>
        <DoublesMemberPicker key={`${mode}-first`} label={mode === 1 ? '報名會員' : '第一位會員'} member={first} onChange={setFirst} disabled={write.locked} />
        {mode === 2 && <DoublesMemberPicker key="second" label="第二位會員" member={second} onChange={setSecond} disabled={write.locked} />}
        {first && (mode === 1 || second) && <div className="doubles-confirm registration-confirm"><h3>送出前核對姓名與辨識註記</h3><p>第一位：<strong>{display(first)}</strong></p>{mode === 2 && second && <p>第二位：<strong>{display(second)}</strong></p>}<p>{mode === 1 ? '送出後會列在等待搭檔名單。' : '請先與搭檔說好。送出後為待管理員確認，不會直接占用正取名額。'}更正請洽管理員。</p>
          {sitekey && <><div ref={challenge.widget} aria-label="安全驗證" />{!challenge.token && <p role="status">安全驗證中，請稍候…</p>}</>}{challenge.error && <p role="alert">{challenge.error}</p>}
          {formError && <p role="alert">{formError}</p>}<button className="registration-submit" disabled={write.locked || (!!sitekey && !challenge.token)}>{mode === 1 ? '確認送出單人登記' : '確認送出兩人組隊'}</button></div>}
      </form>}</section> : <p className="notice">報名已截止，仍可查看名單。</p>}
    {(['waiting_partner', 'pending', 'confirmed', 'waitlisted'] as DoublesStatus[]).map(status => <section className="panel doubles-section" key={status}><h2>{states[status]}（{roster.entries.filter(entry => entry.status === status).length} {status === 'waiting_partner' ? '人' : '隊'}）</h2>
      {roster.entries.filter(entry => entry.status === status).map(entry => <article className="doubles-entry" key={entry.id}><p className="doubles-entry-label">{states[status]}・順位 {entry.sequence}</p><EntryMembers entry={entry} />{status === 'waiting_partner' && c.effective_registration_open && <button disabled={write.locked} aria-label={`和 ${entry.members[0].name} 組隊`} onClick={() => { start(2, { id: entry.members[0].member_id, name: entry.members[0].name, distinguishing_note: entry.members[0].distinguishing_note }); document.querySelector('.registration-form')?.scrollIntoView({ behavior: 'instant', block: 'start' }) }}>和這位組隊</button>}</article>)}
      {!roster.entries.some(entry => entry.status === status) && <p>目前沒有{states[status]}的{status === 'waiting_partner' ? '會員' : '隊伍'}。</p>}</section>)}
  </div>
}

export function DoublesManager({ competition, onLock, username, onRead }: { competition: Competition; onLock: (locked: boolean) => void; username: string; onRead: (competition: Competition) => void }) {
  const [roster, setRoster] = useState<DoublesRoster<Competition, AdminDoublesEntry> | null>(null)
  const [history, setHistory] = useState<DoublesAudit[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const [first, setFirst] = useState<Candidate | null>(null)
  const [second, setSecond] = useState<Candidate | null>(null)
  const [mode, setMode] = useState<1 | 2>(2)
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState('')
  const [operation, setOperation] = useState<{ entry: AdminDoublesEntry; action: 'approve' | 'promote' | 'cancel' | 'split' } | null>(null)
  const [operationReason, setOperationReason] = useState('')
  const reasonDrafts = useRef(new Map<string, string>())
  const completedOperation = useRef<string | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const refreshing = useRef(false)
  const completed = useRef('')
  const endpoint = `/api/admin/competitions/${competition.id}/doubles`
  async function refresh() {
    const [data, audits] = await Promise.all([doublesRequest<DoublesRoster<Competition, AdminDoublesEntry>>(endpoint), doublesRequest<DoublesAudit[]>(endpoint + '/history')])
    setRoster(data); setHistory(audits); onRead(data.competition); setError('')
  }
  const write = useDoublesWrite(async receivedReceipt => { await refresh(); if (!receivedReceipt) { setOperation(null); return }; setSuccess(completed.current); if (completedOperation.current) reasonDrafts.current.delete(completedOperation.current); completedOperation.current = null; setFirst(null); setSecond(null); setReason(''); setOperation(null); setOperationReason('') })
  const interactionLocked = write.locked || loading
  useEffect(() => { onLock(interactionLocked); return () => onLock(false) }, [interactionLocked, onLock])
  useEffect(() => { if (!roster || roster.competition.version !== competition.version) void update() }, [competition.id, competition.version])
  useEffect(() => { if (operation) dialog.current?.showModal() }, [operation])
  async function update() {
    if (refreshing.current || write.locked || write.isBusy()) return
    refreshing.current = true; onLock(true); setLoading(true)
    try { await refresh() } catch (error) { setError((error as Error).message) }
    finally { refreshing.current = false; setLoading(false); onLock(write.locked) }
  }
  const c = roster?.competition || competition
  const readonly = !!c.deleted_at || !['open', 'closed'].includes(c.status)
  const late = c.status === 'closed' || !c.effective_registration_open
  const actionText = { approve: '接受報名', promote: '確認遞補', cancel: '取消登記', split: '拆回等待搭檔' }
  async function mutate(entry: AdminDoublesEntry, action: 'approve' | 'promote' | 'cancel' | 'split', actionReason = '') {
    if (write.locked || refreshing.current || readonly) return
    completedOperation.current = `${entry.id}:${action}`
    completed.current = `${actionText[action]}完成，已更新名單。`; setSuccess('')
    await write.send(`/api/admin/doubles/${entry.id}/${action}`, { version: entry.version, reason: actionReason.trim() || null })
  }
  function selectOperation(entry: AdminDoublesEntry, action: 'approve' | 'promote' | 'cancel' | 'split') {
    if (refreshing.current || write.locked || readonly) return
    if (action === 'cancel' || action === 'split' || late) { setOperation({ entry, action }); setOperationReason(reasonDrafts.current.get(`${entry.id}:${action}`) || '') }
    else void mutate(entry, action)
  }
  async function add(event: React.FormEvent) {
    event.preventDefault(); setFormError('')
    if (!first || (mode === 2 && !second) || write.locked || refreshing.current || readonly) return
    if (mode === 2 && first.id === second!.id) { setFormError('請選擇兩位不同會員。'); return }
    if (late && !reason.trim()) { setFormError('截止後新增登記須填寫原因。'); return }
    completedOperation.current = null
    completed.current = mode === 1 ? '單人登記完成：等待搭檔。' : '兩人組隊完成：待管理員確認。'; setSuccess('')
    await write.send(endpoint, { member_ids: mode === 2 ? [first.id, second!.id] : [first.id], reason: reason.trim() || null })
  }
  async function retryAdmin() {
    try { await refreshArrangementSession(username); await write.send() }
    catch (error) { setError((error as Error).message) }
  }
  const firstWaiting = roster?.entries.find(entry => entry.status === 'waitlisted')?.id
  const auditActions: Record<string, string> = { create: '新增登記', absorbed: '承接至兩人組隊', approve: '接受報名', promote: '候補遞補', cancel: '取消登記', split: '拆隊', waiting_from_split: '拆隊後等待搭檔' }
  return <section id="registration-roster" className="panel doubles-manager" role="region" aria-label="雙打報名管理">
    <div className="section-title"><div><p className="section-kicker">雙打報名管理</p><h2>{c.name}</h2></div><button className="secondary" disabled={interactionLocked || loading} onClick={() => void update()}>更新雙打名單</button></div>
    {readonly && <p className="notice">本場唯讀，不能新增或修改登記。</p>}<Summary competition={c} />
    <p>{c.doubles_min_total_level === null ? '未設級數合計門檻。' : `兩人級數合計至少 ${c.doubles_min_total_level} 級；未達仍可接受，由管理員決定。`}</p><p>等待搭檔與待確認不占正取隊數；接受後依名額與既有候補決定正取或候補。取消不自動遞補。</p>
    {loading && <p role="status">讀取雙打名單中…</p>}{error && <div className="notice error" role="alert">{error}</div>}{success && <p role="status" className="notice success">{success}</p>}<Recovery write={write} retry={() => void retryAdmin()} />
    {!readonly && <details className="doubles-admin-add"><summary>新增登記／重新組隊</summary><p>重新配對請先拆回等待搭檔，再選兩位送出。登記後仍須接受報名。</p><form onSubmit={add}>
      <label>登記人數<select value={mode} disabled={interactionLocked} onChange={event => setMode(Number(event.target.value) as 1 | 2)}><option value={1}>一人，等待搭檔</option><option value={2}>兩人組隊</option></select></label>
      <DoublesMemberPicker label={mode === 1 ? '報名會員' : '第一位會員'} member={first} onChange={setFirst} admin disabled={interactionLocked} />{mode === 2 && <DoublesMemberPicker label="第二位會員" member={second} onChange={setSecond} admin disabled={interactionLocked} />}
      {first && <div className="doubles-confirm"><p>第一位：<strong>{display(first)}</strong></p>{mode === 2 && second && <p>第二位：<strong>{display(second)}</strong></p>}</div>}
      <label>新增原因{late ? '（截止後必填）' : '（選填）'}<input value={reason} maxLength={500} required={late} disabled={interactionLocked} onChange={event => setReason(event.target.value)} /></label>{formError && <p role="alert">{formError}</p>}<button disabled={interactionLocked || !first || (mode === 2 && !second)}>新增雙打登記</button>
    </form></details>}
    {(['waiting_partner', 'pending', 'confirmed', 'waitlisted', 'cancelled'] as DoublesStatus[]).map(status => {
      const entries = roster?.entries.filter(entry => entry.status === status) || []
      const contents = <>{status === 'cancelled' && <p>包含已組隊或拆隊後保留的舊登記。</p>}{entries.map(entry => <article className="doubles-entry" key={entry.id}><p className="doubles-entry-label">{states[status]}・順位 {entry.sequence}</p><EntryMembers entry={entry} />
        {!readonly && status !== 'cancelled' && <div className="doubles-actions">{status === 'pending' && <button disabled={interactionLocked} onClick={() => selectOperation(entry, 'approve')}>接受報名</button>}{status === 'waitlisted' && firstWaiting === entry.id && (c.doubles_summary?.remaining || 0) > 0 && <button disabled={interactionLocked} onClick={() => selectOperation(entry, 'promote')}>確認遞補</button>}{entry.members.length === 2 && <button className="secondary" disabled={interactionLocked} onClick={() => selectOperation(entry, 'split')}>拆回等待搭檔</button>}<button className="danger" disabled={interactionLocked} onClick={() => selectOperation(entry, 'cancel')}>取消登記</button></div>}</article>)}{!entries.length && <p>目前沒有{states[status]}的{status === 'waiting_partner' ? '會員' : '登記'}。</p>}</>
      return status === 'cancelled' ? <details className="doubles-section" key={status}><summary>已取消 {entries.length} 筆</summary>{contents}</details> : <section className="doubles-section" key={status}><h3>{states[status]}（{entries.length} {status === 'waiting_partner' ? '人' : '隊'}）</h3>{contents}</section>
    })}
    <details className="doubles-history"><summary>雙打操作紀錄（{history.length} 筆）</summary><ul className="actor-audits">{history.map(audit => <li key={audit.id}><strong>{auditActions[audit.action] || audit.action}</strong>・{time(audit.created_at)}<p>{roster?.entries.find(entry => entry.id === audit.entry_id)?.members.map(member => display(member)).join(' ＋ ') || '登記紀錄'}<br />{audit.actor_kind === 'public' ? '公開訪客' : audit.actor_kind === 'admin' ? '管理員' : '系統'}：{audit.actor_name}</p>{audit.reason && <p>原因：{audit.reason}</p>}</li>)}</ul></details>
    {operation && <dialog className="competition-confirm-dialog doubles-operation" ref={dialog} aria-label={actionText[operation.action]} onCancel={event => { event.preventDefault(); if (!write.locked) setOperation(null) }}><h2>{actionText[operation.action]}</h2><EntryMembers entry={operation.entry} /><p>{operation.action === 'split' ? '原隊伍將取消，兩位以原登記級數回到等待搭檔。' : operation.action === 'cancel' ? '取消後保留歷史，正取空缺不會自動遞補。' : '本場已截止，請填寫此次操作原因。'}</p><form onSubmit={event => { event.preventDefault(); void mutate(operation.entry, operation.action, operationReason) }}><label>操作原因<input autoFocus maxLength={500} required value={operationReason} disabled={interactionLocked} onChange={event => { const value = event.target.value; reasonDrafts.current.set(`${operation.entry.id}:${operation.action}`, value); setOperationReason(value) }} /></label><Recovery write={write} retry={() => void retryAdmin()} /><div className="doubles-actions"><button type="button" className="secondary" disabled={interactionLocked} onClick={() => setOperation(null)}>暫不操作</button><button disabled={interactionLocked || !operationReason.trim()}>確認{actionText[operation.action]}</button></div></form></dialog>}
  </section>
}

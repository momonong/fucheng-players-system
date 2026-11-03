import { appUrl, appPathname } from './paths'
import { useCallback, useEffect, useRef, useState } from 'react'
import { publicGet } from './publicReads'
import { useVisibleRefresh } from './useVisibleRefresh'
import { doublesRequest, request } from './api'
import { PublicDoublesRegistration } from './DoublesRegistration'
import type { Diet, PublicCompetition, DoublesRoster } from './types'

type IndividualRoster = { competition: PublicCompetition; entries: { name: string; distinguishing_note: string | null; status: 'confirmed' | 'waitlisted'; queue_sequence: number }[] }
type Competition = PublicCompetition
type Candidate = { id: string; name: string; distinguishing_note: string | null }
type Result = { status: string; member_name: string; distinguishing_note: string | null; diet: Diet }
type RegistrationSession = { csrf_token: string; turnstile_sitekey: string | null }
type TurnstileApi = { render: (element: HTMLElement, options: Record<string, unknown>) => string; reset: (id: string) => void; remove: (id: string) => void }
declare global { interface Window { turnstile?: TurnstileApi } }
type Audit = { id: string; action: string; actor_kind: string; actor_name: string; created_at: string; registration_id: string; member_name: string; distinguishing_note: string | null; queue_sequence: number; reason: string | null; changes: Record<string, {before: unknown; after: unknown}> }
const diets: Record<Diet, string> = { omnivore: '葷食', vegetarian: '素食', unset: '未設定' }
const mealOptions = ['omnivore', 'vegetarian'] as const
const states: Record<string, string> = { confirmed: '正取', waitlisted: '候補', cancelled: '已取消' }
const time = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))

async function publicRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  if (!options.method || options.method === 'GET') return publicGet<T>(url)
  let response: Response
  try { response = await fetch(appUrl(url), { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...options.headers } }) }
  catch { throw new Error('連線暫時中斷，請檢查網路後重試') }
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json().catch(() => null) : null
    const message = typeof body?.detail === 'string' ? body.detail : '安全檢查或連線暫時無法完成，請稍後重試'
    throw Object.assign(new Error(message), { status: response.status })
  }
  return response.json()
}

export function PublicRegistrationPortal() {
  const [items, setItems] = useState<Competition[]>([])
  const [selected, setSelected] = useState<Competition | null>(null)
  const [csrf, setCsrf] = useState('')
  const [turnstileSitekey, setTurnstileSitekey] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [rosterRevision, setRosterRevision] = useState(0)
  const listSequence = useRef(0)
  const portalMounted = useRef(false)
  const [individualLocked, setIndividualLocked] = useState(false)
  const [rosterAvailable, setRosterAvailable] = useState(true)
  const writeLock = useRef(false)
  const lockWrite = useCallback((value: boolean) => { writeLock.current = value; setIndividualLocked(value) }, [])
  const isWriteLocked = useCallback(() => writeLock.current, [])
  const routeId = appPathname().match(/^\/register\/([^/]+)$/)?.[1]
  useEffect(() => {
    let active = true
    portalMounted.current = true
    const sequence = ++listSequence.current
    setLoading(true); setError('')
    Promise.all([
      routeId ? publicRequest<RegistrationSession>('/api/public/registration-session') : Promise.resolve({ csrf_token: '', turnstile_sitekey: null }),
      publicRequest<Competition[]>('/api/public/registration-rosters'),
    ]).then(async ([session, competitions]) => {
      if (!active) return
      setCsrf(session.csrf_token); setTurnstileSitekey(session.turnstile_sitekey)
      if (sequence === listSequence.current) setItems(competitions)
      if (routeId) {
        const match = competitions.find(c => c.id === routeId)
        if (match) setSelected(match)
        else {
          try { const roster = await doublesRequest<DoublesRoster>(`/api/public/competitions/${routeId}/doubles`); if (active) setSelected(roster.competition) }
          catch { if (active) setError('找不到這場比賽的公開名單，請選擇其他比賽或洽管理員。') }
        }
      }
    }).catch(e => { if (active && sequence === listSequence.current) setError(e.message) }).finally(() => { if (active && sequence === listSequence.current) setLoading(false) })
    return () => { active = false; portalMounted.current = false; listSequence.current++ }
  }, [retry, routeId])
  useVisibleRefresh(async fresh => {
    const sequence = ++listSequence.current
    try {
      const values = await publicGet<Competition[]>('/api/public/registration-rosters', fresh)
      if (portalMounted.current && sequence === listSequence.current) { setItems(values); setError('') }
    } catch (failure) { if (portalMounted.current && sequence === listSequence.current) setError((failure as Error).message) }
    finally { if (portalMounted.current && sequence === listSequence.current) setLoading(false) }
  }, 5000, !routeId)
  return <>
    <main className="public-registration">
      <h1 className="visually-hidden">比賽報名</h1>
      <p className="registration-intro">找到自己的名字，就能報名。不用帳號、不用密碼。</p>
      {loading ? <p role="status">載入比賽中…</p> : error ? <div className="notice error" role="alert">{error}<button onClick={() => setRetry(r => r + 1)}>重新載入</button></div> : selected ?
        selected.registration_mode === 'doubles' ? <PublicDoublesRegistration key={selected.id} competitionId={selected.id} csrf={csrf} sitekey={turnstileSitekey} /> : <><RegistrationForm key={selected.id} competition={selected} csrf={csrf} turnstileSitekey={turnstileSitekey} onRegistered={() => setRosterRevision(n => n + 1)} onLocked={lockWrite} available={rosterAvailable} /><PublicIndividualRoster competitionId={selected.id} revision={rosterRevision} onUpdate={setSelected} locked={individualLocked} isWriteLocked={isWriteLocked} onAvailability={setRosterAvailable} /></> : <>
          <h2>1. 選擇比賽</h2>
          {!items.length && <div className="panel"><p>目前沒有可查看的比賽。</p><p>如需協助，請洽球館管理員。</p></div>}
          <div className="public-competitions">{items.map(c => <article className="panel" key={c.id}>
            <h3>{c.name}</h3><CompetitionInfo competition={c} />
            <a className="registration-button" href={appUrl(`/register/${c.id}`)}>{c.effective_registration_open ? '報名／查看名單' : '查看名單'}：{c.name}</a>
          </article>)}</div>
        </>}
      <p className="registration-help">如需取消、更正或找不到名字，請洽管理員協助。</p>
    </main>
  </>
}

function PublicIndividualRoster({ competitionId, revision, onUpdate, locked, isWriteLocked, onAvailability }: { competitionId: string; revision: number; onUpdate: (competition: Competition) => void; locked: boolean; isWriteLocked: () => boolean; onAvailability: (available: boolean) => void }) {
  const [roster, setRoster] = useState<IndividualRoster | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const readSequence = useRef(0)
  const mounted = useRef(false)
  const load = useCallback(async (fresh = false) => {
    if (isWriteLocked()) return
    const sequence = ++readSequence.current
    setLoading(true); setError('')
    try {
      const value = await publicGet<IndividualRoster>(`/api/public/competitions/${competitionId}/registrations`, fresh)
      if (mounted.current && sequence === readSequence.current && !isWriteLocked()) { setRoster(value); onUpdate(value.competition); onAvailability(true) }
    } catch (failure) {
      if (mounted.current && sequence === readSequence.current && !isWriteLocked()) {
        setError((failure as Error).message)
        if ((failure as { status?: number }).status === 404) { setRoster(null); onAvailability(false) }
      }
    } finally { if (mounted.current && sequence === readSequence.current) setLoading(false) }
  }, [competitionId, onUpdate, isWriteLocked, onAvailability])
  useEffect(() => {
    mounted.current = true; void load(revision > 0)
    return () => { mounted.current = false; readSequence.current++ }
  }, [load, revision, refresh])
  useVisibleRefresh(fresh => load(fresh), 5000, !locked)

  return <section className="public-roster" aria-label="比賽報名名單">
    <div className="section-title"><h2>報名名單</h2><button type="button" className="secondary" disabled={loading || locked} onClick={() => setRefresh(n => n + 1)}>{loading ? '更新中…' : '更新名單'}</button></div>
    <p>名單會自動更新，依報名順序顯示；同名時請核對註記。候補需由管理員確認遞補。</p>
    {error && <p className="notice error" role="alert">名單更新失敗：{error}。請按「更新名單」重試。</p>}
    {loading && !roster && <p role="status">載入名單中…</p>}
    {roster && <div className="public-roster-groups">{(['confirmed', 'waitlisted'] as const).map(status => {
      const entries = roster.entries.filter(entry => entry.status === status)
      return <section className="panel" key={status} aria-label={`${states[status]}名單`}><h3>{states[status]}（{entries.length} 人）</h3>
        {entries.length ? <ol className="public-roster-names">{entries.map(entry => <li key={entry.queue_sequence}><strong>{entry.name}</strong>{entry.distinguishing_note && <span>{entry.distinguishing_note}</span>}</li>)}</ol> : <p>目前沒有{states[status]}會員。</p>}
      </section>
    })}</div>}
  </section>
}

function CompetitionInfo({ competition: c }: { competition: Competition }) {
  return <><p>比賽日期：{c.competition_date}</p><p>報名截止：{time(c.registration_deadline)}</p>
    {c.notes && <p className="competition-notes">{c.notes}</p>}
    {c.registration_mode === 'doubles' ? <p>雙打組隊・正取 {c.doubles_summary?.confirmed || 0}／{c.capacity} 隊・等待搭檔 {c.doubles_summary?.waiting_partner || 0} 人</p> : <div className="self-counts"><span>正取／名額 <strong>{c.confirmed}／{c.capacity}</strong></span><span>候補 <strong>{c.waitlisted}</strong></span><span>剩餘名額 <strong>{c.remaining}</strong></span></div>}
    {c.waitlisted > 0 && c.remaining > 0 && <p>空缺由管理員依序確認候補，新報名會加入候補。</p>}</>
}

function RegistrationForm({ competition: c, csrf, turnstileSitekey, onRegistered, onLocked, available }: { competition: Competition; csrf: string; turnstileSitekey: string | null; onRegistered: () => void; onLocked: (locked: boolean) => void; available: boolean }) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [member, setMember] = useState<Candidate | null>(null)
  const [diet, setDiet] = useState<(typeof mealOptions)[number]>('omnivore')
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [busy, setBusy] = useState(false)
  const [unknown, setUnknown] = useState(false)
  const uncertain = useRef(false)
  const [result, setResult] = useState<Result | null>(null)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileError, setTurnstileError] = useState('')
  const lock = useRef(false)
  const pending = useRef<{ signature: string; key: string } | null>(null)
  const widget = useRef<HTMLDivElement>(null)
  const widgetId = useRef<string | null>(null)
  useEffect(() => {
    if (!turnstileSitekey || !member || !widget.current) return
    let active = true
    const scriptId = 'fucheng-turnstile-script'
    if (!document.getElementById(scriptId)) {
      const script = document.createElement('script')
      script.id = scriptId
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
      script.async = true
      script.onerror = () => { if (active) setTurnstileError('安全驗證暫時無法載入，請檢查連線後重試') }
      document.head.append(script)
    }
    const timer = window.setInterval(() => {
      if (!active || !widget.current || !window.turnstile || widgetId.current) return
      window.clearInterval(timer)
      widgetId.current = window.turnstile.render(widget.current, {
        sitekey: turnstileSitekey, action: 'public_registration', appearance: 'interaction-only',
        callback: (token: string) => { setTurnstileToken(token); setTurnstileError('') },
        'expired-callback': () => setTurnstileToken(''),
        'error-callback': () => { setTurnstileToken(''); setTurnstileError('安全驗證暫時無法完成，請稍後重試') },
      })
    }, 100)
    return () => { active = false; window.clearInterval(timer); if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current); widgetId.current = null; setTurnstileToken('') }
  }, [turnstileSitekey, !!member])
  function resetTurnstile() { setTurnstileToken(''); if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current) }
  useEffect(() => {
    let active = true
    setSearched(false); setSearchError('')
    if (!query.trim()) { setCandidates([]); setSearching(false); return }
    setSearching(true)
    const timer = setTimeout(() => {
      publicRequest<Candidate[]>(`/api/public/registration-members?search=${encodeURIComponent(query.trim())}`)
        .then(rows => { if (active) { setCandidates(rows); setSearched(true) } })
        .catch(e => { if (active) setSearchError(e.message) })
        .finally(() => { if (active) setSearching(false) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!member || lock.current) return
    if (turnstileSitekey && !turnstileToken) { setSubmitError('請稍候，完成安全驗證後再送出'); return }
    lock.current = true; onLocked(true); setBusy(true); setSubmitError('')
    const signature = `${member.id}:${diet}`
    if (pending.current?.signature !== signature) pending.current = { signature, key: crypto.randomUUID() }
    try {
      const receipt = await publicRequest<Result>(`/api/public/competitions/${c.id}/registrations`, {
        method: 'POST', headers: { 'X-CSRF-Token': csrf },
        body: JSON.stringify({ member_id: member.id, diet, request_id: pending.current.key,
          ...(turnstileSitekey ? { turnstile_token: turnstileToken } : {}) }),
      })
      uncertain.current = false; setUnknown(false); onLocked(false); setResult(receipt); onRegistered()
    } catch (e) {
      const failure = e as Error & { status?: number }
      setSubmitError(failure.message)
      if (!failure.status || failure.status >= 500 || uncertain.current) { uncertain.current = true; setUnknown(true) }
      else onLocked(false)
      // Network uncertainty keeps the same token/key for receipt readback;
      // a definite challenge failure gets a fresh token and keeps the key.
      if (failure.status === 422 || failure.status === 503) resetTurnstile()
    }
    finally { lock.current = false; setBusy(false) }
  }
  if (result) return <section className="panel registration-receipt" aria-label="報名結果">
    <p className="eyebrow">{c.name}</p><h2 role="status">{result.status === 'cancelled' ? '這筆報名已取消' : '報名完成'}</h2>
    <p className="receipt-name">{result.member_name}{result.distinguishing_note && `（${result.distinguishing_note}）`}</p>
    <p>報名結果：<strong className="receipt-status">{states[result.status]}</strong></p><p>當次餐食：{diets[result.diet]}</p>
    <p>{result.status === 'waitlisted' ? '目前為候補，請等候管理員確認遞補。' : result.status === 'cancelled' ? '如需重新報名，請回比賽清單再次操作。' : '已完成登記，請留意比賽時間。'}</p>
    <a className="registration-button" href={appUrl("/competitions")}>回比賽清單</a>
  </section>
  return <>
    <a href={appUrl("/competitions")}>← 回比賽清單</a>
    <section className="panel public-competition-info"><h2>{c.name}</h2><CompetitionInfo competition={c} /></section>
    {(!c.effective_registration_open || !available) && !unknown ? <p className="notice">{available ? '報名已截止，仍可查看下方名單。' : '目前無法讀取這場比賽，暫停新報名；請洽管理員確認。'}</p> : <form className="panel registration-form" onSubmit={submit}>
      <h2>2. 找到自己的名字</h2>
      <label>搜尋姓名<input type="search" value={query} onChange={e => { setQuery(e.target.value); setMember(null); setSubmitError('') }} placeholder="輸入自己的名字" maxLength={100} disabled={busy || unknown} /></label>
      {searching && <p role="status">搜尋中…</p>}{searchError && <p role="alert">{searchError}</p>}
      {searched && !searching && !candidates.length && <p>找不到名字，請洽管理員協助，不用另外註冊。</p>}
      {searched && candidates.length === 20 && <p>符合的名字較多，請輸入更完整的姓名。</p>}
      {!searching && <div className="public-candidates">{candidates.map(item => <button type="button" disabled={busy || unknown} aria-pressed={member?.id === item.id} key={item.id} onClick={() => { setMember(item); setSubmitError('') }}>
        <strong>{item.name}</strong><span>{item.distinguishing_note || '無辨識註記'}{member?.id === item.id ? ' ✓ 已選取' : ''}</span>
      </button>)}</div>}
      {member && <>
        <h2>3. 選擇這次的葷素</h2>
        <fieldset className="meal-options"><legend>當次餐食</legend>{mealOptions.map(value => <label key={value}><input type="radio" name="meal" value={value} checked={diet === value} disabled={busy || unknown} onChange={() => setDiet(value)} />{diets[value]}</label>)}</fieldset>
        <div className="registration-confirm"><h2>4. 確認報名</h2><p>姓名：<strong>{member.name}</strong>{member.distinguishing_note && `（${member.distinguishing_note}）`}</p><p>餐食：{diets[diet]}</p><p>請確認選到自己的名字，同名時請核對註記。</p></div>
        {turnstileSitekey && <div className="registration-security"><div ref={widget} aria-label="安全驗證" />{turnstileError && <p role="alert">{turnstileError}</p>}</div>}
        {submitError && <div className="notice error" role="alert">{submitError}<p>姓名與餐食已保留。若已送出但不確定結果，可再試一次或洽管理員確認。</p></div>}
        <button className="registration-submit" disabled={busy}>{busy ? '報名中，請稍候…' : `確認以 ${member.name} 報名`}</button>
      </>}
    </form>}
  </>
}

export function RegistrationHistory({ competitionId, registrations }: { competitionId: string; registrations: unknown }) {
  const [entries, setEntries] = useState<Audit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; setEntries([]); setLoading(true); setError(''); request<Audit[]>(`/api/admin/competitions/${competitionId}/history`).then(rows => { if (active) { setEntries(rows); setLoading(false) } }).catch(e => { if (active) { setError(e.message); setLoading(false) } }); return () => { active = false } }, [competitionId, registrations])
  const actions: Record<string,string> = { create:'報名', cancel:'取消報名', promote:'確認遞補', diet:'修改餐食', level:'調整當次級數' }
  return <details className="no-print registration-history"><summary>報名操作稽核</summary>{loading && <p role="status">載入本場歷史中…</p>}{error && <p role="alert">{error}</p>}<ul className="actor-audits">{entries.map(row => <li key={row.id}><strong>{row.member_name}{row.distinguishing_note && `（${row.distinguishing_note}）`}・順位 {row.queue_sequence}</strong><br />{row.actor_kind === 'public' ? '免登入報名' : row.actor_kind === 'admin' ? '管理員' : '系統'}：{row.actor_name}・{actions[row.action] ?? row.action}・{time(row.created_at)}{row.changes.competition_level && <p>當次級數：{String(row.changes.competition_level.before ?? '未建立')} → {String(row.changes.competition_level.after)} 級</p>}{row.reason && <p>原因：{row.reason}</p>}</li>)}</ul></details>
}

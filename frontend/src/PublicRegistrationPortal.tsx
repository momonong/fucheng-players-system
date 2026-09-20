import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import type { Diet } from './types'

type Competition = { id: string; name: string; competition_date: string; registration_deadline: string; notes: string | null; capacity: number; confirmed: number; waitlisted: number; remaining: number }
type Candidate = { id: string; name: string; distinguishing_note: string | null }
type Result = { status: string; member_name: string; distinguishing_note: string | null; diet: Diet }
type Audit = { id: string; action: string; actor_kind: string; actor_name: string; created_at: string; registration_id: string; member_name: string; distinguishing_note: string | null; queue_sequence: number; reason: string | null; changes: Record<string, {before: unknown; after: unknown}> }
const diets: Record<Diet, string> = { omnivore: '葷食', vegetarian: '素食', unset: '未設定' }
const mealOptions = ['omnivore', 'vegetarian'] as const
const states: Record<string, string> = { confirmed: '正取', waitlisted: '候補', cancelled: '已取消' }
const time = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))

async function publicRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...options.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: '連線失敗，請稍後再試' }))
    throw new Error(body.detail ?? '操作失敗，請稍後再試')
  }
  return response.json()
}

export function PublicRegistrationPortal() {
  const [items, setItems] = useState<Competition[]>([])
  const [selected, setSelected] = useState<Competition | null>(null)
  const [csrf, setCsrf] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const routeId = location.pathname.match(/^\/register\/([^/]+)$/)?.[1]
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([
      publicRequest<{ csrf_token: string }>('/api/public/registration-session'),
      publicRequest<Competition[]>('/api/public/competitions'),
    ]).then(([session, competitions]) => {
      if (!active) return
      setCsrf(session.csrf_token); setItems(competitions)
      if (routeId) {
        const match = competitions.find(c => c.id === routeId)
        if (match) setSelected(match)
        else setError('這場比賽目前未開放報名，請選擇其他比賽或洽管理員。')
      }
    }).catch(e => { if (active) { setError(e.message); setLoading(false) } }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [retry, routeId])
  return <>
    <header className="admin-header"><div><p className="eyebrow">府城球館</p><h1>比賽報名</h1></div><a href="/admin">管理員入口</a></header>
    <main className="public-registration">
      <p className="registration-intro">找到自己的名字，就能報名。不用帳號、不用密碼。</p>
      {loading ? <p role="status">載入比賽中…</p> : error ? <div className="notice error" role="alert">{error}<button onClick={() => setRetry(r => r + 1)}>重新載入</button></div> : selected ?
        <RegistrationForm key={selected.id} competition={selected} csrf={csrf} /> : <>
          <h2>1. 選擇比賽</h2>
          {!items.length && <div className="panel"><p>目前沒有開放報名的比賽。</p><p>如需協助，請洽球館管理員。</p></div>}
          <div className="public-competitions">{items.map(c => <article className="panel" key={c.id}>
            <h3>{c.name}</h3><CompetitionInfo competition={c} />
            <a className="registration-button" href={`/register/${c.id}`}>我要報名：{c.name}</a>
          </article>)}</div>
        </>}
      <p className="registration-help">如需取消、更正或找不到名字，請洽管理員協助。</p>
    </main>
  </>
}

function CompetitionInfo({ competition: c }: { competition: Competition }) {
  return <><p>比賽日期：{c.competition_date}</p><p>報名截止：{time(c.registration_deadline)}</p>
    {c.notes && <p className="competition-notes">{c.notes}</p>}
    <div className="self-counts"><span>正取／名額 <strong>{c.confirmed}／{c.capacity}</strong></span><span>候補 <strong>{c.waitlisted}</strong></span><span>剩餘名額 <strong>{c.remaining}</strong></span></div>
    {c.waitlisted > 0 && c.remaining > 0 && <p>空缺由管理員依序確認候補，新報名會加入候補。</p>}</>
}

function RegistrationForm({ competition: c, csrf }: { competition: Competition; csrf: string }) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [member, setMember] = useState<Candidate | null>(null)
  const [diet, setDiet] = useState<(typeof mealOptions)[number]>('omnivore')
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const lock = useRef(false)
  const pending = useRef<{ signature: string; key: string } | null>(null)
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
    lock.current = true; setBusy(true); setSubmitError('')
    const signature = `${member.id}:${diet}`
    if (pending.current?.signature !== signature) pending.current = { signature, key: crypto.randomUUID() }
    try {
      const receipt = await publicRequest<Result>(`/api/public/competitions/${c.id}/registrations`, {
        method: 'POST', headers: { 'X-CSRF-Token': csrf },
        body: JSON.stringify({ member_id: member.id, diet, request_id: pending.current.key }),
      })
      setResult(receipt)
    } catch (e) { setSubmitError((e as Error).message) }
    finally { lock.current = false; setBusy(false) }
  }
  if (result) return <section className="panel registration-receipt" aria-label="報名結果">
    <p className="eyebrow">{c.name}</p><h2 role="status">{result.status === 'cancelled' ? '這筆報名已取消' : '報名完成'}</h2>
    <p className="receipt-name">{result.member_name}{result.distinguishing_note && `（${result.distinguishing_note}）`}</p>
    <p>報名結果：<strong className="receipt-status">{states[result.status]}</strong></p><p>當次餐食：{diets[result.diet]}</p>
    <p>{result.status === 'waitlisted' ? '目前為候補，請等候管理員確認遞補。' : result.status === 'cancelled' ? '如需重新報名，請回比賽清單再次操作。' : '已完成登記，請留意比賽時間。'}</p>
    <a className="registration-button" href="/competitions">回比賽清單</a>
  </section>
  return <>
    <a href="/competitions">← 回比賽清單</a>
    <section className="panel public-competition-info"><h2>{c.name}</h2><CompetitionInfo competition={c} /></section>
    <form className="panel registration-form" onSubmit={submit}>
      <h2>2. 找到自己的名字</h2>
      <label>搜尋姓名<input type="search" value={query} onChange={e => { setQuery(e.target.value); setMember(null); setSubmitError('') }} placeholder="輸入自己的名字" maxLength={100} disabled={busy} /></label>
      {searching && <p role="status">搜尋中…</p>}{searchError && <p role="alert">{searchError}</p>}
      {searched && !searching && !candidates.length && <p>找不到名字，請洽管理員協助，不用另外註冊。</p>}
      {searched && candidates.length === 20 && <p>符合的名字較多，請輸入更完整的姓名。</p>}
      {!searching && <div className="public-candidates">{candidates.map(item => <button type="button" disabled={busy} aria-pressed={member?.id === item.id} key={item.id} onClick={() => { setMember(item); setSubmitError('') }}>
        <strong>{item.name}</strong><span>{item.distinguishing_note || '無辨識註記'}{member?.id === item.id ? ' ✓ 已選取' : ''}</span>
      </button>)}</div>}
      {member && <>
        <h2>3. 選擇這次的葷素</h2>
        <fieldset className="meal-options"><legend>當次餐食</legend>{mealOptions.map(value => <label key={value}><input type="radio" name="meal" value={value} checked={diet === value} disabled={busy} onChange={() => setDiet(value)} />{diets[value]}</label>)}</fieldset>
        <div className="registration-confirm"><h2>4. 確認報名</h2><p>姓名：<strong>{member.name}</strong>{member.distinguishing_note && `（${member.distinguishing_note}）`}</p><p>餐食：{diets[diet]}</p><p>請確認選到自己的名字，同名時請核對註記。</p></div>
        {submitError && <div className="notice error" role="alert">{submitError}<p>姓名與餐食已保留。若已送出但不確定結果，可再試一次或洽管理員確認。</p></div>}
        <button className="registration-submit" disabled={busy}>{busy ? '報名中，請稍候…' : `確認以 ${member.name} 報名`}</button>
      </>}
    </form>
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

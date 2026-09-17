import { useEffect, useMemo, useState } from 'react'
import * as api from './api'
import type { AdminMember, AuditEntry, Diet, MemberDraft, PublicMember } from './types'
import { CompetitionManager } from './CompetitionManager'

const dietText: Record<Diet, string> = { unset: '未設定', omnivore: '葷食', vegetarian: '素食' }
const fieldText: Record<string, string> = {
  name: '姓名', distinguishing_note: '辨識註記', legacy_number: '原會員編號',
  level: '級數', diet: '葷素', is_active: '啟用狀態',
}
const emptyDraft: MemberDraft = {
  name: '', distinguishing_note: '', legacy_number: '', level: 1, diet: 'omnivore', is_active: true,
}

export function App() {
  const adminPage = location.pathname.startsWith('/admin')
  return adminPage ? <AdminPage /> : <PublicPage />
}

function PublicPage() {
  const [members, setMembers] = useState<PublicMember[]>([])
  const [printMembers, setPrintMembers] = useState<PublicMember[]>([])
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [preparingPrint, setPreparingPrint] = useState(false)

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      setLoading(true)
      setError('')
      api.publicMembers(search, level)
        .then(result => { if (active) setMembers(result) })
        .catch((e: Error) => { if (active) setError(e.message) })
        .finally(() => { if (active) setLoading(false) })
    }, 150)
    return () => { active = false; clearTimeout(timer) }
  }, [search, level])

  useEffect(() => {
    api.publicMembers('', '').then(setPrintMembers).catch((e: Error) => setError(e.message))
  }, [])

  const groups = useMemo(() => {
    const map = new Map<number, PublicMember[]>()
    members.forEach(member => map.set(member.level, [...(map.get(member.level) ?? []), member]))
    return [...map.entries()].sort(([a], [b]) => a - b)
  }, [members])
  const printColumns = useMemo(
    () => range(1, 10).map(groupLevel => printMembers.filter(member => member.level === groupLevel)),
    [printMembers],
  )
  const printRowCount = Math.max(0, ...printColumns.map(list => list.length))

  async function printRoster() {
    setPreparingPrint(true)
    setError('')
    try {
      setPrintMembers(await api.publicMembers('', ''))
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
      window.print()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setPreparingPrint(false)
    }
  }

  return <>
    <header className="hero">
      <div><p className="eyebrow">府城球館</p><h1>會員硬實力分級</h1><p>依級數查看目前啟用會員名單</p></div>
      <a className="admin-link no-print" href="/admin">管理員登入</a>
    </header>
    <main>
      <section className="filters no-print" aria-label="搜尋與篩選">
        <label>搜尋姓名或辨識註記<input value={search} onChange={e => setSearch(e.target.value)} placeholder="例如：林先生" type="search" /></label>
        <label>級數<select value={level} onChange={e => setLevel(e.target.value)}><option value="">全部級數</option>{range(1, 10).map(n => <option key={n}>{n}</option>)}</select></label>
        <button type="button" onClick={printRoster} disabled={preparingPrint}>{preparingPrint ? '準備列印中…' : '列印／另存 PDF'}</button>
      </section>
      <p className="result-summary" aria-live="polite">{loading ? '載入名單中…' : `共 ${members.length} 位會員`}</p>
      {error && <Notice kind="error">{error}</Notice>}
      {!loading && !members.length && <div className="empty">目前沒有符合條件的會員。</div>}
      <div className="level-grid">{groups.map(([groupLevel, list]) => <section className="level-card" key={groupLevel}>
        <h2>{groupLevel} 級 <span>{list.length} 人</span></h2>
        <table><thead><tr><th>姓名</th></tr></thead><tbody>{list.map(member => <tr key={member.id}>
          <td><span className="public-member-name"><strong>{member.name}</strong>{member.distinguishing_note && <small>{member.distinguishing_note}</small>}</span></td>
        </tr>)}</tbody></table>
      </section>)}</div>
    </main>
    <section className="print-sheet" aria-label="府城會員參考分級表">
      <div className="print-heading"><h1>府城會員參考分級表</h1><p>共 {printMembers.length} 位啟用會員</p></div>
      <table className="print-roster">
        <colgroup><col className="print-row-number" />{range(1, 10).map(n => <col key={n} />)}</colgroup>
        <thead><tr><th scope="col">序</th>{range(1, 10).map(n => <th scope="col" key={n}>{n}級</th>)}</tr></thead>
        <tbody>{range(0, printRowCount - 1).map(row => <tr key={row}>
          <th scope="row">{row + 1}</th>
          {printColumns.map((list, column) => {
            const member = list[row]
            return <td key={column}>{member && <span>{member.name}{member.distinguishing_note && <small>（{member.distinguishing_note}）</small>}</span>}</td>
          })}
        </tr>)}</tbody>
      </table>
    </section>
    <footer>資料如有疑問，請洽球館管理員。</footer>
  </>
}

function AdminPage() {
  const [username, setUsername] = useState<string | null>(null)
  const [checking, setChecking] = useState(true)
  useEffect(() => { api.restoreSession().then(setUsername).catch(() => {}).finally(() => setChecking(false)) }, [])
  if (checking) return <main><p>確認登入狀態中…</p></main>
  if (!username) return <Login onLogin={setUsername} />
  if (location.pathname.startsWith('/admin/competitions')) return <CompetitionManager username={username} onLogout={() => setUsername(null)} />
  return <MemberManager username={username} onLogout={() => setUsername(null)} />
}

function Login({ onLogin }: { onLogin: (name: string) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { onLogin(await api.login(username, password)) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <main className="login-shell"><a href="/">← 返回公開名單</a><form className="panel login" onSubmit={submit}>
    <p className="eyebrow">府城球館</p><h1>管理員登入</h1>
    {error && <Notice kind="error">{error}</Notice>}
    <label>帳號<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
    <label>密碼<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
    <button disabled={busy}>{busy ? '登入中…' : '登入'}</button>
  </form></main>
}

function MemberManager({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [members, setMembers] = useState<AdminMember[]>([])
  const [selected, setSelected] = useState<AdminMember | null>(null)
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), notice.kind === 'success' ? 3500 : 8000)
    return () => window.clearTimeout(timer)
  }, [notice])
  const load = () => api.adminMembers().then(setMembers).catch(e => setNotice({ kind: 'error', text: e.message }))
  const reloadSelected = async (memberId: string) => {
    try {
      const fresh = await api.adminMembers()
      setMembers(fresh)
      setSelected(fresh.find(item => item.id === memberId) ?? null)
      setNotice({ kind: 'success', text: '已載入最新會員資料，請確認後重新輸入變更' })
    } catch (e) {
      setNotice({ kind: 'error', text: (e as Error).message })
    }
  }
  useEffect(() => { load() }, [])
  const shown = members.filter(member => `${member.name} ${member.distinguishing_note ?? ''} ${member.legacy_number ?? ''}`.includes(query))
  async function signOut() { try { await api.logout(); onLogout() } catch (e) { setNotice({ kind: 'error', text: (e as Error).message }) } }
  return <>
    <header className="admin-header"><div><p className="eyebrow">會員管理</p><h1>府城球館</h1></div><div className="header-actions"><span>{username}</span><a href="/admin/competitions">比賽管理</a><a href="/">公開名單</a><button className="secondary" onClick={signOut}>登出</button></div></header>
    {notice && <Toast kind={notice.kind} onClose={() => setNotice(null)}>{notice.text}</Toast>}
    <main className="admin-main">
      <section className="member-list panel">
        <div className="section-title"><div><h2>會員</h2><p>共 {members.length} 筆，停用資料仍保留</p></div><button onClick={() => { setAdding(true); setSelected(null) }}>新增會員</button></div>
        <label className="search-label">搜尋會員<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <div className="member-rows">{shown.map(member => <button className={`member-row ${selected?.id === member.id ? 'selected' : ''}`} key={member.id} onClick={() => { setSelected(member); setAdding(false) }}>
          <span><strong>{member.name}</strong>{member.distinguishing_note && <small>{member.distinguishing_note}</small>}</span>
          <span>{member.level} 級</span><span className={member.is_active ? 'status active' : 'status inactive'}>{member.is_active ? '啟用' : '停用'}</span>
        </button>)}</div>
      </section>
      <section className="editor-area">
        {adding && <MemberEditor key="new" onSaved={member => { setAdding(false); setSelected(member); setNotice({ kind: 'success', text: '會員已新增' }); load() }} />}
        {selected && <MemberEditor key={`${selected.id}-${selected.version}`} member={selected} onSaved={member => { setSelected(member); setNotice({ kind: 'success', text: '會員資料已儲存' }); load() }} onConflict={() => reloadSelected(selected.id)} />}
        {!adding && !selected && <div className="panel empty editor-empty">請選擇會員，或新增一位會員。</div>}
      </section>
    </main>
  </>
}

function MemberEditor({ member, onSaved, onConflict }: { member?: AdminMember; onSaved: (m: AdminMember) => void; onConflict?: () => void }) {
  const [draft, setDraft] = useState<MemberDraft>(member ? {
    name: member.name, distinguishing_note: member.distinguishing_note ?? '', legacy_number: member.legacy_number ?? '',
    level: member.level, diet: member.diet, is_active: member.is_active, version: member.version,
  } : emptyDraft)
  const [state, setState] = useState<'idle' | 'saving' | 'error' | 'conflict'>('idle')
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState<AuditEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)
  function set<K extends keyof MemberDraft>(key: K, value: MemberDraft[K]) { setDraft(current => ({ ...current, [key]: value })) }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setState('saving'); setMessage('')
    try { onSaved(await api.saveMember(draft, member?.id)); setState('idle') }
    catch (e) { const err = e as Error & { status?: number }; setState(err.status === 409 ? 'conflict' : 'error'); setMessage(err.message) }
  }
  async function loadHistory() {
    if (!member) return
    setShowHistory(true)
    try { setHistory(await api.memberHistory(member.id)) }
    catch (e) { setState('error'); setMessage((e as Error).message) }
  }
  return <div className="panel editor"><div className="section-title"><div><h2>{member ? '編輯會員' : '新增會員'}</h2>{member && <p>最後更新：{taipei(member.updated_at)}</p>}</div>{member && <button type="button" className="secondary" onClick={loadHistory}>修改歷史</button>}</div>
    {state === 'saving' && <Notice kind="info">儲存中，請稍候…</Notice>}
    {(state === 'error' || state === 'conflict') && <Notice kind="error">{message}{state === 'conflict' && <button className="inline-button" onClick={onConflict}>重新載入清單</button>}</Notice>}
    <form onSubmit={submit}>
      <label>姓名（必填）<input value={draft.name} onChange={e => set('name', e.target.value)} required maxLength={100} /></label>
      <label>重名辨識註記<input value={draft.distinguishing_note} onChange={e => set('distinguishing_note', e.target.value)} maxLength={100} placeholder="僅在需要辨識時填寫" /></label>
      <label>球館原有會員編號<input value={draft.legacy_number} onChange={e => set('legacy_number', e.target.value)} maxLength={50} /></label>
      <div className="form-row"><label>硬實力級數<select value={draft.level} onChange={e => set('level', Number(e.target.value))}>{range(1, 10).map(n => <option key={n}>{n}</option>)}</select></label>
      <label>預設葷素<select value={draft.diet} onChange={e => set('diet', e.target.value as Diet)}><option value="unset">未設定</option><option value="omnivore">葷食</option><option value="vegetarian">素食</option></select></label></div>
      <label className="check"><input type="checkbox" checked={draft.is_active} onChange={e => set('is_active', e.target.checked)} />啟用會員（停用後不會出現在公開名單）</label>
      <button disabled={state === 'saving'}>{state === 'saving' ? '儲存中…' : '儲存會員'}</button>
    </form>
    {showHistory && <div className="history"><h3>重要修改歷史</h3>{history.length === 0 && <p>尚無紀錄。</p>}{history.map(entry => <article key={entry.id}><strong>{entry.action === 'create' ? '建立會員' : '更新會員'}</strong><span>{entry.admin_username}・{taipei(entry.created_at)}</span><ul>{Object.entries(entry.changes).map(([field, values]) => <li key={field}>{fieldText[field] ?? field}：{formatValue(values.before)} → {formatValue(values.after)}</li>)}</ul></article>)}</div>}
  </div>
}

function Notice({ kind, children }: { kind: 'success' | 'error' | 'info'; children: React.ReactNode }) {
  return <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}
function Toast({ kind, children, onClose }: { kind: 'success' | 'error'; children: React.ReactNode; onClose: () => void }) {
  return <div className={`toast ${kind}`} role={kind === 'error' ? 'alert' : 'status'} aria-live={kind === 'error' ? 'assertive' : 'polite'}>
    <span>{children}</span>
    <button type="button" className="toast-close" onClick={onClose} aria-label="關閉提示">×</button>
  </div>
}
const range = (start: number, end: number) => Array.from({ length: end - start + 1 }, (_, i) => start + i)
const taipei = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))
function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '未設定'
  if (typeof value === 'boolean') return value ? '啟用' : '停用'
  if (value === 'unset' || value === 'omnivore' || value === 'vegetarian') return dietText[value]
  return String(value)
}

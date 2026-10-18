import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import { AdminHeader } from './AdminHeader'
import type { AdminAccount, AdminAccountAudit, AdminSession } from './types'

type Operation = { kind: 'create' } | { kind: 'password' } | { kind: 'reset' | 'status'; account: AdminAccount }
type Props = { session: AdminSession; onLogout: () => void; onPasswordChanged: () => void }
const dateTime = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))
const actionText: Record<AdminAccountAudit['action'], string> = {
  create: '新增管理員', change_password: '本人修改密碼', reset_password: '重設密碼', disable: '停用帳號', enable: '啟用帳號', bootstrap: '建立首位管理員',
}
const sourceText: Record<AdminAccountAudit['source'], string> = { web: '管理後台', cli: '維護工具', bootstrap: '首次設定' }

export function AdminManagement({ session, onLogout, onPasswordChanged }: Props) {
  const [accounts, setAccounts] = useState<AdminAccount[]>([])
  const [audits, setAudits] = useState<AdminAccountAudit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [operation, setOperation] = useState<Operation | null>(null)
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditBusy, setAuditBusy] = useState(false)
  const [moreAudits, setMoreAudits] = useState(false)
  const editor = useRef<HTMLElement>(null)
  async function load() {
    setLoading(true); setError('')
    try {
      const [items, history] = await Promise.all([api.adminAccounts(), api.adminAccountAudits()])
      setAccounts(items); setAudits(history); setAuditOffset(history.length); setMoreAudits(history.length === 100)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  useEffect(() => { if (operation) editor.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [operation])
  async function signOut() {
    try { await api.logout(); onLogout() } catch (e) { setError((e as Error).message) }
  }
  async function loadMoreAudits() {
    if (auditBusy) return
    setAuditBusy(true); setError('')
    try {
      const history = await api.adminAccountAudits(auditOffset)
      setAudits(current => [...current, ...history]); setAuditOffset(current => current + history.length); setMoreAudits(history.length === 100)
    } catch (e) { setError((e as Error).message) }
    finally { setAuditBusy(false) }
  }
  const ownAccount = accounts.find(account => account.id === session.admin_id)
  return <>
    <AdminHeader section="admins" username={session.username} displayName={session.display_name} onLogout={signOut} />
    <main className="admin-management">
      {error && <div className="notice error" role="alert">{error}<button className="inline-button" onClick={load}>重新載入</button></div>}
      {notice && <p className="notice success" role="status">{notice}</p>}
      <div className="section-title admin-management-intro"><div><h2>管理員帳號</h2><p>所有啟用中的管理員皆有相同權限。帳號建立後不可變更。</p></div><div className="admin-management-actions">
        <button className="secondary" disabled={loading} onClick={() => { setOperation({ kind: 'password' }); setNotice('') }}>修改我的密碼</button>
        <button disabled={loading} onClick={() => { setOperation({ kind: 'create' }); setNotice('') }}>新增管理員</button>
      </div></div>
      {loading && <p role="status">載入管理員資料中…</p>}
      <div className="admin-management-workspace">
        <section className="panel" aria-labelledby="admin-list-title"><h2 id="admin-list-title">管理員名單</h2>
          <ul className="admin-account-list">{accounts.map(account => <li key={account.id} data-admin-username={account.username}>
            <div className="admin-account-identity"><strong>{account.display_name || account.username}</strong>{account.id === session.admin_id && <span className="admin-self">本人</span>}<span className={`status ${account.is_active ? 'active' : 'inactive'}`}>{account.is_active ? '啟用' : '停用'}</span></div>
            {account.display_name && <p>帳號：{account.username}</p>}
            <p>{account.must_change_password ? '首次登入需更換密碼' : '密碼已設定'}<small>建立：{dateTime(account.created_at)}</small></p>
            {account.id !== session.admin_id ? <div className="admin-account-actions">
              <button className="secondary" onClick={() => { setOperation({ kind: 'reset', account }); setNotice('') }}>重設密碼</button>
              <button className={account.is_active ? 'secondary danger-action' : 'secondary'} onClick={() => { setOperation({ kind: 'status', account }); setNotice('') }}>{account.is_active ? '停用帳號' : '啟用帳號'}</button>
            </div> : <p className="admin-self-help">無法停用自己；更換密碼請使用「修改我的密碼」。</p>}
          </li>)}</ul>
        </section>
        {operation && <section ref={editor} className="panel admin-account-editor" aria-label="管理員操作">
          <AccountOperation key={operation.kind + ('account' in operation ? operation.account.id : '')} operation={operation} session={session} ownVersion={ownAccount?.version ?? session.version} onCancel={() => setOperation(null)} onPasswordChanged={onPasswordChanged} onSaved={async message => { setOperation(null); setNotice(message); await load() }} />
        </section>}
      </div>
      <section className="panel admin-account-history" aria-labelledby="admin-audit-title"><div className="section-title"><h2 id="admin-audit-title">操作紀錄</h2><button className="secondary" disabled={loading} onClick={load}>重新整理</button></div>
        {!loading && !audits.length && <p>尚無操作紀錄。</p>}
        <ol className="admin-audit-list">{audits.map(audit => <li key={audit.id}>
          <div><strong>{actionText[audit.action]}</strong><span>{dateTime(audit.created_at)}</span></div>
          <p>操作者：{audit.actor_display_name ? `${audit.actor_display_name}（${audit.actor_username}）` : audit.actor_username ?? (audit.source === 'cli' ? '維護工具' : audit.source === 'bootstrap' ? '首次設定' : '未記錄')} → 帳號：{audit.target_display_name ? `${audit.target_display_name}（${audit.target_username}）` : audit.target_username}</p>
          <small>來源：{sourceText[audit.source]}</small>
        </li>)}</ol>
        {moreAudits && <button className="secondary" disabled={auditBusy} onClick={loadMoreAudits}>{auditBusy ? '載入中…' : '載入更多紀錄'}</button>}
      </section>
    </main>
  </>
}

function AccountOperation({ operation, session, ownVersion, onCancel, onSaved, onPasswordChanged, cancelLabel = '取消' }: {
  operation: Operation; session: AdminSession; ownVersion: number; onCancel: () => void; onSaved: (message: string) => Promise<void>; onPasswordChanged: () => void; cancelLabel?: string
}) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [target, setTarget] = useState('account' in operation ? operation.account : null)
  const [version, setVersion] = useState(ownVersion)
  const lock = useRef(false)
  const needsNewPassword = operation.kind !== 'status'
  const title = operation.kind === 'create' ? '新增管理員' : operation.kind === 'password' ? '修改我的密碼' : operation.kind === 'reset' ? `重設 ${target?.username} 的密碼` : `${target?.is_active ? '停用' : '啟用'} ${target?.username}`
  async function reloadTarget() {
    setBusy(true); setError('')
    try {
      if (operation.kind === 'password') {
        const current = await api.restoreAdminSession()
        if (current.admin_id !== session.admin_id) throw new Error('登入帳號已變更，請登出後重新登入。')
        setVersion(current.version); setConflict(false)
        setError('已載入最新帳號狀態，請重新輸入本人密碼。')
        return
      }
      const items = await api.adminAccounts()
      const current = items.find(account => account.id === (target?.id ?? session.admin_id))
      if (!current) throw new Error('找不到這個管理員帳號，請重新載入名單。')
      setTarget(target ? current : null); setVersion(current.version); setConflict(false)
      setError('已載入最新帳號狀態，請確認操作並重新輸入本人密碼。')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (lock.current || conflict) return
    if (needsNewPassword && password !== confirmation) { setError('兩次輸入的新密碼不一致。'); return }
    lock.current = true; setBusy(true); setError('')
    try {
      if (operation.kind === 'password') { await api.changeOwnPassword(version, currentPassword, password); onPasswordChanged(); return }
      if (operation.kind === 'create') await api.createAdminAccount(username.trim(), password, currentPassword, displayName)
      else if (operation.kind === 'reset') await api.resetAdminPassword(target!, password, currentPassword)
      else await api.changeAdminStatus(target!, !target!.is_active, currentPassword)
      setPassword(''); setConfirmation(''); setCurrentPassword('')
      await onSaved(operation.kind === 'create' ? '管理員已新增，首次登入時須更換密碼。' : operation.kind === 'reset' ? '密碼已重設，該帳號須重新登入並更換密碼。' : target!.is_active ? '管理員已停用，原登入已失效。' : '管理員已啟用。')
    } catch (e) {
      setError((e as Error).message); setConflict((e as Error & { status?: number }).status === 409)
      setCurrentPassword('')
    } finally { setBusy(false); lock.current = false }
  }
  return <><h2>{title}</h2>
    {operation.kind === 'create' && <p>新帳號將擁有完整管理權限，首次登入時必須更換密碼。</p>}
    {operation.kind === 'reset' && <p>將登出此帳號的所有裝置，並要求下次登入時更換密碼。請另行將臨時密碼安全交給本人。</p>}
    {operation.kind === 'status' && <p>{target?.is_active ? '停用後會立即登出此帳號的所有裝置，無法再次登入。歷史紀錄仍會保留。' : '啟用後，此帳號可使用原有密碼登入。'}</p>}
    {operation.kind === 'password' && <p>密碼更新後，所有裝置都需要重新登入。</p>}
    <form onSubmit={submit}>
      {operation.kind === 'create' && <label>新管理員帳號<input required maxLength={80} autoComplete="off" value={username} disabled={busy} onChange={e => setUsername(e.target.value)} /></label>}
      {operation.kind === 'create' && <label>管理員姓名（選填）<input maxLength={100} autoComplete="off" value={displayName} disabled={busy} onChange={e => setDisplayName(e.target.value)} /></label>}
      {needsNewPassword && <NewPasswordFields password={password} confirmation={confirmation} busy={busy} onPassword={setPassword} onConfirmation={setConfirmation} />}
      <label>本人目前密碼<input type="password" autoComplete="current-password" required maxLength={256} value={currentPassword} disabled={busy} onChange={e => setCurrentPassword(e.target.value)} /></label>
      {error && <div className="notice error" role="alert">{error}{conflict && <p>資料已變更，請先核對最新狀態，再重新確認操作。<button type="button" className="secondary" disabled={busy} onClick={reloadTarget}>核對最新帳號</button></p>}</div>}
      <div className="admin-management-actions"><button type="button" className="secondary" disabled={busy} onClick={onCancel}>{cancelLabel}</button><button disabled={busy || conflict}>{busy ? '處理中…' : operation.kind === 'create' ? '確認新增管理員' : operation.kind === 'password' ? '更新密碼並重新登入' : operation.kind === 'reset' ? '確認重設密碼' : target?.is_active ? '確認停用帳號' : '確認啟用帳號'}</button></div>
    </form>
  </>
}

function NewPasswordFields({ password, confirmation, busy, onPassword, onConfirmation }: { password: string; confirmation: string; busy: boolean; onPassword: (value: string) => void; onConfirmation: (value: string) => void }) {
  return <><label>新密碼<input aria-label="新密碼" aria-describedby="admin-new-password-help" type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} disabled={busy} onChange={e => onPassword(e.target.value)} /><small id="admin-new-password-help">請使用 12–256 個字元。</small></label>
    <label>再次輸入新密碼<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={confirmation} disabled={busy} onChange={e => onConfirmation(e.target.value)} /></label></>
}

export function RequiredPasswordChange({ session, onLogout, onPasswordChanged }: Props) {
  const [error, setError] = useState('')
  async function signOut() { try { await api.logout(); onLogout() } catch (e) { setError((e as Error).message) } }
  return <main className="login-shell required-password-change"><section className="panel">
    <p className="eyebrow">府城球館</p><h1>請先更換密碼</h1><p>目前登入：<strong>{session.display_name ? `${session.display_name}（${session.username}）` : session.username}</strong></p><p>這是新建帳號或重設後的首次登入。完成更換密碼後，才能使用管理功能。</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    <AccountOperation operation={{ kind: 'password' }} session={session} ownVersion={session.version} onCancel={signOut} onSaved={async () => {}} onPasswordChanged={onPasswordChanged} cancelLabel="登出" />
  </section></main>
}

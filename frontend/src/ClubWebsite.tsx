import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import type { AuditEntry } from './types'

type Announcement = { id: string; title: string; body: string; is_pinned: boolean; published_at: string | null; updated_at: string }
type AdminAnnouncement = Announcement & { is_published: boolean; version: number }
type Schedule = { id: string; name: string; competition_date: string; registration_deadline: string; status: 'open' | 'closed' | 'ended' | 'cancelled'; notes: string | null }
const dateTime = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))
const statusText = { open: '報名中', closed: '報名已截止', ended: '已結束', cancelled: '已取消' }

export function SiteNav() {
  const pathname = location.pathname
  return <nav className="site-nav no-print" aria-label="網站導覽">
    <a className="site-brand" href="/">府城球館<span>一起打球，一起進步。</span></a>
    <div>{[['/', '最新消息'], ['/members', '會員分級'], ['/competitions', '比賽報名']].map(([href, label]) => <a key={href} href={href} aria-current={(pathname === href || (href === '/competitions' && pathname.startsWith('/register/'))) ? 'page' : undefined}>{label}</a>)}<a className="nav-admin" href="/admin">管理後台</a></div>
  </nav>
}

export function ClubHome() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [schedule, setSchedule] = useState<Schedule[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([request<Announcement[]>('/api/public/announcements'), request<Schedule[]>('/api/public/schedule')])
      .then(([news, events]) => { if (active) { setAnnouncements(news); setSchedule(events) } })
      .catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [retry])
  const opening = schedule.filter(item => item.status === 'open').sort((a, b) => a.competition_date.localeCompare(b.competition_date))
  const ordered = [...opening, ...schedule.filter(item => item.status !== 'open')]
  return <>
    <header className="club-hero"><div><p className="eyebrow">府城球館・球友資訊站</p><h1>球館大小事，<br />這裡都找得到。</h1><p>看公告、查分級、報名比賽。<br />不用帳號，隨時掌握球館消息。</p><a className="hero-action" href="/competitions">查看比賽與報名 →</a></div><div className="club-hero-note"><span className="court-mark" aria-hidden="true">府城</span><p>來球館，找球友。<br />下一場，一起上桌。</p></div></header>
    <main className="club-home">
      <section className="home-shortcuts" aria-label="常用功能"><a href="/members"><span>01 / 查名單</span><h2>會員分級名單</h2><p>全部級數、姓名搜尋，快速找到自己。</p><strong>查看分級 →</strong></a><a href="/competitions"><span>02 / 參加比賽</span><h2>比賽報名</h2><p>選比賽、找名字、選葷素，完成登記。</p><strong>前往報名 →</strong></a></section>
      {loading && <p role="status">載入球館消息中…</p>}
      {error && <div className="notice error" role="alert">{error}<button onClick={() => setRetry(n => n + 1)}>重新載入</button></div>}
      {!loading && !error && <div className="home-columns"><section aria-labelledby="news-title"><div className="home-section-title"><p className="section-kicker">CLUB NEWS</p><h2 id="news-title">最新公告</h2></div>
        {!announcements.length && <div className="panel"><p>目前沒有新公告。</p><p>比賽時程與會員分級仍可隨時查看。</p></div>}
        {announcements.map(item => <article className="panel news-card" key={item.id}><div className="news-meta">{item.is_pinned && <span className="news-pin">置頂公告</span>}{item.published_at && <time dateTime={item.published_at}>{dateTime(item.published_at)}</time>}</div><h3>{item.title}</h3><p className="news-body">{item.body}</p></article>)}
      </section><section aria-labelledby="schedule-title"><div className="home-section-title"><p className="section-kicker">MATCH CALENDAR</p><h2 id="schedule-title">比賽時程</h2></div>
        {!ordered.length && <div className="panel"><p>目前尚無已公告的比賽。</p><p>新比賽開放後，會顯示在這裡。</p></div>}
        {ordered.map(item => <article className="panel schedule-card" key={item.id}><span className={`schedule-status ${item.status}`}>{statusText[item.status]}</span><h3>{item.name}</h3><p>比賽日期：{item.competition_date}</p><p>報名截止：{dateTime(item.registration_deadline)}</p>{item.notes && <p className="news-body">{item.notes}</p>}{item.status === 'open' && <a className="registration-button" href={`/register/${item.id}`}>我要報名：{item.name}</a>}</article>)}
      </section></div>}
      <aside className="club-help"><h2>不方便用手機？我們幫你。</h2><p>找不到名字、需要取消或更正，請洽球館管理員。也可以請管理員協助報名。</p></aside>
    </main><footer>府城球館｜球友資訊與比賽報名</footer>
  </>
}

export function AnnouncementManager() {
  const [items, setItems] = useState<AdminAnnouncement[]>([])
  const [selected, setSelected] = useState<AdminAnnouncement | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function load() { try { setItems(await request<AdminAnnouncement[]>('/api/admin/announcements')); setError('') } catch (e) { setError((e as Error).message) } }
  useEffect(() => { load() }, [])
  return <><header className="admin-header"><div><p className="eyebrow">球館消息</p><h1>公告管理</h1></div><div className="header-actions"><a href="/admin">會員管理</a><a href="/admin/competitions">比賽管理</a><a href="/">查看首頁</a></div></header><main>
    {error && <div role="alert" className="notice error">{error}<button onClick={load}>重新載入</button></div>}{notice && <p role="status" className="notice success">{notice}</p>}
    <div className="section-title"><p>草稿不會公開；勾選發布後即顯示在首頁。取消發布即可下架。</p><button onClick={() => { setCreating(true); setSelected(null); setNotice('') }}>新增公告</button></div>
    <div className="announcement-workspace"><section className="panel"><h2>公告清單</h2>{!items.length && <p>尚無公告，請新增第一則球館消息。</p>}{items.map(item => <button className="announcement-row" key={item.id} onClick={() => { setSelected(item); setCreating(false); setNotice('') }}><strong>{item.title}</strong><span>{item.is_published ? '已發布' : '未發布'}{item.is_pinned ? '・置頂' : ''}</span></button>)}</section>
    {creating || selected ? <AnnouncementEditor key={selected ? `${selected.id}-${selected.version}` : 'new'} item={selected} onConflict={load} onSaved={item => { setSelected(item); setCreating(false); setNotice('公告已儲存'); load() }} /> : <div className="panel empty">選擇公告進行編輯，或新增一則公告。</div>}</div>
  </main></>
}

function AnnouncementEditor({ item, onSaved, onConflict }: { item: AdminAnnouncement | null; onConflict: () => Promise<void>; onSaved: (item: AdminAnnouncement) => void }) {
  const [title, setTitle] = useState(item?.title ?? '')
  const [body, setBody] = useState(item?.body ?? '')
  const [published, setPublished] = useState(item?.is_published ?? false)
  const [pinned, setPinned] = useState(item?.is_pinned ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [history, setHistory] = useState<AuditEntry[] | null>(null)
  const pending = useRef({ signature: '', key: '' })
  const lock = useRef(false)
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setConflict(false)
    const values = { title, body, is_published: published, is_pinned: pinned, ...(item ? { version: item.version } : {}) }
    const signature = JSON.stringify(values)
    if (signature !== pending.current.signature) pending.current = { signature, key: crypto.randomUUID() }
    try { onSaved(await request<AdminAnnouncement>(item ? `/api/admin/announcements/${item.id}` : '/api/admin/announcements', { method: item ? 'PUT' : 'POST', body: JSON.stringify({ ...values, request_id: pending.current.key }) })) }
    catch (e) { setError((e as Error).message); setConflict((e as Error & { status: number }).status === 409); if ((e as Error & { status: number }).status === 409) await onConflict() }
    finally { setBusy(false); lock.current = false }
  }
  async function loadHistory() { try { setHistory(await request<AuditEntry[]>(`/api/admin/announcements/${item!.id}/history`)) } catch (e) { setError((e as Error).message) } }
  return <section className="panel"><h2>{item ? '編輯公告' : '新增公告'}</h2><form onSubmit={submit}>
    <label>公告標題<input required maxLength={120} value={title} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>
    <label>公告內容<textarea required maxLength={10000} rows={9} value={body} disabled={busy} onChange={e => setBody(e.target.value)} /></label>
    <label className="check"><input type="checkbox" checked={published} disabled={busy} onChange={e => setPublished(e.target.checked)} />發布到首頁</label>
    <label className="check"><input type="checkbox" checked={pinned} disabled={busy} onChange={e => setPinned(e.target.checked)} />置頂公告</label>
    {error && <div role="alert" className="notice error">{error}{conflict && <p>可先複製目前內容，再從左側清單重新選取公告以載入最新版本。</p>}</div>}
    <button disabled={busy}>{busy ? '儲存中…' : '儲存公告'}</button>
  </form>{item && <button className="secondary history-button" onClick={loadHistory}>公告修改歷史</button>}{history && <ul>{history.map(row => <li key={row.id}>{row.admin_username}・{row.action === 'create' ? '新增' : '修改'}・{dateTime(row.created_at)}<p>{Object.keys(row.changes).map(key => ({ title: '標題', body: '內容', is_published: '發布狀態', is_pinned: '置頂狀態' }[key] ?? key)).join('、')}</p></li>)}</ul>}</section>
}

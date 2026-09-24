import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import { logout } from './api'
import { AdminHeader } from './AdminHeader'
import { AnnouncementRichEditor, hydrateAnnouncementImages } from './AnnouncementRichEditor'
import type { AuditEntry } from './types'

type Announcement = { id: string; title: string; body: string; body_format: 'plain' | 'html'; photo_id: string | null; is_pinned: boolean; published_at: string | null; updated_at: string }
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
        {announcements.map(item => <article className="panel news-card" key={item.id}><div className="news-meta">{item.is_pinned && <span className="news-pin">置頂公告</span>}{item.published_at && <time dateTime={item.published_at}>{dateTime(item.published_at)}</time>}</div><h3>{item.title}</h3><AnnouncementBody item={item} />{item.photo_id && <img className="announcement-photo" src={`/api/public/announcement-media/${item.photo_id}`} alt={`${item.title}公告照片`} />}</article>)}
      </section><section aria-labelledby="schedule-title"><div className="home-section-title"><p className="section-kicker">MATCH CALENDAR</p><h2 id="schedule-title">比賽時程</h2></div>
        {!ordered.length && <div className="panel"><p>目前尚無已公告的比賽。</p><p>新比賽開放後，會顯示在這裡。</p></div>}
        {ordered.map(item => <article className="panel schedule-card" key={item.id}><span className={`schedule-status ${item.status}`}>{statusText[item.status]}</span><h3>{item.name}</h3><p>比賽日期：{item.competition_date}</p><p>報名截止：{dateTime(item.registration_deadline)}</p>{item.notes && <p className="news-body">{item.notes}</p>}{item.status === 'open' && <a className="registration-button" href={`/register/${item.id}`}>我要報名：{item.name}</a>}</article>)}
      </section></div>}
      <aside className="club-help"><h2>不方便用手機？我們幫你。</h2><p>找不到名字、需要取消或更正，請洽球館管理員。也可以請管理員協助報名。</p></aside>
    </main><footer>府城球館｜球友資訊與比賽報名</footer>
  </>
}

export function AnnouncementManager({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [items, setItems] = useState<AdminAnnouncement[]>([])
  const [selected, setSelected] = useState<AdminAnnouncement | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function load() { try { setItems(await request<AdminAnnouncement[]>('/api/admin/announcements')); setError('') } catch (e) { setError((e as Error).message) } }
  async function signOut() { try { await logout(); onLogout() } catch (e) { setError((e as Error).message) } }
  useEffect(() => { load() }, [])
  return <><AdminHeader section="announcements" username={username} onLogout={signOut} /><main className="announcement-main">
    {error && <div role="alert" className="notice error">{error}<button onClick={load}>重新載入</button></div>}{notice && <p role="status" className="notice success">{notice}</p>}
    <div className="section-title"><p>草稿不會公開；勾選發布後即顯示在首頁。取消發布即可下架。</p><button onClick={() => { setCreating(true); setSelected(null); setNotice('') }}>新增公告</button></div>
    <div className="announcement-workspace"><section className="panel"><h2>公告清單</h2>{!items.length && <p>尚無公告，請新增第一則球館消息。</p>}{items.map(item => <button className="announcement-row" key={item.id} onClick={() => { setSelected(item); setCreating(false); setNotice('') }}><strong>{item.title}</strong><span>{item.is_published ? '已發布' : '未發布'}{item.is_pinned ? '・置頂' : ''}</span></button>)}</section>
    {creating || selected ? <AnnouncementEditor key={selected ? `${selected.id}-${selected.version}` : 'new'} item={selected} onConflict={load} onSaved={item => { setSelected(item); setCreating(false); setNotice('公告已儲存'); load() }} /> : <div className="panel empty">選擇公告進行編輯，或新增一則公告。</div>}</div>
  </main></>
}

function AnnouncementBody({ item }: { item: Announcement }) {
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => { if (root.current) hydrateAnnouncementImages(root.current, 'public') }, [item.body])
  return item.body_format === 'html'
    ? <div ref={root} className="news-body rich-body" dangerouslySetInnerHTML={{ __html: item.body }} />
    : <p className="news-body">{item.body}</p>
}

function initialMarkup(item: AdminAnnouncement | null): string {
  if (!item) return ''
  if (item.body_format === 'html') return item.body
  return item.body.split('\n').map(line => `<p>${line.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;') || '<br>'}</p>`).join('')
}

function AnnouncementEditor({ item, onSaved, onConflict }: { item: AdminAnnouncement | null; onConflict: () => Promise<void>; onSaved: (item: AdminAnnouncement) => void }) {
  const [title, setTitle] = useState(item?.title ?? '')
  const [body, setBody] = useState(initialMarkup(item))
  const [bodyFormat, setBodyFormat] = useState<'plain' | 'html'>(item?.body_format ?? 'html')
  const [version, setVersion] = useState(item?.version ?? 0)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [removePhoto, setRemovePhoto] = useState(false)
  const [published, setPublished] = useState(item?.is_published ?? false)
  const [pinned, setPinned] = useState(item?.is_pinned ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [history, setHistory] = useState<AuditEntry[] | null>(null)
  const pending = useRef({ signature: '', key: '' })
  const photoPending = useRef({ signature: '', key: '', version: 0 })
  const inlinePending = useRef({ signature: '', key: '', version: 0 })
  const legacyPhotoPicker = useRef<HTMLInputElement>(null)
  const lock = useRef(false)
  async function uploadInline(file: File): Promise<string> {
    if (!item) throw new Error('請先儲存公告草稿')
    const signature = `${item.id}:${version}:${file.name}:${file.size}:${file.lastModified}`
    if (signature !== inlinePending.current.signature) inlinePending.current = { signature, key: crypto.randomUUID(), version }
    const data = new FormData()
    data.set('version', String(inlinePending.current.version))
    data.set('request_id', inlinePending.current.key)
    data.set('photo', file)
    const result = await request<{ announcement: AdminAnnouncement; media_id: string }>(`/api/admin/announcements/${item.id}/images`, { method: 'POST', body: data })
    setVersion(result.announcement.version)
    inlinePending.current.signature = ''
    return result.media_id
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setConflict(false)
    const values = { title, body: bodyFormat === 'plain' ? item?.body ?? body : body, body_format: bodyFormat, is_published: published, is_pinned: pinned, ...(item ? { version } : {}) }
    const signature = JSON.stringify(values)
    if (signature !== pending.current.signature) pending.current = { signature, key: crypto.randomUUID() }
    try {
      let saved = await request<AdminAnnouncement>(item ? `/api/admin/announcements/${item.id}` : '/api/admin/announcements', { method: item ? 'PUT' : 'POST', body: JSON.stringify({ ...values, request_id: pending.current.key }) })
      setVersion(saved.version)
      if (photoFile || removePhoto) {
        const photoSignature = `${saved.id}:${signature}:${photoFile?.name ?? 'remove'}:${photoFile?.size ?? 0}:${photoFile?.lastModified ?? 0}`
        if (photoSignature !== photoPending.current.signature) photoPending.current = { signature: photoSignature, key: crypto.randomUUID(), version: saved.version }
        if (photoFile) {
          const data = new FormData()
          data.set('version', String(photoPending.current.version)); data.set('request_id', photoPending.current.key); data.set('photo', photoFile)
          saved = await request<AdminAnnouncement>(`/api/admin/announcements/${saved.id}/photo`, { method: 'POST', body: data })
        } else {
          saved = await request<AdminAnnouncement>(`/api/admin/announcements/${saved.id}/photo`, { method: 'DELETE', body: JSON.stringify({ version: photoPending.current.version, request_id: photoPending.current.key }) })
        }
      }
      onSaved(saved)
    }
    catch (e) { setError((e as Error).message); setConflict((e as Error & { status: number }).status === 409); if ((e as Error & { status: number }).status === 409) await onConflict() }
    finally { setBusy(false); lock.current = false }
  }
  async function loadHistory() { try { setHistory(await request<AuditEntry[]>(`/api/admin/announcements/${item!.id}/history`)) } catch (e) { setError((e as Error).message) } }
  return <section className="panel"><h2>{item ? '編輯公告' : '新增公告'}</h2><form onSubmit={submit}>
    <label>公告標題<input required maxLength={120} value={title} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>
    <div><span>公告內容</span><AnnouncementRichEditor initial={initialMarkup(item)} disabled={busy} canUpload={!!item} onUpload={uploadInline} onError={setError} onChange={html => { setBody(html); setBodyFormat('html') }} /></div>
    {item?.photo_id && <details className="legacy-photo"><summary>既有文末照片</summary>
      <p>舊公告的文末照片會顯示在內文後方。</p>
      <img className="announcement-photo preview" src={`/api/admin/announcement-media/${item.photo_id}`} alt="既有文末照片" />
      {photoFile && <p role="status">已選擇 {photoFile.name}，儲存後替換文末照片。</p>}
      {removePhoto && <p role="status">儲存後移除文末照片。</p>}
      <div className="legacy-photo-controls"><button className="secondary" type="button" disabled={busy} onClick={() => legacyPhotoPicker.current?.click()}>替換文末照片</button>
        <button className="secondary" type="button" disabled={busy} onClick={() => { setPhotoFile(null); setRemovePhoto(true); if (legacyPhotoPicker.current) legacyPhotoPicker.current.value = '' }}>移除文末照片</button>
        {(photoFile || removePhoto) && <button className="secondary" type="button" disabled={busy} onClick={() => { setPhotoFile(null); setRemovePhoto(false); if (legacyPhotoPicker.current) legacyPhotoPicker.current.value = '' }}>取消文末照片變更</button>}
      </div><input ref={legacyPhotoPicker} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" aria-label="選擇文末照片" disabled={busy} onChange={e => { setPhotoFile(e.target.files?.[0] ?? null); setRemovePhoto(false) }} />
    </details>}
    <label className="check"><input type="checkbox" checked={published} disabled={busy} onChange={e => setPublished(e.target.checked)} />發布到首頁</label>
    <label className="check"><input type="checkbox" checked={pinned} disabled={busy} onChange={e => setPinned(e.target.checked)} />置頂公告</label>
    {error && <div role="alert" className="notice error">{error}{conflict && <p>可先複製目前內容，再從左側清單重新選取公告以載入最新版本。</p>}</div>}
    <button disabled={busy}>{busy ? '儲存中…' : '儲存公告'}</button>
  </form>{item && <button className="secondary history-button" onClick={loadHistory}>公告修改歷史</button>}{history && <ul>{history.map(row => <li key={row.id}>{row.admin_username}・{row.action === 'create' ? '新增' : row.action === 'photo' ? '照片' : '修改'}・{dateTime(row.created_at)}<p>{Object.keys(row.changes).map(key => ({ title: '標題', body: '內容', photo_id: '照片', is_published: '發布狀態', is_pinned: '置頂狀態' }[key] ?? key)).join('、')}</p></li>)}</ul>}</section>
}

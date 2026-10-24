import { appUrl, appPathname } from './paths'
import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import { logout } from './api'
import { AdminHeader } from './AdminHeader'
import { AnnouncementRichEditor, hydrateAnnouncementImages } from './AnnouncementRichEditor'
import type { AuditEntry } from './types'

type Announcement = { id: string; title: string; body: string; body_format: 'plain' | 'html'; photo_id: string | null; is_pinned: boolean; published_at: string | null; updated_at: string }
type AdminAnnouncement = Announcement & { is_published: boolean; version: number; deleted_at: string | null }
type Schedule = { registration_mode: 'individual' | 'doubles'; id: string; name: string; competition_date: string; registration_deadline: string; status: 'open' | 'closed' | 'ended' | 'cancelled'; notes: string | null }
const dateTime = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value))
const statusText = { open: '報名中', closed: '報名已截止', ended: '已結束', cancelled: '已取消' }

export function SiteNav() {
  const pathname = appPathname()
  return <nav className={`site-nav no-print ${pathname.startsWith('/admin') ? 'admin-site-nav' : ''}`} aria-label="網站導覽">
    <a className="site-brand" href={appUrl("/")}>府城球館<span>一起打球，一起進步。</span></a>
    <div>{[['/', '最新消息'], ['/members', '會員分級表'], ['/competitions', '比賽報名']].map(([href, label]) => <a key={href} href={appUrl(href)} aria-current={(pathname === href || (href === '/competitions' && pathname.startsWith('/register/'))) ? 'page' : undefined}>{label}</a>)}<a className="nav-admin" href={appUrl("/admin")}>管理後台</a></div>
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
    <main className="club-home">
      <h1 className="visually-hidden">府城球館最新消息</h1>
      <section className="home-shortcuts" aria-label="常用功能"><a href={appUrl("/members")}><span>01 / 查名單</span><h2>會員分級表</h2><p>全部級數、姓名搜尋，快速找到自己。</p><strong>查看分級 →</strong></a><a href={appUrl("/competitions")}><span>02 / 參加比賽</span><h2>比賽報名</h2><p>選比賽、找名字，依場次個人報名或雙打組隊。</p><strong>前往報名 →</strong></a></section>
      {loading && <p role="status">載入球館消息中…</p>}
      {error && <div className="notice error" role="alert">{error}<button onClick={() => setRetry(n => n + 1)}>重新載入</button></div>}
      {!loading && !error && <div className="home-columns"><section aria-labelledby="news-title"><div className="home-section-title"><p className="section-kicker">CLUB NEWS</p><h2 id="news-title">最新公告</h2></div>
        {!announcements.length && <div className="panel"><p>目前沒有新公告。</p><p>比賽時程與會員分級表仍可隨時查看。</p></div>}
        {announcements.map(item => <article className="panel news-card" key={item.id}><div className="news-meta">{item.is_pinned && <span className="news-pin">置頂公告</span>}{item.published_at && <time dateTime={item.published_at}>{dateTime(item.published_at)}</time>}</div><h3>{item.title}</h3><AnnouncementBody item={item} />{item.photo_id && <img className="announcement-photo" src={appUrl(`/api/public/announcement-media/${item.photo_id}`)} alt={`${item.title}公告照片`} />}</article>)}
      </section><section aria-labelledby="schedule-title"><div className="home-section-title"><p className="section-kicker">MATCH CALENDAR</p><h2 id="schedule-title">比賽時程</h2></div>
        {!ordered.length && <div className="panel"><p>目前尚無已公告的比賽。</p><p>新比賽開放後，會顯示在這裡。</p></div>}
        {ordered.map(item => <article className="panel schedule-card" key={item.id}><span className={`schedule-status ${item.status}`}>{statusText[item.status]}</span><h3>{item.name}</h3><p>比賽日期：{item.competition_date}</p><p>報名截止：{dateTime(item.registration_deadline)}</p>{item.notes && <p className="news-body">{item.notes}</p>}{(item.status === 'open' || (item.registration_mode === 'doubles' && item.status === 'closed')) && <a className="registration-button" href={appUrl(`/register/${item.id}`)}>{item.registration_mode === 'doubles' ? '查看雙打名單' : '我要報名'}：{item.name}</a>}</article>)}
      </section></div>}
      <aside className="club-help"><h2>不方便用手機？我們幫你。</h2><p>找不到名字、需要取消或更正，請洽球館管理員。也可以請管理員協助報名。</p></aside>
    </main><footer>府城球館｜球友資訊與比賽報名</footer>
  </>
}

export function AnnouncementManager({ username, displayName, onLogout }: { username: string; displayName?: string | null; onLogout: () => void }) {
  const [items, setItems] = useState<AdminAnnouncement[]>([])
  const [selected, setSelected] = useState<AdminAnnouncement | null>(null)
  const [mobileEditor, setMobileEditor] = useState(false)
  const [creating, setCreating] = useState(false)
  const [deleted, setDeleted] = useState(false)
  const [locked, setLocked] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const loadSequence = useRef(0)
  async function load(view = deleted) {
    const sequence = ++loadSequence.current
    try {
      const rows = await request<AdminAnnouncement[]>(`/api/admin/announcements?deleted=${view}`)
      if (sequence === loadSequence.current) { setItems(rows); setError('') }
    } catch (e) { if (sequence === loadSequence.current) setError((e as Error).message) }
  }
  async function signOut() { if (!locked) try { await logout(); onLogout() } catch (e) { setError((e as Error).message) } }
  useEffect(() => { void load(deleted) }, [deleted])
  function switchView(view: boolean) {
    if (locked || view === deleted) return
    setDeleted(view); setItems([]); setSelected(null); setCreating(false); setMobileEditor(false); setNotice('')
  }
  function saved(item: AdminAnnouncement, message = '公告已儲存') {
    const view = item.deleted_at !== null
    setSelected(item); setCreating(false); setNotice(message); setLocked(false)
    if (view !== deleted) { setItems([]); setDeleted(view) } else void load(view)
  }
  return <><AdminHeader section="announcements" username={username} displayName={displayName} onLogout={signOut} /><main className="announcement-main">
    {error && <div role="alert" className="notice error">{error}<button disabled={locked} onClick={() => void load()}>重新載入</button></div>}{notice && <p role="status" className="notice success">{notice}</p>}
    <div className="section-title"><p>先儲存公告，再用「公開到首頁」開關公開或下架；刪除的公告可在已刪除清單還原。</p><button disabled={locked} onClick={() => { setCreating(true); setSelected(null); setNotice(''); setMobileEditor(true) }}>新增公告</button></div>
    <div className={`announcement-workspace ${mobileEditor ? 'mobile-editing' : 'mobile-browsing'}`}><section className="panel"><h2>公告清單</h2>
      <div className="competition-view-switch" role="group" aria-label="公告清單範圍"><button type="button" className="secondary" aria-pressed={!deleted} disabled={locked} onClick={() => switchView(false)}>目前公告</button><button type="button" className="secondary" aria-pressed={deleted} disabled={locked} onClick={() => switchView(true)}>已刪除</button></div>
      {(creating || selected) && !mobileEditor && <button className="secondary mobile-pane-back" disabled={locked} onClick={() => setMobileEditor(true)}>繼續查看公告</button>}
      {!items.length && <p>{deleted ? '目前沒有已刪除的公告。' : '尚無公告，請新增第一則球館消息。'}</p>}
      {items.map(item => <button className="announcement-row" key={item.id} aria-pressed={selected?.id === item.id} disabled={locked} onClick={() => { setSelected(item); setCreating(false); setNotice(''); setMobileEditor(true) }}><strong>{item.title}</strong><span>{item.deleted_at ? '已刪除' : item.is_published ? '已發布' : '未發布'}{item.is_pinned ? '・置頂' : ''}</span></button>)}</section>
    <section className="announcement-editor-pane"><button type="button" className="secondary mobile-pane-back" disabled={locked} onClick={() => setMobileEditor(false)}>← 返回公告清單（保留輸入）</button>{creating || selected ? <AnnouncementEditor key={selected ? `${selected.id}-${selected.version}` : 'new'} item={selected} onConflict={() => load()} onLocked={setLocked} onSaved={saved} /> : <div className="panel empty">選擇公告進行編輯，或新增一則公告。</div>}</section></div>
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

function AnnouncementReadOnlyBody({ item }: { item: AdminAnnouncement }) {
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!root.current) return
    root.current.innerHTML = initialMarkup(item)
    hydrateAnnouncementImages(root.current, 'admin')
  }, [item.body, item.body_format])
  // React owns the container; the effect owns its sanitized markup and hydrated images.
  return <div ref={root} className="news-body rich-body" />
}

// Include response-body decoding in the timeout. A missing receipt keeps the original payload for replay.
async function announcementRequest<T>(url: string, options: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 20000)
  try { return await request<T>(url, { ...options, signal: controller.signal }) }
  catch (error) {
    if (controller.signal.aborted) throw new Error('伺服器未及時回應，操作結果尚未確認。')
    throw error
  } finally { clearTimeout(timer) }
}
function uncertain(error: unknown) {
  const status = (error as { status?: number }).status
  return status === undefined || status >= 500
}

function AnnouncementEditor({ item, onSaved, onConflict, onLocked }: { item: AdminAnnouncement | null; onConflict: () => Promise<void>; onLocked: (value: boolean) => void; onSaved: (item: AdminAnnouncement, message?: string) => void }) {
  const [title, setTitle] = useState(item?.title ?? '')
  const [body, setBody] = useState(initialMarkup(item))
  const [bodyFormat, setBodyFormat] = useState<'plain' | 'html'>(item?.body_format ?? 'html')
  const [version, setVersion] = useState(item?.version ?? 0)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [removePhoto, setRemovePhoto] = useState(false)
  const published = item?.is_published ?? false
  const pinned = item?.is_pinned ?? false
  const [busy, setBusy] = useState(false)
  const [unknown, setUnknown] = useState<'save' | 'status' | 'inline' | null>(null)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [history, setHistory] = useState<AuditEntry[] | null>(null)
  const [deletion, setDeletion] = useState<{ restore: boolean; version: number; key: string } | null>(null)
  const [deletionUnknown, setDeletionUnknown] = useState(false)
  const pending = useRef<{ kind: 'save' | 'status'; message?: string; url: string; method: string; body: string; expectedVersion: number; published: boolean; pinned: boolean; saved?: AdminAnnouncement; photo: File | null; removePhoto: boolean; photoKey: string } | null>(null)
  const inlinePending = useRef<{ key: string; version: number; file: File } | null>(null)
  const legacyPhotoPicker = useRef<HTMLInputElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const safeAction = useRef<HTMLButtonElement>(null)
  const lock = useRef(false)
  const deleted = !!item?.deleted_at
  const disabled = busy || unknown !== null || deletion !== null
  const unsavedContent = !item || title !== item.title || body !== initialMarkup(item) || photoFile !== null || removePhoto
  const statusDisabled = disabled || unsavedContent || conflict
  useEffect(() => { onLocked(disabled); return () => onLocked(false) }, [disabled, onLocked])
  useEffect(() => {
    if (deletion && dialog.current && !dialog.current.open) { dialog.current.showModal(); safeAction.current?.focus() }
    if (!deletion && dialog.current?.open) dialog.current.close()
  }, [deletion])
  async function failed(error: unknown, kind: 'save' | 'status' | 'inline') {
    setError((error as Error).message)
    setConflict((error as { status?: number }).status === 409)
    if (uncertain(error)) setUnknown(kind)
    else {
      setUnknown(null)
      if (kind !== 'inline') pending.current = null
      else inlinePending.current = null
      if ((error as { status?: number }).status === 409) await onConflict()
    }
  }
  async function uploadInline(file: File): Promise<string> {
    if (!item || deleted || lock.current || (unknown && unknown !== 'inline')) throw new Error('目前無法插入圖片')
    lock.current = true; setBusy(true); setError(''); setConflict(false)
    if (!inlinePending.current) inlinePending.current = { key: crypto.randomUUID(), version, file }
    const operation = inlinePending.current
    const data = new FormData()
    data.set('version', String(operation.version)); data.set('request_id', operation.key); data.set('photo', operation.file)
    try {
      const result = await announcementRequest<{ announcement: AdminAnnouncement; media_id: string }>(`/api/admin/announcements/${item.id}/images`, { method: 'POST', body: data })
      if (result.announcement.version !== operation.version + 1 || result.announcement.deleted_at !== null) {
        throw Object.assign(new Error('圖片操作已完成，但公告後續又被變更，請重新核對；目前輸入已保留。'), { status: 409 })
      }
      setVersion(result.announcement.version); setUnknown(null); inlinePending.current = null
      return result.media_id
    } catch (e) { await failed(e, 'inline'); throw e }
    finally { setBusy(false); lock.current = false }
  }
  async function save(status?: { published: boolean; pinned: boolean; message: string }) {
    const kind = status || unknown === 'status' ? 'status' : 'save'
    if (lock.current || deleted || deletion || (unknown && unknown !== kind)) return
    if (!pending.current && kind === 'status' && (!item || unsavedContent || conflict)) return
    lock.current = true; setBusy(true); setError(''); setConflict(false)
    if (!pending.current) {
      // Status changes only replay the saved content; they never submit the editor's draft.
      const values = { title: status ? item!.title : title, body: status ? item!.body : bodyFormat === 'plain' ? item?.body ?? body : body, body_format: status ? item!.body_format : bodyFormat, is_published: status?.published ?? published, is_pinned: status?.pinned ?? pinned, ...(item ? { version } : {}), request_id: crypto.randomUUID() }
      pending.current = { kind, message: status?.message, url: item ? `/api/admin/announcements/${item.id}` : '/api/admin/announcements', method: item ? 'PUT' : 'POST', body: JSON.stringify(values), expectedVersion: item ? version + 1 : 1, published: values.is_published, pinned: values.is_pinned, photo: status ? null : photoFile, removePhoto: status ? false : removePhoto, photoKey: crypto.randomUUID() }
    }
    const operation = pending.current
    try {
      if (!operation.saved) {
        const result = await announcementRequest<AdminAnnouncement>(operation.url, { method: operation.method, body: operation.body })
        if (result.version !== operation.expectedVersion || result.deleted_at !== null || result.is_published !== operation.published || result.is_pinned !== operation.pinned) {
          throw Object.assign(new Error('儲存操作已完成，但公告後續又被變更，請重新核對；目前輸入已保留。'), { status: 409 })
        }
        operation.saved = result
      }
      let saved = operation.saved
      if (operation.photo || operation.removePhoto) {
        if (operation.photo) {
          const data = new FormData()
          data.set('version', String(saved.version)); data.set('request_id', operation.photoKey); data.set('photo', operation.photo)
          saved = await announcementRequest<AdminAnnouncement>(`/api/admin/announcements/${saved.id}/photo`, { method: 'POST', body: data })
        } else saved = await announcementRequest<AdminAnnouncement>(`/api/admin/announcements/${saved.id}/photo`, { method: 'DELETE', body: JSON.stringify({ version: saved.version, request_id: operation.photoKey }) })
        if (saved.version !== operation.saved.version + 1 || saved.deleted_at !== null) {
          throw Object.assign(new Error('照片操作已完成，但公告後續又被變更，請重新核對；目前輸入已保留。'), { status: 409 })
        }
      }
      pending.current = null; setUnknown(null); onSaved(saved, operation.message)
    } catch (e) { if (operation.saved) setVersion(operation.saved.version); await failed(e, operation.kind) }
    finally { setBusy(false); lock.current = false }
  }
  function submit(event: React.FormEvent) { event.preventDefault(); void save() }
  async function changeDeletion() {
    if (!item || !deletion || lock.current) return
    lock.current = true; setBusy(true); setError(''); setConflict(false)
    try {
      const result = await announcementRequest<AdminAnnouncement>(`/api/admin/announcements/${item.id}/${deletion.restore ? 'restore' : 'delete'}`, {
        method: 'POST', body: JSON.stringify({ version: deletion.version, request_id: deletion.key, confirmed: true }),
      })
      setDeletionUnknown(false); setDeletion(null)
      if ((result.deleted_at === null) !== deletion.restore || result.version !== deletion.version + 1 || result.is_published) {
        // A receipt replay can observe a later administrator's opposite operation.
        // Keep this editor's input until the administrator explicitly selects the current row.
        setConflict(true); setError('原操作已完成，但公告狀態後續又被變更，請從清單重新選取並核對。'); await onConflict()
      } else onSaved(result, deletion.restore ? '公告已還原，尚未發布到首頁' : '公告已刪除，可在已刪除清單還原')
    } catch (e) {
      setError((e as Error).message)
      if (uncertain(e)) setDeletionUnknown(true)
      else { setDeletion(null); setDeletionUnknown(false); setConflict((e as { status?: number }).status === 409); await onConflict() }
    } finally { setBusy(false); lock.current = false }
  }
  async function loadHistory() { try { setHistory(await request<AuditEntry[]>(`/api/admin/announcements/${item!.id}/history`)) } catch (e) { setError((e as Error).message) } }
  const errors = error && <div role="alert" className="notice error">{error}{conflict && <p>目前輸入已保留。可先複製內容，再從公告清單重新選取以載入最新版本。</p>}{unknown && <p>結果尚未確認，已暫停其他操作。請原樣重試以核對結果。</p>}</div>
  return <section className="panel"><h2>{deleted ? '已刪除公告' : item ? '編輯公告' : '新增公告'}</h2>
    {deleted ? <><p className="notice info">已於 {dateTime(item!.deleted_at!)} 刪除。內容、圖片與操作紀錄保留；還原後需另外發布。</p><label>公告標題<input value={title} readOnly /></label><div><span>公告內容（唯讀）</span><AnnouncementReadOnlyBody item={item!} /></div></> : <form onSubmit={submit}>
    <label>公告標題<input required maxLength={120} value={title} disabled={disabled} onChange={e => setTitle(e.target.value)} /></label>
    <div><span>公告內容</span><AnnouncementRichEditor initial={initialMarkup(item)} disabled={disabled} canUpload={!!item} onUpload={uploadInline} onError={setError} onChange={html => { setBody(html); setBodyFormat('html') }} /></div>
    {item?.photo_id && <details className="legacy-photo"><summary>既有文末照片</summary>
      <p>舊公告的文末照片會顯示在內文後方。</p><img className="announcement-photo preview" src={appUrl(`/api/admin/announcement-media/${item.photo_id}`)} alt="既有文末照片" />
      {photoFile && <p role="status">已選擇 {photoFile.name}，儲存後替換文末照片。</p>}{removePhoto && <p role="status">儲存後移除文末照片。</p>}
      <div className="legacy-photo-controls"><button className="secondary" type="button" disabled={disabled} onClick={() => legacyPhotoPicker.current?.click()}>替換文末照片</button><button className="secondary" type="button" disabled={disabled} onClick={() => { setPhotoFile(null); setRemovePhoto(true); if (legacyPhotoPicker.current) legacyPhotoPicker.current.value = '' }}>移除文末照片</button>{(photoFile || removePhoto) && <button className="secondary" type="button" disabled={disabled} onClick={() => { setPhotoFile(null); setRemovePhoto(false); if (legacyPhotoPicker.current) legacyPhotoPicker.current.value = '' }}>取消文末照片變更</button>}</div>
      <input ref={legacyPhotoPicker} className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" aria-label="選擇文末照片" disabled={disabled} onChange={e => { setPhotoFile(e.target.files?.[0] ?? null); setRemovePhoto(false) }} />
    </details>}
    {!deletion && errors}
    {published && <p className="notice info announcement-live-hint">這則公告已公開到首頁；儲存內容會立即更新首頁。</p>}
    <div className="announcement-editor-actions">
      <div className="announcement-save-actions"><button type="submit" disabled={busy || (unknown !== null && unknown !== 'save') || deletion !== null}>{busy && pending.current?.kind === 'save' ? '儲存中…' : unknown === 'save' ? '原樣重試儲存' : '儲存公告'}</button>{item && <button type="button" className="secondary history-button" disabled={disabled} onClick={loadHistory}>公告修改歷史</button>}</div>
      <div className="announcement-visibility" role="group" aria-label="公告公開與置頂狀態">
        <div className="announcement-switch-row"><button className="announcement-switch" type="button" role="switch" aria-label="公開到首頁" aria-checked={published} aria-describedby={unsavedContent ? 'announcement-status-hint' : undefined} disabled={statusDisabled} onClick={() => void save({ published: !published, pinned, message: published ? '公告已從首頁下架' : '公告已公開到首頁' })}><span className="announcement-switch-track" aria-hidden="true"><span /></span><span>公開到首頁</span></button><span className="announcement-switch-state">{published ? '已公開' : '未公開'}</span></div>
        <div className="announcement-switch-row"><button className="announcement-switch" type="button" role="switch" aria-label="置頂公告" aria-checked={pinned} aria-describedby={unsavedContent ? 'announcement-status-hint' : undefined} disabled={statusDisabled} onClick={() => void save({ published, pinned: !pinned, message: pinned ? '公告已取消置頂' : '公告已置頂' })}><span className="announcement-switch-track" aria-hidden="true"><span /></span><span>置頂公告</span></button><span className="announcement-switch-state">{pinned ? '已置頂' : '未置頂'}</span></div>
        {unsavedContent && <p id="announcement-status-hint" className="editor-hint">先儲存內容，再變更公開或置頂狀態</p>}
        {!unsavedContent && <p className="editor-hint">{busy && pending.current?.kind === 'status' ? '正在儲存狀態…' : '開關會立即儲存狀態。'}{!published && pinned ? '公開後才會在首頁置頂。' : ''}</p>}
        {unknown === 'status' && <button type="button" className="secondary" disabled={busy} onClick={() => void save()}>原樣重試狀態變更</button>}
      </div>
    </div>
  </form>}
    {deleted && item?.photo_id && <img className="announcement-photo preview" src={appUrl(`/api/admin/announcement-media/${item.photo_id}`)} alt="既有文末照片" />}
    {deleted && !deletion && errors}
    {item && <>{deleted && <button type="button" className="secondary history-button" disabled={disabled} onClick={loadHistory}>公告修改歷史</button>}<div className="announcement-lifecycle"><p>{deleted ? '還原後會回到目前公告，維持未發布。' : '刪除後會從首頁移除，內容、圖片與操作紀錄仍可還原。'}</p><button type="button" className={deleted ? 'secondary' : 'danger secondary'} disabled={disabled} onClick={() => { setError(''); setDeletionUnknown(false); setDeletion({ restore: deleted, version, key: crypto.randomUUID() }) }}>{deleted ? '還原公告' : '刪除公告'}</button></div></>}
    {history && <ul>{history.map(row => <li key={row.id}>{row.admin_username}・{({ create: '新增', update: '修改', photo: '照片', inline_photo: '內文圖片', delete: '刪除', restore: '還原' }[row.action] ?? row.action)}・{dateTime(row.created_at)}<p>{Object.keys(row.changes).map(key => ({ title: '標題', body: '內容', photo_id: '照片', inline_media_id: '內文圖片', is_published: '發布狀態', is_pinned: '置頂狀態', deleted_at: '刪除狀態' }[key] ?? key)).join('、')}</p></li>)}</ul>}
    <dialog ref={dialog} className="competition-confirm-dialog" aria-labelledby="announcement-confirm-title" onCancel={event => { event.preventDefault(); if (!busy && !deletionUnknown) setDeletion(null) }}>
      <h2 id="announcement-confirm-title">{deletion?.restore ? '確認還原公告？' : '確認刪除公告？'}</h2><p className="competition-confirm-name">{item?.title}</p><p>{deletion?.restore ? '內容、圖片與操作紀錄會保留。還原後維持未發布，確認內容後可再發布到首頁。' : '公告將從首頁移除，並移至已刪除清單，可隨時還原。只保留已儲存的版本，尚未儲存的輸入不會保存。'}</p>
      {errors}{deletionUnknown && <p>操作結果尚未確認。請用原請求重試，核對完成前無法取消或進行其他操作。</p>}
      <div className="competition-confirm-buttons"><button ref={safeAction} type="button" className="secondary" disabled={busy || deletionUnknown} onClick={() => setDeletion(null)}>{deletion?.restore ? '維持刪除' : '保留公告'}</button><button type="button" className={deletion?.restore ? '' : 'danger'} disabled={busy} onClick={() => void changeDeletion()}>{busy ? '處理中…' : deletionUnknown ? '原樣重試核對結果' : deletion?.restore ? '確認還原' : '確認刪除'}</button></div>
    </dialog>
  </section>
}

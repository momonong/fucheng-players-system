import { useEffect, useRef, useState } from 'react'
import { AdminHeader } from './AdminHeader'
import { request } from './api'

type Status = 'PASS' | 'WARN' | 'FAIL' | 'NOT_TESTED'
type Check = { id: string; status: Status; reason: string; evidence: string; next_action: string }
type Recommendation = { candidate: string; status: Status; reason: string; next_action: string }
type HostReport = {
  checked_at: string
  host: { name: string; windows: string; build: string }
  summary: Record<Status, number>
  checks: Check[]
  recommendations: Recommendation[]
}
type State = { version: number; uploaded_at: string | null; report: HostReport | null; markdown: string | null }
const MAX_REPORT_BYTES = 256 * 1024

function dateTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '時間無法辨識' : new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', dateStyle: 'medium', timeStyle: 'short',
  }).format(date)
}

export function DeploymentReportPage({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [state, setState] = useState<State | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  async function load() {
    try { setState(await request<State>('/api/admin/deployment-report')); setError('') }
    catch (e) { setError((e as Error).message) }
  }
  useEffect(() => { void load() }, [])
  async function upload() {
    if (!file || !state) return
    if (file.size > MAX_REPORT_BYTES) { setError('JSON 報告超過 256 KiB；原報告未變更。'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const saved = await request<State>(`/api/admin/deployment-report?version=${state.version}`, { method: 'POST', body: file })
      setState(saved); setFile(null); if (fileInput.current) fileInput.current.value = ''
      setNotice('報告已儲存，且已納入資料庫備份。')
    } catch (e) {
      setError((e as Error).message)
      if ((e as Error & { status?: number }).status === 409) {
        try { setState(await request<State>('/api/admin/deployment-report')) } catch { /* keep selected file */ }
      }
    } finally { setBusy(false) }
  }
  async function copyMarkdown() {
    if (!state?.markdown) return
    try { await navigator.clipboard.writeText(state.markdown); setNotice('已複製 Markdown。'); setError('') }
    catch { setError('無法複製；請改用下載 Markdown。') }
  }
  const report = state?.report
  const checkedAt = report ? Date.parse(report.checked_at) : NaN
  const age = Date.now() - checkedAt
  const timeWarning = report && (!Number.isFinite(checkedAt) || age < -5 * 60_000
    ? '主機檢查時間在未來或無法辨識，請核對主機時鐘。'
    : age > 7 * 24 * 60 * 60_000 ? '這份報告已超過 7 天；部署前請在目標主機重新執行。' : '')
  return <>
    <AdminHeader section="status" username={username} onLogout={onLogout} />
    <main className="deployment-report-page">
      <p className="eyebrow">管理後台 → 系統狀態</p><h2>部署檢查報告</h2>
      <p>在目標 Windows 主機的 Git Bash 執行唯讀健檢，再上傳產生的 <code>report.json</code>。伺服器只保存最新一份，不會執行上傳檔中的指令，也不會獨立驗證報告宣稱的主機身份。</p>
      <section className="panel deployment-upload" aria-label="上傳部署檢查報告">
        <h3>上傳 JSON 報告</h3>
        <p>只接受本專案主機健檢產生的 JSON，大小上限 256 KiB；上傳需管理員權限。</p>
        <input ref={fileInput} type="file" accept=".json,application/json" aria-label="選擇部署檢查 JSON" disabled={busy} onChange={event => setFile(event.target.files?.[0] ?? null)} />
        <button type="button" disabled={!file || !state || busy} onClick={upload}>{busy ? '上傳中…' : '上傳並取代最新報告'}</button>
        {file && <p>已選：{file.name}</p>}
      </section>
      {error && <p role="alert" className="notice error">{error}</p>}
      {notice && <p role="status" className="notice success">{notice}</p>}
      {!state && !error && <p role="status">載入中…</p>}
      {state && !report && <section className="panel"><p>尚無部署檢查報告。</p></section>}
      {report && state && <>
        <section className="panel deployment-summary">
          <h3>最新報告 <small>版本 {state.version}</small></h3>
          <p>報告宣稱的主機：<strong>{report.host.name}</strong>・{report.host.windows} build {report.host.build}</p>
          <p>主機檢查時間：{dateTime(report.checked_at)}；上傳時間：{state.uploaded_at ? dateTime(state.uploaded_at) : '未知'}</p>
          {timeWarning && <p role="alert" className="notice error">{timeWarning}</p>}
          <p className="deployment-counts">{(['PASS', 'WARN', 'FAIL', 'NOT_TESTED'] as const).map(status => <span key={status} className={`report-${status.toLowerCase()}`}>{status} {report.summary[status]}</span>)}</p>
          <div className="deployment-actions"><button type="button" onClick={copyMarkdown}>複製 Markdown</button><a href="/api/admin/deployment-report/json" download>下載 JSON</a><a href="/api/admin/deployment-report/markdown" download>下載 Markdown</a></div>
        </section>
        <section className="panel"><h3>入口建議</h3><ul className="deployment-recommendations">{report.recommendations.map(item => <li key={item.candidate}><strong>{item.candidate}・{item.status}</strong><p>{item.reason}</p><p>下一步：{item.next_action}</p></li>)}</ul></section>
        <section className="panel"><h3>逐項檢查</h3><div className="deployment-checks">{report.checks.map(item => <article key={item.id}><h4>{item.id} <span className={`report-${item.status.toLowerCase()}`}>{item.status}</span></h4><p>{item.reason}</p><p>證據：{item.evidence}</p><p>下一步：{item.next_action}</p></article>)}</div></section>
      </>}
    </main>
  </>
}

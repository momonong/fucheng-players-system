import { appUrl } from './paths'
import { useEffect, useRef, useState } from 'react'
import { AdminHeader } from './AdminHeader'
import { request } from './api'

type Status = 'PASS' | 'WARN' | 'FAIL' | 'NOT_TESTED'
type Check = { id: string; status: Status; reason: string; evidence: string; next_action: string }
type Recommendation = { candidate: string; status: Status; reason: string; next_action: string }
type HostReport = {
  checked_at: string
  schema_version: 1 | 2
  report_type?: "container_runtime"
  host?: { name: string; windows: string; build: string }
  runtime?: { name: string; system: string; python: string }
  summary: Record<Status, number>
  checks: Check[]
  recommendations: Recommendation[]
}
type Run = { request_id: string; send_state: 'not_configured' | 'unknown' | 'rejected' | 'received'; detail: string; device_id: string | null; receipt: { report_id: string; device_id: string; digest: string; received_at: string } | null }
type State = { version: number; uploaded_at: string | null; report: HostReport | null; markdown: string | null; run: Run | null }
type Payload = { version: number; request_id: string; probe_network: boolean }
type Pending = { kind: 'run'; payload: Payload; phase: 'unknown' | 'refresh' | 'conflict' } | { kind: 'send'; requestId: string; phase: 'unknown' | 'refresh' | 'conflict' }
async function diagnosticRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 60000)
  try { return await request<T>(url, { ...options, signal: controller.signal }) }
  finally { clearTimeout(timer) }
}
const MAX_REPORT_BYTES = 256 * 1024

function dateTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '時間無法辨識' : new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', dateStyle: 'medium', timeStyle: 'short',
  }).format(date)
}

export function DeploymentReportPage({ username, displayName, onLogout }: { username: string; displayName?: string | null; onLogout: () => void }) {
  const pendingKey = `fucheng-deployment-diagnostic:${appUrl('/admin')}:${username}`
  const [pending, setPending] = useState<Pending | null>(() => {
    try { return JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null') as Pending | null } catch { return null }
  })
  const [probeNetwork, setProbeNetwork] = useState(false)
  const [state, setState] = useState<State | null>(null)
  function keepPending(value: Pending | null) {
    setPending(value)
    if (value) sessionStorage.setItem(pendingKey, JSON.stringify(value))
    else sessionStorage.removeItem(pendingKey)
  }
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
  async function readBack(operation: Pending) {
    const key = operation.kind === 'run' ? operation.payload.request_id : operation.requestId
    const saved = await diagnosticRequest<State>(`/api/admin/deployment-report/runs/${key}`)
    setState(saved); keepPending(null); setError(''); setNotice('原報告已讀回並保存。')
  }
  async function execute(operation: Pending) {
    const key = operation.kind === 'run' ? operation.payload.request_id : operation.requestId
    keepPending(operation)
    let saved: State
    try {
      saved = await diagnosticRequest<State>(operation.kind === 'run' ? '/api/admin/deployment-report/run' : `/api/admin/deployment-report/runs/${key}/send`, {
        method: 'POST', ...(operation.kind === 'run' ? { body: JSON.stringify(operation.payload) } : {}),
      })
    } catch (e) {
      const status = (e as Error & { status?: number }).status
      if (status === 507 && operation.kind === 'run') keepPending(null)
      else if (status === 409) keepPending({ ...operation, phase: 'conflict' })
      throw e
    }
    setState(saved)
    const refresh = { ...operation, phase: 'refresh' as const }
    keepPending(refresh)
    await readBack(refresh)
  }
  async function startRun() {
    if (!state || pending || busy) return
    const operation: Pending = { kind: 'run', phase: 'unknown', payload: { version: state.version, request_id: crypto.randomUUID(), probe_network: probeNetwork } }
    setBusy(true); setError(''); setNotice('')
    try { await execute(operation) }
    catch (e) {
      const lead = (e as Error & { status?: number }).status === 507 ? '本次檢查未保存。' : '檢查結果尚未確認，請讀回原執行結果。'
      setError(`${lead}${(e as Error).message}`)
    }
    finally { setBusy(false) }
  }
  async function recover() {
    if (!pending || busy) return
    setBusy(true); setError('')
    try {
      try { await readBack(pending) }
      catch (e) {
        if ((e as Error & { status?: number }).status === 404 && pending.phase === 'unknown' && pending.kind === 'run') await execute(pending)
        else if ((e as Error & { status?: number }).status === 404 && pending.phase === 'conflict') {
          setState(await diagnosticRequest<State>('/api/admin/deployment-report'))
          keepPending(null); setNotice('已核對最新報告；原請求未保存，請確認目前版本後再執行。')
        } else throw e
      }
    } catch (e) {
      const lead = pending.kind === 'run' && (e as Error & { status?: number }).status === 507 ? '本次檢查未保存。' : '原請求仍保留，請稍後讀回。'
      setError(`${lead}${(e as Error).message}`)
    }
    finally { setBusy(false) }
  }
  async function resend() {
    if (!state?.run || pending || busy) return
    const operation: Pending = { kind: 'send', requestId: state.run.request_id, phase: 'unknown' }
    setBusy(true); setError(''); setNotice('')
    try { await execute(operation) }
    catch (e) { setError(`回傳結果尚未確認，原報告 ID 仍保留。${(e as Error).message}`) }
    finally { setBusy(false) }
  }
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
  // Bind run downloads to exactly the report currently displayed, even when a
  // different administrator has replaced the singleton latest report meanwhile.
  const jsonDownload = state?.run && report
    ? `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(report, null, 2) + '\n')}`
    : appUrl('/api/admin/deployment-report/json')
  const markdownDownload = state?.run && state.markdown
    ? `data:text/markdown;charset=utf-8,${encodeURIComponent(state.markdown)}`
    : appUrl('/api/admin/deployment-report/markdown')
  const checkedAt = report ? Date.parse(report.checked_at) : NaN
  const age = Date.now() - checkedAt
  const timeWarning = report && (!Number.isFinite(checkedAt) || age < -5 * 60_000
    ? '主機檢查時間在未來或無法辨識，請核對主機時鐘。'
    : age > 7 * 24 * 60 * 60_000 ? '這份報告已超過 7 天；部署前請在目標主機重新執行。' : '')
  return <>
    <AdminHeader section="status" username={username} displayName={displayName} onLogout={onLogout} />
    <main className="deployment-report-page">
      <p className="eyebrow">管理後台 → 系統狀態</p><h2>部署檢查報告</h2>
      <p>網站啟動後即可檢查目前 app／Linux 容器，保存報告並依部署設定回傳。Windows 主機、Docker daemon、真實外部入口及完整備份還原仍需現場核對。</p>
      <section className="panel deployment-diagnostic" aria-label="立即執行部署檢查">
        <h3>檢查目前網站</h3>
        <p>不需下載健檢工具。檢查結果保存在資料庫；回傳憑證未配置或網路失敗時仍可查看與下載。</p>
        <label className="diagnostic-network"><input type="checkbox" checked={probeNetwork} disabled={busy || !!pending} onChange={event => setProbeNetwork(event.target.checked)} />一併檢查固定官方網路端點（Cloudflare TCP 7844／HTTPS、Docker Registry）</label>
        <div className="deployment-actions"><button type="button" disabled={!state || busy || !!pending} onClick={startRun}>{busy ? '處理中…' : '立即檢查並回傳'}</button>
          {pending && <button type="button" disabled={busy} onClick={recover}>讀回原執行結果</button>}
        </div>
        {pending && <p role="status">原請求已保留；先讀回結果，避免重複執行。{pending.phase === 'refresh' && '伺服器已回覆，只會重新讀取報告。'}</p>}
        {state?.run && <div className="diagnostic-delivery" data-run-id={state.run.request_id}>
          <p><strong>本機已保存</strong>・回傳狀態：{({ not_configured: '未配置', unknown: '結果未確認', rejected: '接收站拒收', received: '已收到收據' })[state.run.send_state]}</p>
          <p>{state.run.detail}</p><p>報告 ID：<code>{state.run.request_id}</code></p>
          {state.run.receipt && <p>接收時間：{dateTime(state.run.receipt.received_at)}；回傳成功不表示檢查全部通過。</p>}
          {state.run.send_state !== 'received' && <button type="button" disabled={busy || !!pending} onClick={resend}>重送原報告</button>}
        </div>}
      </section>
      <details className="panel deployment-manual"><summary>額外 Windows 主機檢查／手動上傳</summary>
      <section className="deployment-upload" aria-label="上傳部署檢查報告">
        <h3>上傳 JSON 報告</h3>
        <p>只接受本專案主機健檢產生的 JSON，大小上限 256 KiB；上傳需管理員權限。</p>
        <input ref={fileInput} type="file" accept=".json,application/json" aria-label="選擇部署檢查 JSON" disabled={busy || !!pending} onChange={event => setFile(event.target.files?.[0] ?? null)} />
        <button type="button" disabled={!file || !state || busy || !!pending} onClick={upload}>{busy ? '上傳中…' : '上傳並取代最新報告'}</button>
        {file && <p>已選：{file.name}</p>}
      </section>
      </details>
      {error && <p role="alert" className="notice error">{error}</p>}
      {notice && <p role="status" className="notice success">{notice}</p>}
      {!state && !error && <p role="status">載入中…</p>}
      {state && !report && <section className="panel"><p>尚無部署檢查報告。</p></section>}
      {report && state && <>
        <section className="panel deployment-summary">
          <h3>最新報告 <small>版本 {state.version}</small></h3>
          {report.runtime ? <p>來源：<strong>{report.runtime.name}</strong>・{report.runtime.system}・Python {report.runtime.python}</p> : report.host && <p>報告宣稱的主機：<strong>{report.host.name}</strong>・{report.host.windows} build {report.host.build}</p>}
          <p>檢查時間：{dateTime(report.checked_at)}；保存時間：{state.uploaded_at ? dateTime(state.uploaded_at) : '未知'}</p>
          {timeWarning && <p role="alert" className="notice error">{timeWarning}</p>}
          <p className="deployment-counts">{(['PASS', 'WARN', 'FAIL', 'NOT_TESTED'] as const).map(status => <span key={status} className={`report-${status.toLowerCase()}`}>{status} {report.summary[status]}</span>)}</p>
          <div className="deployment-actions"><button type="button" onClick={copyMarkdown}>複製 Markdown</button><a href={jsonDownload} download="deployment-report.json">下載 JSON</a><a href={markdownDownload} download="deployment-report.md">下載 Markdown</a></div>
        </section>
        <section className="panel"><h3>入口建議</h3><ul className="deployment-recommendations">{report.recommendations.map(item => <li key={item.candidate}><strong>{item.candidate}・{item.status}</strong><p>{item.reason}</p><p>下一步：{item.next_action}</p></li>)}</ul></section>
        <section className="panel"><h3>逐項檢查</h3><div className="deployment-checks">{report.checks.map(item => <article key={item.id}><h4>{item.id} <span className={`report-${item.status.toLowerCase()}`}>{item.status}</span></h4><p>{item.reason}</p><p>證據：{item.evidence}</p><p>下一步：{item.next_action}</p></article>)}</div></section>
      </>}
    </main>
  </>
}

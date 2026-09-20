import { useEffect, useRef, useState } from 'react'
import { arrangementVersion } from './api'
import { LevelCardBoard, arrangementChanges, changeText } from './LevelCardBoard'
import type { Competition, ArrangementVersion } from './types'
import type { ArrangementController } from './useArrangementWorkspace'

const time = (value: string) => new Date(value).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })
export function CompetitionLevels({ competition, controller, username }: {
  competition: Competition; controller: ArrangementController; username: string
}) {
  const id = competition.id
  const workspace = controller.workspaces[id]
  const state = workspace?.state
  const readonly = state ? !state.editable : !!competition.deleted_at || !['open', 'closed'].includes(competition.status)
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const searchInput = useRef<HTMLInputElement>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null)
  const [historical, setHistorical] = useState<{ current: ArrangementVersion; previous: ArrangementVersion | null } | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [saveOpen, setSaveOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [editor, setEditor] = useState(username)
  const [note, setNote] = useState('')
  const saveDialog = useRef<HTMLDialogElement>(null)
  const pending = Object.values(controller.moves).filter(item => item.competitionId === id)
  useEffect(() => { void controller.load(id, !competition.deleted_at && ['open', 'closed'].includes(competition.status)) }, [id, competition.status, competition.deleted_at])
  useEffect(() => { if (searchOpen) searchInput.current?.focus() }, [searchOpen])
  useEffect(() => { if (saveOpen) saveDialog.current?.showModal() }, [saveOpen])
  useEffect(() => {
    setHistorical(null); setHistoryError('')
    if (!selectedVersion || !state) return
    let cancelled = false
    const summary = state.versions.find(version => version.id === selectedVersion)
    const previous = state.versions.find(version => version.sequence === (summary?.sequence ?? 0) - 1)
    void Promise.all([arrangementVersion(id, selectedVersion), previous ? arrangementVersion(id, previous.id) : Promise.resolve(null)]).then(([current, prior]) => {
      if (!cancelled) setHistorical({ current, previous: prior })
    }).catch(error => { if (!cancelled) setHistoryError((error as Error).message) })
    return () => { cancelled = true }
  }, [selectedVersion, id])
  const rows = selectedVersion ? historical?.current.rows ?? [] : state?.rows ?? []
  const baseline = selectedVersion ? historical?.previous?.rows ?? historical?.current.rows ?? [] : state?.latest?.rows ?? rows
  const changes = arrangementChanges(rows, baseline)
  const big = workspace?.save
  const canSave = !readonly && !selectedVersion && !!state?.latest && workspace?.verified && !pending.length && !big && changes.length > 0
  const boardReadonly = readonly || !!selectedVersion || !state?.latest || !!big
  return <section className="arrangement-workspace" aria-label="當次比賽級數安排">
    <div className="arrangement-toolbar"><div><h2>{competition.name}</h2><small>{selectedVersion ? `回看：${historical?.current.label ?? '讀取中'}` : '目前安排'}</small></div><div className="arrangement-tools">
      <button className="icon-button secondary" aria-label="搜尋姓名" aria-expanded={searchOpen} onClick={() => { setSearchOpen(!searchOpen); if (searchOpen) setSearch('') }}>⌕</button>
      <button className="secondary" onClick={() => setHistoryOpen(!historyOpen)} aria-expanded={historyOpen}>歷史</button>
      {selectedVersion ? <button onClick={() => { setSelectedVersion(null); setHistorical(null) }}>回目前安排</button> : <button disabled={!canSave} onClick={() => { setLabel(workspace?.draft?.label ?? `版本 ${(state?.latest?.sequence ?? 0) + 1}`); setEditor(workspace?.draft?.editor_label ?? username); setNote(workspace?.draft?.note ?? ''); setSaveOpen(true) }}>保存完整安排</button>}
      <button className="icon-button secondary" aria-label="重新讀取安排" disabled={workspace?.loading || big?.status === 'saving'} onClick={() => void controller.load(id, !readonly)}>↻</button>
    </div></div>
    {searchOpen && <div className="arrangement-search"><input ref={searchInput} type="search" aria-label="搜尋姓名或辨識註記" value={search} onChange={event => setSearch(event.target.value)} placeholder="輸入名字" /></div>}
    <div className="arrangement-status" role="status">{selectedVersion ? '歷史版本唯讀' : readonly ? '此場次為唯讀' : big?.status === 'saving' ? '正在保存完整安排…' : pending.some(item => item.status === 'saving') ? '正在自動儲存…' : workspace?.loading ? '讀取中…' : workspace?.notice || (state?.latest ? `上次保存：${state.latest.label} · ${time(state.latest.created_at)}` : '')}</div>
    {workspace?.error && <p role="alert" className="notice error">{workspace.error} <button className="secondary" onClick={() => void controller.load(id, !readonly)}>重新讀取</button></p>}
    {!!big && big.status !== 'saving' && <div className="arrangement-recovery" role="alert"><p>{big.status === 'refresh' ? '已保存，需讀取目前安排確認後才能繼續。' : big.error}</p><details><summary>這次保存：{big.payload.label || '預設名稱'}</summary><p>顯示編輯者：{big.payload.editor_label || username}</p><p>備註：{big.payload.note || '未填'}</p></details>{big.status === 'unknown' && <p>結果尚未確認。這場暫停移動與再次保存，請確認原操作。</p>}{big.status === 'rejected' ? <button onClick={() => controller.discardSave(id)}>重新讀取並核對</button> : <button onClick={() => controller.retrySave(id)}>{big.status === 'refresh' ? '讀取目前安排' : '確認保存結果／原樣重試'}</button>}</div>}
    {pending.filter(item => item.status !== 'saving').map(item => <div className="arrangement-recovery" key={item.row.registration_id} data-pending-id={item.row.registration_id} role="alert"><span>{item.row.member_name}：{item.row.competition_level} → {item.level} 級。{item.status === 'refresh' ? '已儲存，等待讀回目前安排。' : item.error}</span>{item.status === 'rejected' ? <button onClick={() => controller.discardMove(item.row.registration_id)}>放棄未完成移動並核對</button> : <button onClick={() => controller.retryMove(item.row.registration_id)}>{item.status === 'refresh' ? '讀回目前安排' : '確認移動結果／原樣重試'}</button>}</div>)}
    <div className={`arrangement-content ${historyOpen ? 'with-history' : ''}`}>
      <div className="arrangement-sheet"><LevelCardBoard rows={rows} changes={changes} search={search} readonly={boardReadonly} pending={selectedVersion ? {} : controller.moves} onMove={(row, level) => controller.move(id, row, level)} />
        <details className="arrangement-help"><summary>操作說明</summary><p>滑鼠拖動姓名；手機長按小把手再拖動，表格其他位置可水平捲動。點姓名可查看或用鍵盤選級數。每次移動自動儲存；橙色表示改級、綠色表示新增，移出項目見歷史側欄。保存完整安排後以該版為新基準。</p></details>
      </div>
      {historyOpen && <aside className="arrangement-history" aria-label="安排歷史"><h3>保存紀錄</h3><button className="secondary" aria-pressed={!selectedVersion} onClick={() => setSelectedVersion(null)}>目前安排</button>
        {state?.versions.map(version => <button className={`version-item secondary ${selectedVersion === version.id ? 'selected' : ''}`} key={version.id} onClick={() => setSelectedVersion(version.id)}><strong>{version.label}</strong><small>{time(version.created_at)}</small><small>顯示編輯者：{version.editor_label}</small></button>)}
        {historyError && <p role="alert">{historyError}</p>}
        {historical && selectedVersion && <div className="version-meta"><p>顯示編輯者：{historical.current.editor_label}</p><p>實際操作：{historical.current.actor_name}</p>{historical.current.note && <p>備註：{historical.current.note}</p>}</div>}
        <h3>{selectedVersion ? '相較前一保存版本' : `相較 ${state?.latest?.label ?? '起始基準'}`}</h3>
        {!changes.length && <p>沒有安排變更</p>}
        <ul className="arrangement-changes">{changes.map(change => <li className={`net-${change.kind}`} key={change.row.registration_id}><strong>{change.row.member_name}</strong>{change.row.distinguishing_note && <small>{change.row.distinguishing_note}</small>}<span>{changeText(change)}</span></li>)}</ul>
      </aside>}
    </div>
    {saveOpen && <dialog ref={saveDialog} className="arrangement-dialog" aria-labelledby="save-arrangement-title" onCancel={() => setSaveOpen(false)}><h3 id="save-arrangement-title">保存完整安排</h3><label>版本名稱<input maxLength={100} value={label} onChange={event => { setLabel(event.target.value); controller.setDraft(id, { label: event.target.value, editor_label: editor, note }) }} /></label><label>顯示編輯者<input list="arrangement-editors" maxLength={100} value={editor} onChange={event => { setEditor(event.target.value); controller.setDraft(id, { label, editor_label: event.target.value, note }) }} /></label><datalist id="arrangement-editors">{[...new Set([username, ...(state?.versions.map(version => version.editor_label) ?? [])])].map(value => <option key={value} value={value} />)}</datalist><label>備註（選填）<textarea maxLength={500} value={note} onChange={event => { setNote(event.target.value); controller.setDraft(id, { label, editor_label: editor, note: event.target.value }) }} /></label><p>實際操作帳號：{username}</p><button disabled={!canSave} onClick={() => { controller.setDraft(id, { label, editor_label: editor, note }); controller.save(id, { label, editor_label: editor, note }); setSaveOpen(false) }}>保存</button><button className="secondary" onClick={() => setSaveOpen(false)}>取消</button></dialog>}
  </section>
}

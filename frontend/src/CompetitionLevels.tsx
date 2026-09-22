import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrangementPrint } from './ArrangementPrint'
import { arrangementVersion } from './api'
import { LevelCardBoard, arrangementChanges, changeText, structureSignature } from './LevelCardBoard'
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
  const [printJob,setPrintJob]=useState<Parameters<typeof ArrangementPrint>[0]|null>(null)
  useEffect(()=>{
    if(!printJob)return
    const clear=()=>setPrintJob(null)
    window.addEventListener('afterprint',clear)
    const frame=requestAnimationFrame(()=>{try{window.print()}catch{clear()}})
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('afterprint',clear)}
  },[printJob])
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [vegetarian, setVegetarian] = useState(false)
  const searchInput = useRef<HTMLInputElement>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const versionList=useRef<HTMLDivElement>(null)
  const historyView=useRef<{id:string;opened:boolean;latest:number}>({id:'',opened:false,latest:-1})
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null)
  const [historical, setHistorical] = useState<{ current: ArrangementVersion; previous: ArrangementVersion | null } | null>(null)
  const [historyError, setHistoryError] = useState('')
  useEffect(()=>setPrintJob(null),[id,selectedVersion])
  const [saveOpen, setSaveOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [editor, setEditor] = useState(username)
  const [note, setNote] = useState('')
  const saveDialog = useRef<HTMLDialogElement>(null)
  const operation = workspace?.operation
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
  const layout = selectedVersion ? historical?.current.layout ?? null : state?.layout ?? null
  const oldLayout = selectedVersion ? historical?.previous?.layout ?? null : state?.layout_baseline ?? null
  const changes = arrangementChanges(rows, baseline, layout, oldLayout)
  const structural = !!layout && !!oldLayout && structureSignature(layout) !== structureSignature(oldLayout)
  const orderedVersions=[...(state?.versions??[])].sort((a,b)=>a.sequence-b.sequence)
  const newestSequence=orderedVersions.at(-1)?.sequence??-1
  useLayoutEffect(()=>{
    const previous=historyView.current
    if(historyOpen && versionList.current && (previous.id!==id||!previous.opened||(newestSequence>previous.latest&&!selectedVersion))) {
      versionList.current.scrollTop=versionList.current.scrollHeight
    }
    historyView.current={id,opened:historyOpen,latest:newestSequence}
  },[historyOpen,id,newestSequence])
  const dietUnknown = rows.filter(row => row.diet === null).length
  const big = workspace?.save
  const canSave = !readonly && !selectedVersion && !!state?.latest && workspace?.verified && !operation && !big && (changes.length > 0 || structural)
  const boardReadonly = readonly || !!selectedVersion
  const busy = !!big || !!operation || !workspace?.verified
  return <section className="arrangement-workspace" aria-label="當次比賽級數安排">
    {printJob&&<ArrangementPrint {...printJob}/>}
    <div className="arrangement-toolbar"><div><h2>{competition.name}</h2><small>{selectedVersion ? `回看：${historical?.current.label ?? '讀取中'}` : '目前安排'}</small></div><div className="arrangement-tools">
      <button className="secondary" disabled={selectedVersion?!historical:!state||busy} onClick={()=>setPrintJob({rows,layout,title:competition.name,version:selectedVersion?`歷史：${historical!.current.label}`:'目前安排'})}>列印安排</button>
      <button className="secondary vegetarian-toggle" aria-pressed={vegetarian} onClick={() => setVegetarian(!vegetarian)}>素食 {rows.filter(row => row.diet === 'vegetarian').length} 人{dietUnknown ? `（${dietUnknown} 人未記錄）` : ''}</button>
      <button className="icon-button secondary" aria-label="搜尋姓名" aria-expanded={searchOpen} onClick={() => { setSearchOpen(!searchOpen); if (searchOpen) setSearch('') }}>⌕</button>
      <button className="secondary" onClick={() => setHistoryOpen(!historyOpen)} aria-expanded={historyOpen}>歷史</button>
      {selectedVersion ? <button onClick={() => { setSelectedVersion(null); setHistorical(null) }}>回目前安排</button> : <button disabled={!canSave} onClick={() => { setLabel(workspace?.draft?.label ?? `版本 ${(state?.latest?.sequence ?? 0) + 1}`); setEditor(workspace?.draft?.editor_label ?? username); setNote(workspace?.draft?.note ?? ''); setSaveOpen(true) }}>保存完整安排</button>}
      <button className="icon-button secondary" aria-label="重新讀取安排" disabled={workspace?.loading || big?.status === 'saving'} onClick={() => void controller.load(id, !readonly)}>↻</button>
    </div></div>
    {searchOpen && <div className="arrangement-search"><input ref={searchInput} type="search" aria-label="搜尋姓名或辨識註記" value={search} onChange={event => setSearch(event.target.value)} placeholder="輸入名字" /></div>}
    <div className="arrangement-status" role="status">{selectedVersion ? '歷史版本唯讀' : readonly ? '此場次為唯讀' : big?.status === 'saving' ? '正在保存完整安排…' : operation?.status === 'saving' ? '正在自動儲存…' : workspace?.loading ? '讀取中…' : workspace?.notice || (state?.latest ? `上次保存：${state.latest.label} · ${time(state.latest.created_at)}` : '')}</div>
    {workspace?.error && <p role="alert" className="notice error">{workspace.error} <button className="secondary" onClick={() => void controller.load(id, !readonly)}>重新讀取</button></p>}
    {!!big && big.status !== 'saving' && <div className="arrangement-recovery" role="alert"><p>{big.status === 'refresh' ? '已保存，需讀取目前安排確認後才能繼續。' : big.error}</p><details><summary>這次保存：{big.payload.label || '預設名稱'}</summary><p>顯示編輯者：{big.payload.editor_label || username}</p><p>備註：{big.payload.note || '未填'}</p></details>{big.status === 'unknown' && <p>結果尚未確認。這場暫停移動與再次保存，請確認原操作。</p>}{big.status === 'rejected' ? <button onClick={() => controller.discardSave(id)}>重新讀取並核對</button> : <button onClick={() => controller.retrySave(id)}>{big.status === 'refresh' ? '讀取目前安排' : '確認保存結果／原樣重試'}</button>}</div>}
    {operation && operation.status !== 'saving' && <div className="arrangement-recovery" role="alert"><p>{operation.status === 'refresh' ? '已儲存，等待讀回目前布局；這場暫停修改。' : operation.error}</p>{operation.status === 'unknown' && <p>結果尚未確認，這場暫停所有表格調整與保存；重試不會重複執行同一次修改。</p>}{operation.status === 'rejected' ? <button onClick={() => controller.discardOperation(id)}>重新讀取並核對</button> : <button onClick={() => controller.retryOperation(id)}>{operation.status === 'refresh' ? '讀回目前安排' : '確認操作結果／原樣重試'}</button>}</div>}
    {!layout && <p className="notice">舊版未記錄儲存格位置；以下僅按級數與順位檢視，不代表當時分組。未保存的餐食與長期級數顯示未知。</p>}
    {layout && !selectedVersion && !state?.latest?.layout && <p className="notice">級數與名單仍比較上次保存；位置與文字比較本次啟用布局時的基準。</p>}
    <div className={`arrangement-content ${historyOpen ? 'with-history' : ''}`}>
      <div className="arrangement-sheet"><LevelCardBoard canUndo={!!workspace?.undoStack?.length&&workspace?.undoToken===state?.state_token} onUndo={()=>controller.undo(id)} confirmedGrid={workspace?.confirmedGrid} historical={!!selectedVersion} competitionId={id} key={`${id}/${selectedVersion ?? 'current'}`} stateToken={state?.state_token??''} rows={rows} layout={layout} baselineLayout={oldLayout} changes={changes} search={search} vegetarian={vegetarian} readonly={boardReadonly} busy={busy} textDrafts={workspace?.texts ?? {}} onTextDraft={(key, text) => controller.setTextDraft(id,key,text)} onOperate={(operation,token) => controller.operate(id, operation,token)} />
        <details className="arrangement-help"><summary>操作說明</summary><p>滑鼠拖動姓名；手機長按小把手再拖動，表格其他位置可水平捲動。單擊／輕點姓名選取儲存格，雙擊／連點兩下查看本場餐食與級數。鍵盤 Space 選格、Enter 查看資訊；資訊內選級數可移到欄底。範圍選取時點姓名只延伸選區。拖到選手中央交換位置，上下邊界插入並讓下方選手向下移；拖到空格直接移動、來源留空。放手前請核對交換或插入提示。搜尋只顯示符合姓名，其他選手以已占用格表示，不改格位；素食以柔和底色及「素」標記提示。表格邊界的＋可在該處插入；級數標題上緣的＋新增表頭列。邊緣可右鍵或點選開啟整排／文字欄刪除。表格上方工具列可對選取範圍設底色、合併或解除合併；復原或 Ctrl+Z（Mac 為 Command+Z）可逐步復原本次編輯已確認的操作，大保存後開始新區段。滑鼠從空白、文字或格邊拖曳框選，表頭單擊選取後可用工具列改字／底色，不影響級數身份或下面格子；表頭與資料格不混選合併。雙擊文字或表頭直接編輯（Enter送出、點外面保存退出、Escape取消）；手機選格後按編輯文字或範圍選取。合併格可直接改字，解除保留原文字格位。列印安排包含完整名單，不受搜尋或素食開關影響；寬表與長表分幅接續列印。橙色表示位置或級數異動，綠色表示新增。保存完整安排後以該版為新基準。</p></details>
      </div>
      {historyOpen && <>
        <aside className="arrangement-diff" aria-label="該版本變動"><h3>該版本變動</h3>
        <p className="arrangement-diff-baseline">{selectedVersion ? '相較前一保存版本' : `相較 ${state?.latest?.label ?? '起始基準'}`}</p>
        {structural && <p className="net-position">文字、行列、底色或合併結構已變更</p>}{!oldLayout && selectedVersion && <p>前版未記錄位置，無法比較位置差異。</p>}{!changes.length && !structural && <p>沒有可比較的安排變更</p>}
        <ul className="arrangement-changes">{changes.map(change => <li className={`net-${change.kind}`} key={change.row.registration_id}><strong>{change.row.member_name}</strong>{change.row.distinguishing_note && <small>{change.row.distinguishing_note}</small>}<span>{changeText(change)}</span></li>)}</ul>
        </aside>
      <aside className="arrangement-history" aria-label="版本紀錄"><h3>版本紀錄</h3><button className="secondary" aria-pressed={!selectedVersion} onClick={() => setSelectedVersion(null)}>目前安排</button>
        <div className="arrangement-version-list" ref={versionList} aria-label="保存版本，由舊到新">{orderedVersions.map(version => <button className={`version-item secondary ${selectedVersion === version.id ? 'selected' : ''}`} key={version.id} data-version-sequence={version.sequence} onClick={() => setSelectedVersion(version.id)}><strong>{version.label}{version.sequence===newestSequence&&<span className="version-latest">最新</span>}</strong><small>{time(version.created_at)}</small><small>顯示編輯者：{version.editor_label}</small></button>)}</div>
        {historyError && <p role="alert">{historyError}</p>}
        {historical && selectedVersion && <div className="version-meta"><p>顯示編輯者：{historical.current.editor_label}</p><p>實際操作：{historical.current.actor_name}</p>{historical.current.note && <p>備註：{historical.current.note}</p>}</div>}
      </aside></>}
    </div>
    {saveOpen && <dialog ref={saveDialog} className="arrangement-dialog" aria-labelledby="save-arrangement-title" onCancel={() => setSaveOpen(false)}><h3 id="save-arrangement-title">保存完整安排</h3><label>版本名稱<input maxLength={100} value={label} onChange={event => { setLabel(event.target.value); controller.setDraft(id, { label: event.target.value, editor_label: editor, note }) }} /></label><label>顯示編輯者<input list="arrangement-editors" maxLength={100} value={editor} onChange={event => { setEditor(event.target.value); controller.setDraft(id, { label, editor_label: event.target.value, note }) }} /></label><datalist id="arrangement-editors">{[...new Set([username, ...(state?.versions.map(version => version.editor_label) ?? [])])].map(value => <option key={value} value={value} />)}</datalist><label>備註（選填）<textarea maxLength={500} value={note} onChange={event => { setNote(event.target.value); controller.setDraft(id, { label, editor_label: editor, note: event.target.value }) }} /></label><p>實際操作帳號：{username}</p><button disabled={!canSave} onClick={() => { controller.setDraft(id, { label, editor_label: editor, note }); controller.save(id, { label, editor_label: editor, note }); setSaveOpen(false) }}>保存</button><button className="secondary" onClick={() => setSaveOpen(false)}>取消</button></dialog>}
  </section>
}

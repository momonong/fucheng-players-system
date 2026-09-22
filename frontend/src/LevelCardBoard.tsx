import { Fragment, useEffect, useRef, useState } from 'react'
import type { ArrangementRow, GridCell, GridLayout, GridOperation, GridPoint } from './types'
import { createPortal } from 'react-dom'
import { useLevelCardDrag } from './useLevelCardDrag'
import { useGridSelection } from './useGridSelection'
import { MemberLevelHistory } from './MemberLevelHistory'
import { shadeResolver, expandedSelection, ShadePalette, shades } from './gridShade'
import { CellShadeMenu, type CellShadePanel } from './CellShadeMenu'
import { GridInsertControls } from './GridInsertControls'
export const columnTitle = (c: GridLayout['columns'][number]) => c.title ?? (c.kind === 'level' ? `${c.level} 級` : '文字／備註')

export type ArrangementChange = { kind: 'level' | 'position' | 'added' | 'removed'; row: ArrangementRow; before?: number; after?: number }
export const pointKey = (p: GridPoint) => `${p.row_id}/${p.column_id}`
const positions = (layout: GridLayout | null) => new Map(layout?.cells.flatMap(c => c.kind === 'registration' ? [[c.registration_id, pointKey(c)] as const] : []))
export function arrangementChanges(rows: ArrangementRow[], baseline: ArrangementRow[], layout: GridLayout | null, oldLayout: GridLayout | null): ArrangementChange[] {
  const old = new Map(baseline.map(row => [row.registration_id, row])), current = new Set(rows.map(row => row.registration_id))
  const oldPositions = positions(oldLayout), currentPositions = positions(layout)
  const result: ArrangementChange[] = []
  for (const row of rows) {
    const before = old.get(row.registration_id)
    if (!before) result.push({ kind: 'added', row, after: row.competition_level })
    else if (before.competition_level !== row.competition_level) result.push({ kind: 'level', row, before: before.competition_level, after: row.competition_level })
    else if (layout && oldLayout && oldPositions.get(row.registration_id) !== currentPositions.get(row.registration_id)) result.push({ kind: 'position', row })
  }
  for (const row of baseline) if (!current.has(row.registration_id)) result.push({ kind: 'removed', row, before: row.competition_level })
  return result
}
export const changeText = (c: ArrangementChange) => c.kind === 'level' ? `${c.before} → ${c.after} 級` : c.kind === 'position' ? '位置已變更' : c.kind === 'added' ? `新增至 ${c.after} 級` : `移出（原 ${c.before} 級）`
export function structureSignature(layout: GridLayout | null) {
  if (!layout) return ''
  return JSON.stringify({ rows: layout.rows.map(r => [r.id, r.role, r.shade??0]), columns: layout.columns.map(c => [c.id, c.kind, c.level, columnTitle(c), c.shade??0, c.header_shade??null]),
    text: layout.cells.filter((c): c is GridCell & { kind: 'text' } => c.kind === 'text').map(c => [pointKey(c), c.text]).sort(),
    cell_shades: (layout.cell_shades??[]).map(c=>[pointKey(c),c.shade]).sort(),
    merges: layout.merges.map(m => [pointKey(m.start), pointKey(m.end)]).sort() })
}
export function legacyLayout(rows: ArrangementRow[]): GridLayout {
  const columns = Array.from({ length: 10 }, (_, i) => ({ id: `legacy-${i}`, kind: 'level' as const, level: i + 1 }))
  const groups = columns.map(c => rows.filter(r => r.competition_level === c.level).sort((a,b) => a.queue_sequence-b.queue_sequence))
  const heights = Array.from({ length: Math.max(8,...groups.map(g => g.length)) },(_,i) => ({ id: `legacy-row-${i}`, role: 'body' as const }))
  return { schema_version: 1, rows: heights, columns, merges: [], cells: groups.flatMap((g,i) => g.map((r,j) => ({ kind: 'registration' as const, registration_id:r.registration_id, row_id:heights[j].id, column_id:columns[i].id }))) }
}
export function LevelCardBoard({ rows, layout: knownLayout, baselineLayout, changes, search, vegetarian, readonly, busy, textDrafts, onTextDraft, onOperate, stateToken, competitionId, historical, confirmedGrid, canUndo, onUndo }: {
  rows: ArrangementRow[]; layout: GridLayout | null; baselineLayout: GridLayout | null; changes: ArrangementChange[]; search: string; vegetarian: boolean
  canUndo:boolean; onUndo:()=>void; confirmedGrid?:{request_id:string;action:GridOperation['action']}; historical:boolean; competitionId:string; stateToken: string; readonly: boolean; busy: boolean; textDrafts: Record<string, string>; onTextDraft: (key: string, text: string) => void; onOperate: (operation: GridOperation, expectedToken?: string) => void
}) {
  const layout = knownLayout ?? legacyLayout(rows)
  const [selected, setSelected] = useState<GridPoint | null>(null)
  const [selectedHeader,setSelectedHeader]=useState<string|null>(null)
  const [end, setEnd] = useState<GridPoint | null>(null)
  const [rangeMode, setRangeMode] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [shadePanel,setShadePanel]=useState<CellShadePanel|null>(null)
  const textPending=useRef<string|null>(null),composing=useRef(false),outsideDetail=useRef(false),outsideText=useRef(false),consumeOutsideClick=useRef(false)
  const shadePending=useRef<string|null>(null)
  const playerClicks=useRef<{id:string;at:number;count:number;touch:boolean}|null>(null)
  const playerPointer=useRef<{x:number;y:number}|null>(null)
  const cellShade=shadeResolver(layout)
  const [target, setTarget] = useState('1')
  const [editing, setEditing] = useState<{ key: string; point?: GridPoint; column?: string; inline: boolean; original: string; persisted:string } | null>(null)
  const [text, setText] = useState('')
  const detailDialog = useRef<HTMLDialogElement>(null), textDialog = useRef<HTMLDialogElement>(null), tableRef = useRef<HTMLTableElement>(null)
  const cells = new Map(layout.cells.map(c => [pointKey(c),c])), rowMap = new Map(rows.map(r => [r.registration_id,r]))
  const changesById = new Map(changes.map(c => [c.row.registration_id,c]))
  const oldText = new Map(baselineLayout?.cells.filter(c => c.kind === 'text').map(c => [pointKey(c), c.kind === 'text' ? c.text : '']))
  const blocked = readonly || busy || !knownLayout
  const detail = detailId ? rowMap.get(detailId) : undefined
  const merged = new Map<string,{ id: string; anchor: string; rowSpan: number; colSpan: number; text: string }>()
  for (const merge of layout.merges) {
    const ri = layout.rows.findIndex(r => r.id === merge.start.row_id), rj = layout.rows.findIndex(r => r.id === merge.end.row_id)
    const ci = layout.columns.findIndex(c => c.id === merge.start.column_id), cj = layout.columns.findIndex(c => c.id === merge.end.column_id)
    const texts: string[] = []
    for (let r=ri;r<=rj;r++) for (let c=ci;c<=cj;c++) { const value = cells.get(pointKey({ row_id:layout.rows[r].id,column_id:layout.columns[c].id })); if (value?.kind === 'text') texts.push(value.text) }
    for (let r=ri;r<=rj;r++) for (let c=ci;c<=cj;c++) merged.set(pointKey({ row_id:layout.rows[r].id,column_id:layout.columns[c].id }),{ id:merge.id, anchor:pointKey(merge.start), rowSpan:rj-ri+1,colSpan:cj-ci+1,text:texts.join(' ') })
  }
  function selectHeader(id:string){if(blocked)return;playerClicks.current=null;setSelectedHeader(id);setSelected(null);setEnd(null);setRangeMode(false);setShadePanel(null)}
  function select(point: GridPoint, extend = false) { playerClicks.current=null;setSelectedHeader(null);if ((extend || rangeMode) && selected) { setEnd(point); setRangeMode(false) } else { setSelected(point); setEnd(null) } }
  function selectPlayer(id:string,extend=false) {
    const cell=layout.cells.find(c=>c.kind==='registration'&&c.registration_id===id)
    if(cell)select(cell,extend)
  }
  function openDetail(id:string) {
    const row=rowMap.get(id)
    if(row){setDetailId(id);setTarget(String(row.competition_level))}
  }
  function clickPlayer(event:React.MouseEvent<HTMLButtonElement>,id:string) {
    const touch=(event.nativeEvent as PointerEvent).pointerType==='touch'
    const previous=playerClicks.current,now=performance.now()
    const extending=rangeMode||event.shiftKey
    // Keep both clicks of a range-ending gesture from collapsing the range or opening a dialog.
    if(previous?.id===id&&previous.count===0&&now-previous.at<500)return
    selectPlayer(id,event.shiftKey)
    if(extending){playerClicks.current={id,at:now,count:0,touch};return}
    const count=previous?.id===id&&previous.touch===touch&&now-previous.at<500?previous.count+1:1
    playerClicks.current={id,at:now,count,touch}
    if(touch&&count===2){playerClicks.current=null;openDetail(id)}
  }
  function doubleClickPlayer(id:string) {
    // A drag's suppressed click must never count toward opening details.
    if(playerClicks.current?.id===id&&playerClicks.current.count>=2&&!playerClicks.current.touch){playerClicks.current=null;openDetail(id)}
  }
  function keyPlayer(event:React.KeyboardEvent<HTMLButtonElement>,id:string) {
    if(event.key!=='Enter'&&event.key!==' ')return
    event.preventDefault();playerClicks.current=null
    if(event.key==='Enter'&&!rangeMode)openDetail(id)
    else selectPlayer(id)
  }
  const { drag, holding, start } = useLevelCardDrag((id, destination) => {
    if (blocked) return
    const source = layout.cells.find(c => c.kind === 'registration' && c.registration_id === id)
    if (!source || pointKey(source) === pointKey(destination))return
    const point={row_id:destination.row_id,column_id:destination.column_id}
    if(destination.mode==='swap')onOperate({action:'swap',registration_id:id,target_registration_id:destination.registrationId!})
    else if(destination.mode==='insert')onOperate({action:'insert',registration_id:id,target:point,side:destination.side!})
    else onOperate({action:'move_empty',registration_id:id,target:point})
  },!blocked&&!rangeMode)
  useEffect(()=>{if(drag)playerClicks.current=null},[drag])
  useEffect(() => { if (detailId) detailDialog.current?.showModal() },[detailId])
  useEffect(() => { if (editing && !editing.inline) textDialog.current?.showModal() },[editing])
  const selection=selected?expandedSelection(layout,selected,end??selected):null
  function selectedRange(point:GridPoint){
    if(!selection)return false
    const ri=layout.rows.findIndex(r=>r.id===point.row_id),ci=layout.columns.findIndex(c=>c.id===point.column_id)
    return ri>=selection.top&&ri<=selection.bottom&&ci>=selection.left&&ci<=selection.right
  }
  function openShade(point:GridPoint,left:number,top:number){
    if(blocked)return
    setSelectedHeader(null)
    const box=selectedRange(point)?selection:expandedSelection(layout,point)
    if(!box)return
    if(!selectedRange(point)){setSelected(point);setEnd(null);setRangeMode(false)}
    const local=new Map((layout.cell_shades??[]).map(c=>[pointKey(c),c.shade]))
    const values=new Set<number>()
    for(let r=box.top;r<=box.bottom;r++)for(let c=box.left;c<=box.right;c++)values.add(local.get(`${layout.rows[r].id}/${layout.columns[c].id}`)??0)
    setShadePanel({start:box.start,end:box.end,token:stateToken,left,top,value:values.size===1?[...values][0]:undefined})
  }
  useEffect(()=>{
    if(shadePending.current!==null&&confirmedGrid&&['shade_cells','shade_header'].includes(confirmedGrid.action)&&shadePending.current!==confirmedGrid.request_id){
      shadePending.current=null;setSelectedHeader(null);setSelected(null);setEnd(null);setRangeMode(false);setShadePanel(null)
    }
  },[confirmedGrid])
  function applyShade(shade:number){
    if(blocked||(!selection&&!selectedHeader))return
    shadePending.current=confirmedGrid?.request_id??''
    if(selectedHeader)operate({action:'shade_header',column_id:selectedHeader,shade},stateToken)
    else if(selection)operate({action:'shade_cells',start:selection.start,end:selection.end,shade},stateToken)
  }
  const localShades=new Map((layout.cell_shades??[]).map(c=>[pointKey(c),c.shade]))
  const selectedShades=new Set<number>()
  if(selectedHeader)selectedShades.add(layout.columns.find(c=>c.id===selectedHeader)?.header_shade??0)
  if(selection)for(let r=selection.top;r<=selection.bottom;r++)for(let c=selection.left;c<=selection.right;c++)selectedShades.add(localShades.get(`${layout.rows[r].id}/${layout.columns[c].id}`)??0)
  const startSelection = useGridSelection(!blocked, select)
  const selectionHasPlayer=layout.cells.some(c=>c.kind==='registration'&&selectedRange(c))
  const selectionMerge = selected ? merged.get(pointKey(selected)) : undefined
  const selectionCell = selected ? cells.get(pointKey(selected)) : undefined
  const operate = (op: GridOperation, expectedToken?: string) => { if (!blocked) onOperate(op,expectedToken) }
  useEffect(()=>{
    if(busy)return // Unknown/rejected input is kept until a verified successful read.
    const exists=(p:GridPoint)=>layout.rows.some(r=>r.id===p.row_id)&&layout.columns.some(c=>c.id===p.column_id)
    if(selectedHeader&&!layout.columns.some(c=>c.id===selectedHeader))setSelectedHeader(null)
    if(selected&&!exists(selected)){setSelected(null);setEnd(null);setRangeMode(false)}
    else if(end&&!exists(end))setEnd(null)
    if(editing&&((editing.point&&!exists(editing.point))||(editing.column&&!layout.columns.some(c=>c.id===editing.column))))setEditing(null)
  },[layout,busy])
  function beginEdit(point: GridPoint | null, column?: string, inline=false) {
    if(blocked)return
    const key=column?`column/${column}`:pointKey(point!)
    const cell=point?cells.get(pointKey(point)):undefined, merge=point?merged.get(pointKey(point)):undefined
    if(cell?.kind==='registration')return
    const value=column?columnTitle(layout.columns.find(c=>c.id===column)!):merge?.text??(cell?.kind==='text'?cell.text:'')
    if(point)select(point)
    else if(column)selectHeader(column)
    setText(textDrafts[key]??value);setEditing({key,point:point??undefined,column,inline,original:textDrafts[key]??value,persisted:value})
  }
  function commitText(){
    if(!editing||blocked||composing.current||textPending.current!==null)return
    if(text===editing.persisted){setEditing(null);return}
    textPending.current=confirmedGrid?.request_id??''
    operate(editing.column?{action:'column_title',column_id:editing.column,text}:{action:'text',target:editing.point!,text})
  }
  function cancelEdit(){if(blocked){setEditing(null);return}if(editing)onTextDraft(editing.key,editing.original);setEditing(null)}
  useEffect(()=>{
    if(textPending.current!==null&&confirmedGrid&&['text','column_title'].includes(confirmedGrid.action)&&textPending.current!==confirmedGrid.request_id){textPending.current=null;setEditing(null)}
  },[confirmedGrid])
  useEffect(()=>{if(!busy)textPending.current=null},[busy])
  useEffect(()=>{
    const undoKey=(e:KeyboardEvent)=>{
      const target=e.target as HTMLElement
      if(e.key.toLowerCase()!=='z'||!(e.ctrlKey||e.metaKey)||e.shiftKey||e.altKey||e.isComposing||target.closest('input,textarea,select,[contenteditable="true"],dialog'))return
      if(!readonly){e.preventDefault();if(!blocked&&canUndo)onUndo()}
    }
    document.addEventListener('keydown',undoKey);return()=>document.removeEventListener('keydown',undoKey)
  },[readonly,blocked,canUndo,onUndo])
  useEffect(()=>{
    const reset=(e:PointerEvent)=>{consumeOutsideClick.current=false;if(!(e.target as HTMLElement).closest('.cell-name'))playerClicks.current=null}
    const consume=(e:MouseEvent)=>{if(consumeOutsideClick.current){consumeOutsideClick.current=false;e.preventDefault();e.stopImmediatePropagation()}}
    document.addEventListener('pointerdown',reset,true);document.addEventListener('click',consume,true)
    return()=>{document.removeEventListener('pointerdown',reset,true);document.removeEventListener('click',consume,true)}
  },[])
  useEffect(()=>{
    if(!editing?.inline||blocked)return
    const outside=(e:PointerEvent)=>{
      if((e.target as HTMLElement).closest('.grid-inline-editor'))return
      consumeOutsideClick.current=true;e.preventDefault();e.stopImmediatePropagation();commitText()
    }
    document.addEventListener('pointerdown',outside,true)
    return()=>document.removeEventListener('pointerdown',outside,true)
  },[editing,text,blocked])
  const beyond=(event:React.PointerEvent<HTMLDialogElement>)=>{const box=event.currentTarget.getBoundingClientRect();return event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom}
  const inlineEditor=()=> <input className="grid-inline-editor" aria-label="直接編輯文字" autoFocus maxLength={500} disabled={blocked} value={text}
    onCompositionStart={()=>{composing.current=true}} onCompositionEnd={()=>{composing.current=false}} onChange={e=>{setText(e.target.value);if(editing)onTextDraft(editing.key,e.target.value)}} onClick={e=>e.stopPropagation()}
    onKeyDown={e=>{if(e.nativeEvent.isComposing)return;if(e.key==='Enter'){e.preventDefault();commitText()}if(e.key==='Escape'){e.preventDefault();cancelEdit()}}}/>
  return <>
    {!readonly&&<div className="grid-selection-tools" role="toolbar" aria-label="表格編輯工具">
      <button className="secondary" disabled={blocked||!canUndo} title="復原（Ctrl+Z／Command+Z）" onClick={onUndo}>復原</button>
      <fieldset className="cell-shade-toolbar"><legend>儲存格底色</legend><ShadePalette local value={selectedShades.size===1?[...selectedShades][0]:undefined} disabled={blocked||(!selection&&!selectedHeader)} onChoose={applyShade}/></fieldset>
      <button className="secondary" disabled={blocked||(!selected&&!selectedHeader)||selectionCell?.kind==='registration'} onClick={()=>selectedHeader?beginEdit(null,selectedHeader):selected&&beginEdit(selected)}>編輯文字</button>
      <button className="secondary grid-touch-range" disabled={blocked||!selected} aria-pressed={rangeMode} onClick={()=>setRangeMode(!rangeMode)}>{rangeMode?'點選範圍另一角':'範圍選取'}</button>
      <button className="secondary" disabled={blocked||!selected||!end||!!selectionMerge||selectionHasPlayer} onClick={()=>selected&&end&&operate({action:'merge',start:selected,end})}>合併儲存格</button>
      <button className="secondary" disabled={blocked||!selectionMerge} onClick={()=>selectionMerge&&operate({action:'unmerge',merge_id:selectionMerge.id})}>解除合併儲存格</button>
      <button className="secondary" disabled={!selected&&!selectedHeader} onClick={()=>{setSelectedHeader(null);setSelected(null);setEnd(null);setRangeMode(false)}}>取消選取</button>
    </div>}
    <div className={`arrangement-table-scroll ${drag ? 'is-dragging' : ''}`} tabIndex={0} role="region" aria-label="級數表格，可水平捲動">
      <div className="grid-canvas" style={{minWidth:Math.max(1100,layout.columns.length*110)}}>
      {!readonly&&<GridInsertControls layout={layout} table={tableRef} stateToken={stateToken} disabled={blocked} onOperate={operate}/>}
      <table ref={tableRef} className="arrangement-table grid-table" aria-label="當次級數表" style={{ minWidth: layout.columns.length * 110 }}>
        <tbody>{layout.rows.map((r,ri) => <Fragment key={r.id}>{r.role==='body'&&(ri===0||layout.rows[ri-1].role==='header')&&<tr className="grid-level-head">{layout.columns.map(c=><th scope="col" key={c.id} data-column-id={c.id} data-grid-header={c.id} data-header-shade={c.header_shade??c.shade??0} className={selectedHeader===c.id?'grid-selected':''} style={{background:shades[c.header_shade??c.shade??0]}} onContextMenu={e=>{if(!blocked){e.preventDefault();selectHeader(c.id)}}}>{editing?.inline&&editing.column===c.id?inlineEditor():<button className="grid-column-title" disabled={blocked} aria-pressed={selectedHeader===c.id} onDoubleClick={()=>beginEdit(null,c.id,true)} aria-label={`選取第 ${layout.columns.indexOf(c)+1} 欄表頭`} onClick={()=>selectHeader(c.id)}>{columnTitle(c)}</button>}</th>)}</tr>}<tr data-row-id={r.id} data-row-role={r.role}>{layout.columns.map((c,ci) => {
          const point = { row_id:r.id,column_id:c.id }, k=pointKey(point), merge=merged.get(k)
          if (merge && merge.anchor !== k) return null
          const cell=cells.get(k), row=cell?.kind==='registration' ? rowMap.get(cell.registration_id) : undefined
          const change=row ? changesById.get(row.registration_id) : undefined
          const match=!row || `${row.member_name} ${row.distinguishing_note ?? ''}`.includes(search.trim())
          const dropEnabled=!blocked && r.role==='body' && c.kind==='level' && !merge && cell?.kind!=='text'
          const shade=cellShade(ri,ci,merge?.rowSpan,merge?.colSpan)
          const isTarget=drag?.target&&pointKey(drag.target)===k
          const textChanged=knownLayout && baselineLayout && ((cell?.kind==='text' ? cell.text : '') !== (oldText.get(k) ?? ''))
          return <td key={c.id} rowSpan={merge?.rowSpan} colSpan={merge?.colSpan} data-drop-row={r.id} data-drop-column={c.id} data-drop-level={c.level ?? undefined} data-drop-enabled={dropEnabled}
            data-drop-registration={row?.registration_id} data-drop-name={match?row?.member_name:undefined} data-shade={shade} style={{background:shades[shade]}} data-grid-cell={k} className={`${selectedRange(point) ? 'grid-selected' : ''} ${isTarget ? `drop-${drag!.target!.mode} ${drag!.target!.side??''}` : ''} ${textChanged ? 'net-position' : ''}`}
            onContextMenu={event=>{if(blocked)return;event.preventDefault();event.stopPropagation();openShade(point,event.clientX,event.clientY)}}
            onPointerDown={event=>startSelection(event,point)} onDoubleClick={event=>{if(!(event.target as HTMLElement).closest('.cell-name,.cell-grip'))beginEdit(point,undefined,true)}}
            onClick={event => { if ((event.target as HTMLElement).closest('.cell-name,.cell-grip')) return; select(point,event.shiftKey) }}>
            {editing?.inline&&editing.point&&pointKey(editing.point)===k?inlineEditor():row ? <div data-draggable={!blocked} data-registration-id={row.registration_id} className={`arrangement-cell ${drag?.card.id===row.registration_id ? 'is-drag-source' : ''} ${change ? `net-${change.kind}` : ''} ${!match ? 'search-hidden' : search.trim() ? 'search-match' : ''} ${vegetarian && row.diet==='vegetarian' ? 'diet-highlight' : ''}`}>
              {!match ? <span className="search-occupied" aria-label="搜尋隱藏，已占用">已占用</span> : <>
              {!readonly && <button className="cell-grip" type="button" disabled={blocked} aria-label={`拖曳 ${row.member_name} ${row.distinguishing_note ?? ''}`} onPointerDown={event => {if(!rangeMode)start(event,{ id:row.registration_id,name:row.member_name,note:row.distinguishing_note })}} onClick={()=>{playerClicks.current=null;selectPlayer(row.registration_id)}} onKeyDown={e=>keyPlayer(e,row.registration_id)} onContextMenu={event=>event.preventDefault()}>{holding===row.registration_id?'…':'⠿'}</button>}
              <button className="cell-name" type="button" aria-label={`${row.member_name}${row.distinguishing_note ? `・${row.distinguishing_note}` : ''}，單擊選取、雙擊查看`} title={row.member_name}
                onPointerDown={event => {playerPointer.current={x:event.clientX,y:event.clientY};if(event.pointerType==='mouse'&&!blocked&&!rangeMode)start(event,{id:row.registration_id,name:row.member_name,note:row.distinguishing_note})}}
                onPointerMove={event=>{const p=playerPointer.current;if(p&&Math.hypot(event.clientX-p.x,event.clientY-p.y)>8)playerClicks.current=null}}
                onPointerCancel={()=>{playerClicks.current=null;playerPointer.current=null}}
                onClick={event=>clickPlayer(event,row.registration_id)} onDoubleClick={()=>doubleClickPlayer(row.registration_id)} onKeyDown={event=>keyPlayer(event,row.registration_id)}><span className="cell-name-line"><span className="cell-person-name">{row.member_name}</span>{vegetarian&&row.diet==='vegetarian'&&<em className="diet-mark" aria-label="本場素食">素</em>}</span>{row.distinguishing_note&&<small>{row.distinguishing_note}</small>}</button>
              {change&&<span className="cell-change" aria-label={changeText(change)}>{change.kind==='added'?'+':change.kind==='position'?'↕':`${change.before}→${change.after}`}</span>}
</> }
            </div> : <button type="button" className="grid-empty" aria-label={`第 ${ri+1} 列第 ${ci+1} 欄${merge ? '合併格' : ''}，${merge?.text || (cell?.kind==='text'?cell.text:'空白')}`} onClick={event=>{ event.stopPropagation();select(point,event.shiftKey) }}>{merge?.text || (cell?.kind==='text'?cell.text:'')}</button>}
          </td>
        })}</tr></Fragment>)}</tbody>
      </table>
      </div>
    </div>
    {shadePanel&&<CellShadeMenu panel={shadePanel} disabled={blocked} onClose={()=>setShadePanel(null)} onChoose={shade=>{
      if(blocked)return
      shadePending.current=confirmedGrid?.request_id??''
      operate({action:'shade_cells',start:shadePanel.start,end:shadePanel.end,shade},shadePanel.token);setShadePanel(null)
    }}/>}
    {drag&&createPortal(<div className="level-drag-ghost" aria-hidden="true" style={{width:drag.width,height:drag.height,left:Math.max(8,Math.min(drag.x+12,window.innerWidth-drag.width-8)),top:Math.max(8,Math.min(drag.y+(drag.touch?-drag.height-16:16),window.innerHeight-drag.height-8))}}><strong>{drag.card.name}</strong>{drag.card.note&&<small>{drag.card.note}</small>}</div>,document.body)}
    {drag?.target&&createPortal(<div className="drag-intent" role="status" data-drag-intent={drag.target.mode} style={{left:Math.max(8,Math.min(drag.x-80,window.innerWidth-240)),top:Math.max(8,Math.min(drag.y+(drag.touch?20:drag.height+24),window.innerHeight-48))}}>{drag.target.label}</div>,document.body)}
    {detail&&<dialog ref={detailDialog} className="arrangement-dialog" aria-labelledby="cell-detail-title" onCancel={()=>setDetailId(null)} onPointerDown={e=>{outsideDetail.current=beyond(e)}} onPointerUp={e=>{if(outsideDetail.current&&beyond(e))setDetailId(null);outsideDetail.current=false}}><button className="dialog-close secondary" aria-label="關閉" title="關閉" onClick={()=>setDetailId(null)}>×</button><h3 id="cell-detail-title">{detail.member_name}</h3><p>{detail.distinguishing_note || '無辨識註記'}</p>
      <p>本場餐食：<span className={`detail-diet diet-${detail.diet??'unknown'}`}>{detail.diet===null?'此版本未記錄':detail.diet==='vegetarian'?'素食':detail.diet==='omnivore'?'葷食':'未設定'}</span></p><p>當次級數：{detail.competition_level} 級・長期級數：{detail.member_level===null?'此版本未記錄':`${detail.member_level} 級`}</p>
      <MemberLevelHistory key={detail.member_id} competitionId={competitionId} memberId={detail.member_id} historical={historical}/>
      {!readonly&&<div className="detail-move"><label>移到級數<select disabled={blocked} value={target} onChange={e=>setTarget(e.target.value)}>{Array.from({length:10},(_,i)=><option key={i} value={i+1}>{i+1} 級</option>)}</select></label><button className="secondary" disabled={blocked} onClick={()=>{ operate({action:'move_bottom',registration_id:detail.registration_id,level:Number(target)});setDetailId(null) }}>移動</button><small>放到目標級數欄最下面。</small></div>}
      </dialog>}
    {editing&&!editing.inline&&<dialog ref={textDialog} className="arrangement-dialog" aria-labelledby="grid-text-title" onCancel={cancelEdit} onPointerDown={e=>{outsideText.current=beyond(e)}} onPointerUp={e=>{if(outsideText.current&&beyond(e))commitText();outsideText.current=false}}><h3 id="grid-text-title">儲存格文字</h3><label>文字<textarea onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();commitText()}}} onCompositionStart={()=>{composing.current=true}} onCompositionEnd={()=>{composing.current=false}} aria-label="儲存格文字內容" maxLength={500} disabled={blocked} value={text} onChange={e=>{setText(e.target.value);onTextDraft(editing.key,e.target.value)}} /></label><button disabled={blocked} onClick={commitText}>儲存文字</button><button className="secondary" onClick={cancelEdit}>{blocked?'返回表格核對（保留文字）':'取消'}</button></dialog>}
  </>
}

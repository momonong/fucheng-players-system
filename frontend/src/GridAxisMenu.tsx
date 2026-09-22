import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { GridLayout, GridOperation } from './types'
export type AxisTarget={axis:'row'|'column';id:string;index:number;offset:number;size:number}
export type AxisPanel={target:AxisTarget;layout:GridLayout;token:string;left:number;top:number;confirm:boolean}

function deletionPreview({layout,target}:AxisPanel) {
  const field=target.axis==='row'?'row_id':'column_id'
  const removed=layout.cells.filter(c=>c[field]===target.id)
  const item=target.axis==='row'?layout.rows.find(r=>r.id===target.id):layout.columns.find(c=>c.id===target.id)
  const people=removed.filter(c=>c.kind==='registration').length
  let blocked=people?`這一整排有 ${people} 位選手，請先移走再刪除；不會刪除選手或報名。`:''
  if(target.axis==='column'&&item&&'kind' in item&&item.kind==='level')blocked='1到10級的固定級數欄不能刪除。'
  if(target.axis==='row'&&item&&'role' in item&&item.role==='body'&&layout.rows.filter(r=>r.role==='body').length<=1)blocked='請至少保留一排資料格，供後續安排選手。'
  const texts=removed.flatMap(c=>c.kind==='text'&&c.text.trim()?[{text:c.text,keep:false}]:[])
  for(const merge of layout.merges) {
    const ri=layout.rows.findIndex(r=>r.id===merge.start.row_id),rj=layout.rows.findIndex(r=>r.id===merge.end.row_id),ci=layout.columns.findIndex(c=>c.id===merge.start.column_id),cj=layout.columns.findIndex(c=>c.id===merge.end.column_id)
    const rows=layout.rows.slice(ri,rj+1),cols=layout.columns.slice(ci,cj+1)
    if(!(target.axis==='row'?rows:cols).some(v=>v.id===target.id))continue
    const content=layout.cells.filter(c=>rows.some(r=>r.id===c.row_id)&&cols.some(v=>v.id===c.column_id))
    const nonempty=content.filter(c=>c.kind==='text'&&c.text.trim())
    if(nonempty.length>1||content.some(c=>c.kind==='registration'))blocked='受影響的合併區內容有衝突，請先解除合併並整理文字。'
    const remains=(target.axis==='row'?rows:cols).some(v=>v.id!==target.id)
    for(const c of nonempty)if(remains&&c[field]===target.id&&c.kind==='text') {
      const record=texts.find(t=>t.text===c.text&&!t.keep);if(record)record.keep=true
    }
  }
  if(target.axis==='column'&&item&&'title' in item&&item.title&&item.title!=='文字／備註')texts.unshift({text:`欄標題：${item.title}`,keep:false})
  const title=target.axis==='row'?`第 ${target.index+1} 排（由左到右這一整排）`:`第 ${target.index+1} 直欄（由上到下的文字格）`
  return {blocked,texts,title}
}
export function GridAxisMenu({panel,disabled,onPanel,onOperate}:{panel:AxisPanel;disabled:boolean;onPanel:(value:AxisPanel|null)=>void;onOperate:(op:GridOperation,token?:string)=>void}) {
  const dialog=useRef<HTMLDialogElement>(null),preview=deletionPreview(panel)
  const [viewport,setViewport]=useState({width:innerWidth,height:innerHeight})
  useEffect(()=>{const resize=()=>setViewport({width:innerWidth,height:innerHeight});window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize)},[])
  const top=Math.max(8,Math.min(panel.top,viewport.height-Math.min(400,viewport.height-16)))
  useEffect(()=>{if(panel.confirm)dialog.current?.showModal()},[panel.confirm])
  useEffect(()=>{
    const outside=(e:PointerEvent)=>{if(!panel.confirm&&!(e.target as HTMLElement).closest('.grid-axis-popup,.grid-axis-more'))onPanel(null)}
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onPanel(null)}
    window.addEventListener('pointerdown',outside);window.addEventListener('keydown',key)
    return()=>{window.removeEventListener('pointerdown',outside);window.removeEventListener('keydown',key)}
  },[panel.confirm,onPanel])
  function remove(confirmed:boolean){
    if(disabled||preview.blocked)return
    onOperate({action:panel.target.axis==='row'?'delete_row':'delete_column',axis_id:panel.target.id,confirmed_text:confirmed},panel.token)
    onPanel(null)
  }
  const contents=<>{preview.texts.length>0&&<ul>{preview.texts.map((t,i)=><li key={i}><strong>{t.keep?'保留並移到剩餘合併區左上格：':'刪除：'}</strong>{t.text}</li>)}</ul>}<small>其餘格子的內容與選手位置保留。合併區會縮小，只剩一格時解除合併。</small></>
  return createPortal(panel.confirm?<dialog ref={dialog} className="arrangement-dialog axis-delete-dialog" aria-labelledby="axis-delete-title" onCancel={()=>onPanel(null)}>
    <h3 id="axis-delete-title">確認刪除這個範圍</h3><p>{preview.title}</p><div className="axis-delete-content">{contents}</div><div className="axis-delete-actions">
    <button className="secondary" autoFocus onClick={()=>onPanel(null)}>保留這個範圍</button><button className="danger" disabled={disabled||!!preview.blocked} onClick={()=>remove(true)}>確認刪除{panel.target.axis==='row'?'整排':'文字直欄'}</button></div>
  </dialog>:<div className="grid-axis-popup" role="group" aria-label="這個範圍的操作" style={{left:Math.max(8,Math.min(panel.left,viewport.width-300)),top,maxHeight:Math.min(400,viewport.height-top-8)}}>
    <strong>{preview.title}</strong><div className="axis-delete-content">{preview.blocked?<p role="status">{preview.blocked}</p>:contents}</div><div className="axis-delete-actions">
    <button className="danger" disabled={disabled||!!preview.blocked} onClick={()=>preview.texts.length?onPanel({...panel,confirm:true}):remove(false)}>刪除{panel.target.axis==='row'?'這一整排':'這個文字直欄'}</button>
    <button className="secondary" onClick={()=>onPanel(null)}>關閉</button></div>
  </div>,document.body)
}

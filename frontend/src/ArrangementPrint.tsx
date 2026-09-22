import { createPortal } from 'react-dom'
import type { ArrangementRow, GridLayout } from './types'
import { shadeResolver, PrintedShade } from './gridShade'
import { columnTitle, legacyLayout, pointKey } from './LevelCardBoard'

// Bounded tiles preserve source coordinates; wide merges are clipped to each tile,
// repeated with a continuation label. Every body registration belongs to one tile.
export function ArrangementPrint({rows,layout:known,title,version}:{rows:ArrangementRow[];layout:GridLayout|null;title:string;version:string}) {
  const layout=known??legacyLayout(rows), cells=new Map(layout.cells.map(c=>[pointKey(c),c])), people=new Map(rows.map(r=>[r.registration_id,r]))
  const cellShade=shadeResolver(layout)
  const headers=layout.rows.filter(r=>r.role==='header'),body=layout.rows.filter(r=>r.role==='body')
  const columnBands=Array.from({length:Math.ceil(layout.columns.length/12)},(_,i)=>layout.columns.slice(i*12,(i+1)*12))
  const rowBands=Array.from({length:Math.max(1,Math.ceil(body.length/18))},(_,i)=>body.slice(i*18,(i+1)*18))
  const multiple=columnBands.length*rowBands.length>1
  const merges=layout.merges.map(m=>{
    const rs=layout.rows.findIndex(r=>r.id===m.start.row_id),re=layout.rows.findIndex(r=>r.id===m.end.row_id),cs=layout.columns.findIndex(c=>c.id===m.start.column_id),ce=layout.columns.findIndex(c=>c.id===m.end.column_id)
    const memberCells=layout.cells.filter(c=>layout.rows.findIndex(r=>r.id===c.row_id)>=rs&&layout.rows.findIndex(r=>r.id===c.row_id)<=re&&layout.columns.findIndex(v=>v.id===c.column_id)>=cs&&layout.columns.findIndex(v=>v.id===c.column_id)<=ce)
    return {...m,rs,re,cs,ce,text:memberCells.flatMap(c=>c.kind==='text'?[c.text]:[]).join(' ')}
  })
  return createPortal(<section className="arrangement-print" aria-label="完整安排列印">{rowBands.flatMap((band,bi)=>columnBands.map((columns,ci)=>{
    const shown=[...headers,...band],rowIds=shown.map(r=>r.id),colIds=columns.map(c=>c.id)
    function renderRows(group:typeof shown){return group.map(r=><tr key={r.id} data-print-row={r.id}>{multiple&&<th className="print-coordinate" scope="row">{layout.rows.indexOf(r)+1}</th>}{columns.map(c=>{
      const ri=layout.rows.indexOf(r),cj=layout.columns.indexOf(c),merge=merges.find(m=>ri>=m.rs&&ri<=m.re&&cj>=m.cs&&cj<=m.ce)
      const intersectRows=merge?layout.rows.slice(merge.rs,merge.re+1).filter(v=>rowIds.includes(v.id)):[],intersectCols=merge?layout.columns.slice(merge.cs,merge.ce+1).filter(v=>colIds.includes(v.id)):[]
      if(merge&&(r.id!==intersectRows[0]?.id||c.id!==intersectCols[0]?.id))return null
      const cell=cells.get(pointKey({row_id:r.id,column_id:c.id})),person=cell?.kind==='registration'?people.get(cell.registration_id):undefined
      const continued=merge&&(ri!==merge.rs||cj!==merge.cs),split=merge&&(intersectRows.length!==merge.re-merge.rs+1||intersectCols.length!==merge.ce-merge.cs+1)
      return <td key={c.id} rowSpan={merge?intersectRows.length:undefined} colSpan={merge?intersectCols.length:undefined} data-print-cell={`${r.id}/${c.id}`} data-print-registration={person?.registration_id}>
        <PrintedShade shade={merge?cellShade(merge.rs,merge.cs,merge.re-merge.rs+1,merge.ce-merge.cs+1):cellShade(ri,cj)}/><span className="print-cell-content">
        {person?<><strong>{person.member_name}</strong>{person.diet==='vegetarian'&&<b className="print-vegetarian">素</b>}{person.distinguishing_note&&<small>{person.distinguishing_note}</small>}</>:merge?<>{merge.text}{split&&<small className="print-continuation">{continued?'（合併續）':'（合併跨頁）'}</small>}</>:cell?.kind==='text'?cell.text:''}
      </span></td>
    })}</tr>)}
    return <article className="arrangement-print-page" key={`${bi}/${ci}`}><header><h1>{title}</h1><p>{version}{multiple&&<> · 第 {bi*columnBands.length+ci+1} / {rowBands.length*columnBands.length} 幅{columnBands.length>1&&<> · 第 {ci*12+1}–{ci*12+columns.length} 欄</>}</>}</p></header>
      <p className="print-legend">共 {rows.length} 人 · 素＝本場素食{rows.some(r=>r.diet===null)?' · 此版未記錄的餐食保持未知':''}{!known?' · 舊版未保存格位，依級數與順位呈現，不代表當時分組':''}</p>
      <table style={{width:`${columns.length/Math.min(12,layout.columns.length)*100}%`}}><thead>{renderRows(headers)}<tr>{multiple&&<th className="print-coordinate">列</th>}{columns.map(c=><th key={c.id} data-print-header={c.id}><PrintedShade shade={c.header_shade??c.shade??0}/><span className="print-cell-content">{columnTitle(c)}</span></th>)}</tr></thead><tbody>{renderRows(band)}</tbody></table>
      {columnBands.length>1&&<p className="print-legend">寬表分幅：依原欄位接續閱讀；選手不重複，合併文字於交界標示續接。</p>}
    </article>
  }))}</section>,document.body)
}

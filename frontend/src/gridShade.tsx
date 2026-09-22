import type { GridLayout, GridPoint } from './types'
export const shades=['#ffffff','#ededed','#d9d9d9','#c4c4c4']
const key=(p:GridPoint)=>`${p.row_id}/${p.column_id}`
export function shadeResolver(layout:GridLayout) {
  const local=new Map((layout.cell_shades??[]).map(c=>[key(c),c.shade]))
  return (rowIndex:number,columnIndex:number,rowSpan=1,colSpan=1)=>{
    let shade=0
    for(const row of layout.rows.slice(rowIndex,rowIndex+rowSpan))for(const col of layout.columns.slice(columnIndex,columnIndex+colSpan))
      shade=Math.max(shade,local.get(`${row.id}/${col.id}`)??Math.max(row.shade??0,col.shade??0))
    return shade
  }
}
// A rectangular closure also covers merges touched by earlier expansion.
export function expandedSelection(layout:GridLayout,start:GridPoint,end:GridPoint=start) {
  const rows=new Map(layout.rows.map((r,i)=>[r.id,i])),cols=new Map(layout.columns.map((c,i)=>[c.id,i]))
  const bounds=(a:GridPoint,b:GridPoint)=>({top:Math.min(rows.get(a.row_id)??-1,rows.get(b.row_id)??-1),bottom:Math.max(rows.get(a.row_id)??-1,rows.get(b.row_id)??-1),left:Math.min(cols.get(a.column_id)??-1,cols.get(b.column_id)??-1),right:Math.max(cols.get(a.column_id)??-1,cols.get(b.column_id)??-1)})
  const box=bounds(start,end),merges=layout.merges.map(m=>bounds(m.start,m.end))
  if(box.top<0||box.left<0)return null
  let changed=true
  while(changed){changed=false;for(const m of merges){
    if(m.top>box.bottom||m.bottom<box.top||m.left>box.right||m.right<box.left)continue
    if(m.top<box.top||m.bottom>box.bottom||m.left<box.left||m.right>box.right){Object.assign(box,{top:Math.min(box.top,m.top),bottom:Math.max(box.bottom,m.bottom),left:Math.min(box.left,m.left),right:Math.max(box.right,m.right)});changed=true}
  }}
  return {...box,start:{row_id:layout.rows[box.top].id,column_id:layout.columns[box.left].id},end:{row_id:layout.rows[box.bottom].id,column_id:layout.columns[box.right].id}}
}
export function ShadePalette({value,local=false,disabled=false,onChoose}:{value?:number;local?:boolean;disabled?:boolean;onChoose:(shade:number)=>void}) {
  return <div className="shade-palette">{shades.slice(1).map((color,i)=><button key={i} type="button" aria-label={`淺灰 ${i+1}`} title={`淺灰 ${i+1}`} aria-pressed={value===i+1} disabled={disabled} style={{background:color}} onClick={()=>onChoose(i+1)}/>)}<button type="button" className="secondary" aria-label={local?'清除局部底色':'無底色'} title={local?'恢復排欄底色':'無底色'} aria-pressed={value===0} disabled={disabled} onClick={()=>onChoose(0)}><svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" fill="white" stroke="#777"/><path d="M4 20L20 4" stroke="#a33" strokeWidth="2"/></svg></button></div>
}
// SVG is foreground content, so PDF/print retains gray when background graphics are off.
export function PrintedShade({shade}:{shade:number}) {
  return shade>0?<svg className="print-cell-shade" data-print-shade={shade} aria-hidden="true" viewBox="0 0 1 1" preserveAspectRatio="none"><rect width="1" height="1" fill={shades[shade]}/></svg>:null
}

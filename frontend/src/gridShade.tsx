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
export function ShadePalette({value,disabled=false,onChoose}:{value?:number;local?:boolean;disabled?:boolean;onChoose:(shade:number)=>void}) {
  return <div className="shade-palette">{shades.map((color,shade)=><button key={shade} type="button" aria-label={shade?`淺灰 ${shade}`:'白色'} title={shade?`淺灰 ${shade}`:'白色'} aria-pressed={value===shade} disabled={disabled} style={{background:color}} onClick={()=>{if(value!==shade)onChoose(shade)}}/>)}</div>
}
// SVG is foreground content, so PDF/print retains gray when background graphics are off.
export function PrintedShade({shade}:{shade:number}) {
  return shade>0?<svg className="print-cell-shade" data-print-shade={shade} aria-hidden="true" viewBox="0 0 1 1" preserveAspectRatio="none"><rect width="1" height="1" fill={shades[shade]}/></svg>:null
}

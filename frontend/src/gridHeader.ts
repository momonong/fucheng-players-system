import type { GridLayout } from './types'
export const HEADER_ROW_ID='column-headers'
export const columnTitle=(c:GridLayout['columns'][number])=>c.title??(c.kind==='level'?`${c.level} 級`:'文字／備註')
export function selectionLayout(layout:GridLayout):GridLayout {
  const rows=[...layout.rows],index=rows.findIndex(r=>r.role==='body')
  rows.splice(index,0,{id:HEADER_ROW_ID,role:'header'})
  return {...layout,rows,merges:[...layout.merges,...(layout.header_merges??[]).map(m=>({id:m.id,start:{row_id:HEADER_ROW_ID,column_id:m.start_column_id},end:{row_id:HEADER_ROW_ID,column_id:m.end_column_id}}))]}
}
export function headerCells(layout:GridLayout){
  return layout.columns.map((column,index)=>{
    const merge=layout.header_merges?.find(m=>index>=layout.columns.findIndex(c=>c.id===m.start_column_id)&&index<=layout.columns.findIndex(c=>c.id===m.end_column_id))
    const left=merge?layout.columns.findIndex(c=>c.id===merge.start_column_id):index,right=merge?layout.columns.findIndex(c=>c.id===merge.end_column_id):index
    const columns=layout.columns.slice(left,right+1)
    return {column,index,merge,left,right,anchor:!merge||column.id===merge.start_column_id,title:merge?.title??columns.map(columnTitle).join(' '),shade:Math.max(...columns.map(c=>c.header_shade??c.shade??0))}
  })
}

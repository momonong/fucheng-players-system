import writeExcelFile, { type CellObject, type SheetData } from 'write-excel-file/browser'
import type { ArrangementRow, GridLayout } from './types'
import { legacyLayout, pointKey } from './LevelCardBoard'
import { headerCells } from './gridHeader'
import { shadeResolver, shades } from './gridShade'

export type ArrangementExport = { rows: ArrangementRow[]; layout: GridLayout | null; title: string; version: string }

// Export only the visible table fields from a frozen, complete arrangement.
// Explicit String/@ keeps names and text such as =1+1 literal, never formulas.
export async function exportArrangementExcel({rows,layout:known,title,version}:ArrangementExport) {
  const layout=known??legacyLayout(rows), people=new Map(rows.map(r=>[r.registration_id,r]))
  const source=new Map(layout.cells.map(c=>[pointKey(c),c])), shade=shadeResolver(layout)
  const cols=layout.columns.length, data:SheetData=[]
  const textCell=(value:string,extra:Partial<CellObject>={}):CellObject=>({value,type:String,format:'@',wrap:true,align:'center',alignVertical:'center',fontSize:11,...extra})
  for(const [i,value] of [title,version,`共 ${rows.length} 人 · 素＝本場素食${rows.some(r=>r.diet===null)?' · 未記錄餐食保持未知':''}${known?'':' · 舊版未保存格位，依級數與順位呈現，不代表當時分組'}`].entries()) {
    data.push([textCell(value,{columnSpan:cols,align:'left',fontWeight:i===0?'bold':undefined,fontSize:i===0?15:10,height:i===2&&!known?32:25}),...Array(cols-1).fill(null)])
  }
  const excelRows=new Map<string,number>()
  const gridStyle:Partial<CellObject>={borderColor:'#333333',borderStyle:'thin'}
  for(const [ri,row] of layout.rows.entries()) {
    if(row.role==='body'&&(ri===0||layout.rows[ri-1].role==='header')) {
      data.push(headerCells(layout).map(h=>h.anchor?textCell(h.title,{...gridStyle,columnSpan:h.right-h.left+1,fontWeight:'bold',height:30,backgroundColor:shades[h.shade]}):null))
    }
    excelRows.set(row.id,data.length)
    data.push(layout.columns.map((col,ci)=>{
      const cell=source.get(pointKey({row_id:row.id,column_id:col.id})), person=cell?.kind==='registration'?people.get(cell.registration_id):undefined
      const value=person?`${person.member_name}${person.diet==='vegetarian'?' [素]':''}${person.distinguishing_note?'\n'+person.distinguishing_note:''}`:cell?.kind==='text'?cell.text:''
      // CJK characters need roughly twice the Latin width; estimate enough height without shrinking text.
      const lines=value.split('\n').reduce((sum,line)=>sum+Math.max(1,Math.ceil([...line].reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0)/17)),0)
      return textCell(value,{...gridStyle,height:Math.min(409,Math.max(36,lines*15+8)),backgroundColor:shades[shade(ri,ci)]})
    }))
  }
  for(const merge of layout.merges) {
    const top=layout.rows.findIndex(r=>r.id===merge.start.row_id),bottom=layout.rows.findIndex(r=>r.id===merge.end.row_id)
    const left=layout.columns.findIndex(c=>c.id===merge.start.column_id),right=layout.columns.findIndex(c=>c.id===merge.end.column_id)
    const first=excelRows.get(merge.start.row_id)!,last=excelRows.get(merge.end.row_id)!
    const parts:string[]=[]
    for(let r=top;r<=bottom;r++)for(let c=left;c<=right;c++){
      const cell=source.get(pointKey({row_id:layout.rows[r].id,column_id:layout.columns[c].id}))
      if(cell?.kind==='text'&&cell.text)parts.push(cell.text)
      data[excelRows.get(layout.rows[r].id)!][c]=null
    }
    data[first][left]=textCell(parts.join(' '),{...gridStyle,columnSpan:right-left+1,rowSpan:last-first+1,backgroundColor:shades[shade(top,left,bottom-top+1,right-left+1)],height:40})
  }
  const fileName=`${title}-${version}`.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,100)+'.xlsx'
  await writeExcelFile(data,{sheet:'比賽安排',columns:layout.columns.map(()=>({width:20})),orientation:'landscape',showGridLines:false},{fontFamily:'Microsoft JhengHei',fontSize:11}).toFile(fileName)
}

import { useLayoutEffect, useState } from 'react'
import type { RefObject } from 'react'
import type { GridLayout, GridOperation } from './types'
import { GridAxisMenu, type AxisTarget, type AxisPanel } from './GridAxisMenu'
type Boundary={id:string;axis:'row'|'column';offset:number;label:string;operation:GridOperation}
export function GridInsertControls({layout,table,disabled,onOperate,stateToken}:{layout:GridLayout;table:RefObject<HTMLTableElement|null>;disabled:boolean;stateToken:string;onOperate:(op:GridOperation,token?:string)=>void}) {
  const [boundaries,setBoundaries]=useState<Boundary[]>([]),[active,setActive]=useState<string|null>(null)
  const [edge,setEdge]=useState<string|null>(null)
  const [targets,setTargets]=useState<AxisTarget[]>([]),[panel,setPanel]=useState<AxisPanel|null>(null)
  useLayoutEffect(()=>{
    const element=table.current;if(!element)return
    function measure(){
      if(!element)return
      const box=element.getBoundingClientRect(), found:Boundary[]=[], axes:AxisTarget[]=[]
      const rowElements=Array.from(element.querySelectorAll<HTMLElement>('tr[data-row-id]'))
      rowElements.forEach((row,i)=>found.push({id:`row-${i}`,axis:'row',offset:row.getBoundingClientRect().top-box.top,label:`在第 ${i+1} 列上方插列`,operation:{action:'insert_row',before_id:row.dataset.rowId!}}))
      rowElements.forEach((row,index)=>axes.push({axis:'row',id:row.dataset.rowId!,index,offset:row.getBoundingClientRect().top-box.top,size:row.getBoundingClientRect().height}))
      found.push({id:'row-end',axis:'row',offset:box.height,label:'在表格下方插列',operation:{action:'insert_row',before_id:null}})
      const head=element.querySelector<HTMLElement>('.grid-level-head')
      if(head){
        found.push({id:'header',axis:'row',offset:head.getBoundingClientRect().top-box.top,label:'在級數標題上方插入表頭列',operation:{action:'insert_header',before_id:null}})
        Array.from(element.querySelectorAll<HTMLElement>('col[data-column-id]')).forEach((col,i)=>found.push({id:`col-${i}`,axis:'column',offset:col.getBoundingClientRect().left-box.left,label:`在第 ${i+1} 欄左方插入文字欄`,operation:{action:'insert_column',before_id:layout.columns[i].id}}))
      }
      found.push({id:'col-end',axis:'column',offset:box.width,label:'在表格右方插入文字欄',operation:{action:'insert_column',before_id:null}})
      if(head)Array.from(element.querySelectorAll<HTMLElement>('col[data-column-id]')).forEach((col,index)=>axes.push({axis:'column',id:layout.columns[index].id,index,offset:col.getBoundingClientRect().left-box.left,size:col.getBoundingClientRect().width}))
      setBoundaries(found);setTargets(axes)
    }
    measure();const observer=new ResizeObserver(measure);observer.observe(element);window.addEventListener('resize',measure)
    return()=>{observer.disconnect();window.removeEventListener('resize',measure)}
  },[layout,table])
  function open(target:AxisTarget,element:HTMLElement){
    const box=element.getBoundingClientRect();setEdge(`${target.axis}/${target.id}`)
    setPanel({target,layout,token:stateToken,left:Math.max(8,box.right+4),top:Math.max(8,box.top),confirm:false})
  }
  const selected=targets.find(t=>`${t.axis}/${t.id}`===edge)
  return <><div className="grid-insert-controls" aria-label="表格邊界插入">{boundaries.map(b=>{
    const nearby=selected&&selected.axis===b.axis&&(Math.abs(b.offset-selected.offset)<2||Math.abs(b.offset-selected.offset-selected.size)<2)
    return <div key={b.id} className={`grid-boundary grid-boundary-${b.axis} ${active===b.id?'boundary-active':''} ${nearby?'edge-selected':''}`} style={b.axis==='row'?{top:b.offset}:{left:b.offset}}>
    <button type="button" disabled={disabled} aria-label={b.label} title={b.label} onMouseEnter={()=>setActive(b.id)} onMouseLeave={()=>setActive(null)} onFocus={()=>setActive(b.id)} onBlur={()=>setActive(null)} onPointerDown={()=>setActive(b.id)} onClick={()=>{onOperate(b.operation);setActive(null)}}>＋</button>
    {active===b.id&&<span className="boundary-line" aria-hidden="true"/>}
  </div>})}{targets.map(target=><button key={`${target.axis}/${target.id}`} className={`grid-axis-more grid-axis-${target.axis} ${edge===`${target.axis}/${target.id}`?'edge-selected':''}`} type="button" disabled={disabled} aria-label={`第 ${target.index+1} ${target.axis==='row'?'排':'直欄'}更多操作`} title="點選或右鍵：底色與刪除" style={target.axis==='row'?{top:target.offset+7,height:Math.max(24,target.size-14)}:{left:target.offset+14,width:Math.max(24,target.size-28)}} onClick={e=>open(target,e.currentTarget)} onContextMenu={e=>{e.preventDefault();if(!disabled)open(target,e.currentTarget)}}><span>⋯</span></button>)}
    {selected&&<div className={`axis-removal-preview axis-removal-${selected.axis}`} style={selected.axis==='row'?{top:selected.offset,height:selected.size}:{left:selected.offset,width:selected.size}}/>}
  </div>{panel&&<GridAxisMenu panel={panel} disabled={disabled} onPanel={value=>{setPanel(value);if(!value)setEdge(null)}} onOperate={onOperate}/>}</>
}

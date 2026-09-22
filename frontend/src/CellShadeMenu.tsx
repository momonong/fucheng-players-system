import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { GridPoint } from './types'
import { ShadePalette } from './gridShade'
export type CellShadePanel={start:GridPoint;end:GridPoint;token:string;left:number;top:number;value?:number}
export function CellShadeMenu({panel,disabled,onClose,onChoose}:{panel:CellShadePanel;disabled:boolean;onClose:()=>void;onChoose:(shade:number)=>void}) {
  const ref=useRef<HTMLDivElement>(null)
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null
    ref.current?.querySelector('button')?.focus()
    const outside=(e:PointerEvent)=>{if(!ref.current?.contains(e.target as Node))onClose()}
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();onClose()}}
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape)
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);previous?.focus({preventScroll:true})}
  },[])
  return createPortal(<div ref={ref} role="dialog" aria-label="儲存格底色" className="cell-shade-menu" style={{left:Math.max(8,Math.min(panel.left,window.innerWidth-238)),top:Math.max(8,Math.min(panel.top,window.innerHeight-115))}} onContextMenu={e=>e.preventDefault()}><strong>儲存格底色</strong><ShadePalette local value={panel.value} disabled={disabled} onChoose={onChoose}/><small>合併格會完整選取</small></div>,document.body)
}

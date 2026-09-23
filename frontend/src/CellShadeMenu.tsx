import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ShadePalette } from './gridShade'
export type CellShadePanel={left:number;top:number}
export function CellShadeMenu({panel,value,disabled,onClose,onChoose,children}:{panel:CellShadePanel;value?:number;disabled:boolean;onClose:()=>void;onChoose:(shade:number)=>void;children:ReactNode}) {
  const ref=useRef<HTMLDivElement>(null)
  useLayoutEffect(()=>{
    const previous=document.activeElement as HTMLElement|null
    const place=()=>{const el=ref.current;if(el){const rect=el.getBoundingClientRect();el.style.left=`${Math.max(8,Math.min(panel.left,innerWidth-rect.width-8))}px`;el.style.top=`${Math.max(8,Math.min(panel.top,innerHeight-rect.height-8))}px`}}
    place();ref.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({preventScroll:true})
    const outside=(e:PointerEvent)=>{const target=e.target;if(!(target instanceof Node))return;const element=target instanceof Element?target:target.parentElement;if(element?.closest('.grid-menu-trigger'))return;if(!ref.current?.contains(target))onClose()}
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();onClose()}}
    window.addEventListener('resize',place);document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape)
    return()=>{window.removeEventListener('resize',place);document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape);previous?.focus({preventScroll:true})}
  },[panel.left,panel.top])
  return createPortal(<div ref={ref} role="dialog" aria-label="儲存格操作" className="cell-shade-menu" style={{left:panel.left,top:panel.top}} onContextMenu={e=>e.preventDefault()}>
    <div className="cell-menu-colors" role="group" aria-label="表格底色"><strong>表格底色</strong><ShadePalette value={value} disabled={disabled} onChoose={onChoose}/></div>{children}
  </div>,document.body)
}

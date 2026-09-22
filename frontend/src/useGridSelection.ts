import { useEffect, useRef } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { GridPoint } from './types'

// Mouse selection owns only blank/text cells and the visible inset around a card.
// Touch remains native scrolling; its explicit range button uses two taps.
export function useGridSelection(enabled: boolean, select: (p: GridPoint, extend?: boolean) => void) {
  const latest = useRef({ enabled, select }); latest.current = { enabled, select }
  const gesture = useRef<{ pointer: number; x: number; y: number; active: boolean; element: HTMLElement } | null>(null)
  const suppress = useRef<number | null>(null)
  useEffect(() => {
    function down() { suppress.current = null }
    function move(e: PointerEvent) {
      const g = gesture.current
      if (!g || g.pointer !== e.pointerId || !latest.current.enabled) return
      if (Math.hypot(e.clientX-g.x,e.clientY-g.y)>4) g.active=true
      if (!g.active) return
      e.preventDefault()
      const td=document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-grid-cell]')
      if(td?.dataset.dropRow && td.dataset.dropColumn) latest.current.select({row_id:td.dataset.dropRow,column_id:td.dataset.dropColumn},true)
    }
    function finish() {
      const g=gesture.current; gesture.current=null
      if(g?.active) suppress.current=g.pointer
      if(g?.element.hasPointerCapture(g.pointer))g.element.releasePointerCapture(g.pointer)
    }
    function click(e: MouseEvent) {
      if(suppress.current===null || e.detail===0) return
      if(e instanceof PointerEvent && e.pointerId!==suppress.current)return
      suppress.current=null;e.preventDefault();e.stopImmediatePropagation()
    }
    function key(e: KeyboardEvent){if(e.key==='Escape')finish()}
    window.addEventListener('pointerdown',down,true);window.addEventListener('pointermove',move,{passive:false})
    window.addEventListener('pointerup',finish);window.addEventListener('pointercancel',finish);window.addEventListener('blur',finish)
    window.addEventListener('click',click,true);window.addEventListener('keydown',key)
    return()=>{finish();window.removeEventListener('pointerdown',down,true);window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',finish);window.removeEventListener('pointercancel',finish);window.removeEventListener('blur',finish);window.removeEventListener('click',click,true);window.removeEventListener('keydown',key)}
  },[])
  return (e:ReactPointerEvent<HTMLElement>,point:GridPoint)=>{
    if(!enabled||e.pointerType!=='mouse'||e.button!==0||(e.target as HTMLElement).closest('.cell-name,.cell-grip,input,textarea,.grid-inline-editor'))return
    latest.current.select(point,e.shiftKey)
    gesture.current={pointer:e.pointerId,x:e.clientX,y:e.clientY,active:false,element:e.currentTarget}
    e.currentTarget.setPointerCapture(e.pointerId)
  }
}

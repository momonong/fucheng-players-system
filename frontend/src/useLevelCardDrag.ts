import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

import type { GridPoint } from './types'

type Card = { id: string; name: string; note: string | null }
export type DropTarget = GridPoint & { mode:'swap'|'insert'|'move_empty'; side?:'before'|'after'; registrationId?:string; label:string }
type Drag = { card: Card; x: number; y: number; touch: boolean; width: number; height: number; target: DropTarget | null }
type Gesture = {
  card: Card; pointer: number; handle: HTMLElement; startX: number; startY: number
  x: number; y: number; active: boolean; touch: boolean; width: number; height: number; target: DropTarget | null; timer?: number
}

// Only the handle opts out of native touch scrolling. Cards and lane bodies still scroll.
export function useLevelCardDrag(onMove: (id: string, target: DropTarget) => void, enabled: boolean) {
  const [drag, setDrag] = useState<Drag | null>(null)
  const [holding, setHolding] = useState<string | null>(null)
  const gesture = useRef<Gesture | null>(null)
  const displayed = useRef<DropTarget | null>(null)
  useLayoutEffect(()=>{displayed.current=drag?.target??null},[drag])
  const latest = useRef({ onMove, enabled })
  latest.current = { onMove, enabled }
  // Only a completed/cancelled drag sequence owns this click. A new pointerdown
  // immediately ends that ownership, so a real subsequent click is never delayed.
  const dragClick = useRef<{ pointer: number; endedAt: number } | null>(null)

  useEffect(() => {
    function targetAt(current: Gesture): DropTarget | null {
      const target = document.elementFromPoint(current.x, current.y)?.closest<HTMLElement>('[data-drop-row]')
      if (!target || target.dataset.dropEnabled !== 'true') return null
      const point = {row_id:target.dataset.dropRow!,column_id:target.dataset.dropColumn!}
      const registrationId=target.dataset.dropRegistration
      if (registrationId === current.card.id) return null
      if (!registrationId) return {...point,mode:'move_empty',label:'移到空白格'}
      const box=target.getBoundingClientRect(), y=current.y-box.top, edge=box.height*.22
      const previous=current.target, same=previous?.row_id===point.row_id&&previous?.column_id===point.column_id
      let side:'before'|'after'|undefined=y<edge?'before':y>box.height-edge?'after':undefined
      // Four pixels of hysteresis within the same cell prevents boundary jitter.
      if(same) {
        if(previous.mode==='insert'&&previous.side==='before'&&y<edge+4)side='before'
        else if(previous.mode==='insert'&&previous.side==='after'&&y>box.height-edge-4)side='after'
        else if(previous.mode==='swap'&&y>=edge-4&&y<=box.height-edge+4)side=undefined
      }
      const name=target.dataset.dropName||'這位選手'
      return side?{...point,mode:'insert',side,registrationId,label:`插入 ${name} ${side==='before'?'上方':'下方'}`}:{...point,mode:'swap',registrationId,label:`與 ${name} 交換`}
    }
    function show(current: Gesture) {
      current.target=targetAt(current)
      setDrag({ card: current.card, x: current.x, y: current.y, touch: current.touch, width: current.width, height: current.height, target: current.target })
    }
    function clear(cancelledMovement = false) {
      const current = gesture.current
      if (current && (current.active || cancelledMovement)) dragClick.current = { pointer: current.pointer, endedAt: performance.now() }
      gesture.current = null
      if (current?.timer) window.clearTimeout(current.timer)
      if (current?.handle.hasPointerCapture(current.pointer)) current.handle.releasePointerCapture(current.pointer)
      setDrag(null); setHolding(null)
    }
    function move(event: PointerEvent) {
      const current = gesture.current
      if (!current || current.pointer !== event.pointerId) return
      current.x = event.clientX; current.y = event.clientY
      const distance = Math.hypot(current.x - current.startX, current.y - current.startY)
      if (!current.active) {
        if (current.touch && distance > 8) { clear(true); return }
        if (!current.touch && distance > 6) current.active = true
      }
      if (current.active) { if (event.cancelable) event.preventDefault(); show(current) }
    }
    function up(event: PointerEvent) {
      const current = gesture.current
      if (!current || current.pointer !== event.pointerId) return
      const target = displayed.current // Only a committed React preview may be submitted; not a pending frame.
      clear()
      if (!latest.current.enabled) return
      if (current.active && target !== null) latest.current.onMove(current.card.id, target)
    }
    function cancel(event: PointerEvent) { if (gesture.current?.pointer === event.pointerId) clear() }
    function pointerDown() { dragClick.current = null }
    function click(event: MouseEvent) {
      const completed = dragClick.current
      if (!completed) return
      // Keyboard/programmatic activation has no originating pointer gesture.
      if (event.detail === 0 && (!(event instanceof PointerEvent) || !event.pointerType)) return
      if (event instanceof PointerEvent && event.pointerId !== completed.pointer) return
      if (performance.now() - completed.endedAt > 1000) { dragClick.current = null; return }
      dragClick.current = null
      event.preventDefault(); event.stopImmediatePropagation()
    }
    const blur = () => clear()
    function key(event: KeyboardEvent) { if (event.key === 'Escape') clear() }
    let frame = 0
    function scroll() {
      const current = gesture.current
      if (current?.active) {
        if (!latest.current.enabled) clear()
        else {
          const lane = document.elementFromPoint(current.x, current.y)?.closest<HTMLElement>('.arrangement-table-scroll')
          const edgeSpeed = (position: number, start: number, end: number) => position < start + 35 ? -9 : position > end - 35 ? 9 : 0
          const rect = lane?.getBoundingClientRect()
          if (lane && rect) {
            lane.scrollLeft += edgeSpeed(current.x, rect.left, rect.right)
            lane.scrollTop += edgeSpeed(current.y, rect.top, rect.bottom)
          }
          const dy = edgeSpeed(current.y, 0, window.innerHeight)
          if (dy) window.scrollBy(0, dy)
          show(current)
        }
      }
      frame = requestAnimationFrame(scroll)
    }
    frame = requestAnimationFrame(scroll)
    window.addEventListener('pointerdown', pointerDown, true)
    window.addEventListener('click', click, true)
    window.addEventListener('lostpointercapture', cancel)
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    window.addEventListener('keydown', key)
    window.addEventListener('blur', blur)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('pointerdown', pointerDown, true)
      window.removeEventListener('click', click, true)
      window.removeEventListener('lostpointercapture', cancel)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      window.removeEventListener('keydown', key)
      window.removeEventListener('blur', blur)
      const current = gesture.current
      if (current?.timer) window.clearTimeout(current.timer)
      if (current?.handle.hasPointerCapture(current.pointer)) current.handle.releasePointerCapture(current.pointer)
      gesture.current = null
    }
  }, [])

  function start(event: ReactPointerEvent<HTMLButtonElement>, card: Card) {
    if (!latest.current.enabled || event.button !== 0 || gesture.current) return
    const box = (event.currentTarget.closest('.arrangement-cell') ?? event.currentTarget).getBoundingClientRect()
    const current: Gesture = {
      card, pointer: event.pointerId, handle: event.currentTarget,
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY,
      active: false, target:null, touch: event.pointerType === 'touch', width: box.width, height: box.height,
    }
    gesture.current = current
    event.currentTarget.setPointerCapture(event.pointerId)
    if (current.touch) {
      setHolding(card.id)
      current.timer = window.setTimeout(() => {
        if (gesture.current !== current || !latest.current.enabled) return
        current.active = true; setHolding(null)
        setDrag({ card, x: current.x, y: current.y, touch: current.touch, width: current.width, height: current.height, target: null })
      }, 350)
    }
  }
  return { drag, holding, start }
}

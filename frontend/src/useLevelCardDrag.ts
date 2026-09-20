import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

type Card = { id: string; name: string }
type Drag = { card: Card; x: number; y: number; target: number | null }
type Gesture = {
  card: Card; pointer: number; handle: HTMLElement; startX: number; startY: number
  x: number; y: number; active: boolean; touch: boolean; timer?: number
}

// Only the handle opts out of native touch scrolling. Cards and lane bodies still scroll.
export function useLevelCardDrag(onMove: (id: string, level: number) => void, onPick: (id: string) => void, enabled: boolean) {
  const [drag, setDrag] = useState<Drag | null>(null)
  const [holding, setHolding] = useState<string | null>(null)
  const gesture = useRef<Gesture | null>(null)
  const latest = useRef({ onMove, onPick, enabled })
  latest.current = { onMove, onPick, enabled }

  useEffect(() => {
    function targetAt(x: number, y: number) {
      const target = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-drop-level]')
      return target && target.dataset.dropEnabled === 'true' ? Number(target.dataset.dropLevel) : null
    }
    function show(current: Gesture) {
      setDrag({ card: current.card, x: current.x, y: current.y, target: targetAt(current.x, current.y) })
    }
    function clear() {
      const current = gesture.current
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
        if (current.touch && distance > 8) { clear(); return }
        if (!current.touch && distance > 6) current.active = true
      }
      if (current.active) { if (event.cancelable) event.preventDefault(); show(current) }
    }
    function up(event: PointerEvent) {
      const current = gesture.current
      if (!current || current.pointer !== event.pointerId) return
      const target = targetAt(event.clientX, event.clientY)
      clear()
      if (!latest.current.enabled) return
      if (current.active && target !== null) latest.current.onMove(current.card.id, target)
      else if (!current.active) latest.current.onPick(current.card.id)
    }
    function cancel(event: PointerEvent) { if (gesture.current?.pointer === event.pointerId) clear() }
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
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    window.addEventListener('keydown', key)
    window.addEventListener('blur', clear)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      window.removeEventListener('keydown', key)
      window.removeEventListener('blur', clear)
      const current = gesture.current
      if (current?.timer) window.clearTimeout(current.timer)
      if (current?.handle.hasPointerCapture(current.pointer)) current.handle.releasePointerCapture(current.pointer)
      gesture.current = null
    }
  }, [])

  function start(event: ReactPointerEvent<HTMLButtonElement>, card: Card) {
    if (!latest.current.enabled || event.button !== 0 || gesture.current) return
    const current: Gesture = {
      card, pointer: event.pointerId, handle: event.currentTarget,
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY,
      active: false, touch: event.pointerType === 'touch',
    }
    gesture.current = current
    event.currentTarget.setPointerCapture(event.pointerId)
    if (current.touch) {
      setHolding(card.id)
      current.timer = window.setTimeout(() => {
        if (gesture.current !== current || !latest.current.enabled) return
        current.active = true; setHolding(null)
        setDrag({ card, x: current.x, y: current.y, target: null })
      }, 350)
    }
  }
  return { drag, holding, start }
}

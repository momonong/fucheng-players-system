import { useEffect, useRef } from 'react'

// Callers own their result/error state and write locks. This hook only schedules
// reads and never retries a mutation. Interval reads do not overlap; a fresh
// wake-up read may supersede an older normal read.
export function useVisibleRefresh(refresh: (fresh: boolean) => Promise<unknown>, milliseconds: number, enabled = true) {
  const latest = useRef(refresh)
  latest.current = refresh
  useEffect(() => {
    if (!enabled) return
    let running = false, forcing = false, active = true, sequence = 0
    const run = (fresh = false) => {
      if (!active || (running && (!fresh || forcing)) || document.visibilityState !== 'visible') return
      running = true; forcing = fresh
      const current = ++sequence
      void latest.current(fresh).catch(() => { /* the caller presents the read error */ }).finally(() => { if (current === sequence) { running = false; forcing = false } })
    }
    const wake = () => run(true)
    const timer = window.setInterval(() => run(), milliseconds)
    window.addEventListener('focus', wake)
    window.addEventListener('online', wake)
    document.addEventListener('visibilitychange', wake)
    return () => {
      active = false; window.clearInterval(timer)
      window.removeEventListener('focus', wake); window.removeEventListener('online', wake)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [milliseconds, enabled])
}

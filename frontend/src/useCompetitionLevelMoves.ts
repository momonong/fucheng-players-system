import { useEffect, useRef, useState } from 'react'
import { updateRegistrationLevel } from './api'
import type { CompetitionDetail, CompetitionRegistration } from './types'

export type LevelMove = {
  base: CompetitionRegistration; level: number; reason: string; requestId: string
  status: 'saving' | 'unknown' | 'conflict' | 'rejected'; error: string; isUndo: boolean
}
type Undo = { before: number; after: number; version: number }

// Lives above navigation: immutable requests and late responses stay with their own row.
export function useCompetitionLevelMoves() {
  const [moves, setMoves] = useState<Record<string, LevelMove>>({})
  const movesRef = useRef(moves)
  const [canonical, setCanonical] = useState<Record<string, CompetitionRegistration>>({})
  const [undos, setUndos] = useState<Record<string, Undo>>({})
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [notices, setNotices] = useState<Record<string, string>>({})
  const inFlight = useRef(new Set<string>())
  function put(id: string, value: LevelMove | null) {
    const next = { ...movesRef.current }
    if (value) next[id] = value
    else delete next[id]
    movesRef.current = next; setMoves(next)
  }
  function notice(id: string, value: string) { setNotices(current => ({ ...current, [id]: value })) }
  useEffect(() => {
    if (!Object.keys(moves).length) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [moves])
  async function send(operation: LevelMove) {
    const id = operation.base.id
    if (inFlight.current.has(id)) return
    inFlight.current.add(id)
    put(id, { ...operation, status: 'saving', error: '' })
    try {
      const response = await updateRegistrationLevel(operation.base, operation.level, operation.reason, operation.requestId)
      // Idempotency replay returns the current row, not a frozen original response.
      setCanonical(current => !current[id] || response.version >= current[id].version ? { ...current, [id]: response } : current)
      const exact = response.status === 'confirmed' && response.competition_level === operation.level && response.version === operation.base.version + 1
      setUndos(current => {
        const next = { ...current }
        if (exact && !operation.isUndo) next[id] = { before: operation.base.competition_level, after: response.competition_level, version: response.version }
        else delete next[id]
        return next
      })
      put(id, null)
      notice(operation.base.competition_id, exact
        ? `${response.member_name}：${operation.base.competition_level} → ${response.competition_level} 級，已自動儲存${operation.isUndo ? '（反向異動已記錄）' : ''}`
        : `${response.member_name}：已確認這次操作，但最新紀錄已變更。目前 ${response.competition_level} 級／版本 ${response.version}／${response.status === 'confirmed' ? '正取' : response.status === 'cancelled' ? '已取消' : '候補'}，請核對。`)
    } catch (error) {
      const status = (error as Error & { status?: number }).status
      put(id, { ...operation, status: status === 409 ? 'conflict' : !status || status >= 500 ? 'unknown' : 'rejected', error: (error as Error).message })
      notice(operation.base.competition_id, `${operation.base.member_name} 的移動尚未確認儲存，請處理未完成移動。`)
    } finally { inFlight.current.delete(id) }
  }
  function move(row: CompetitionRegistration, level: number, isUndo = false) {
    const reason = reasons[row.competition_id]?.trim()
    if (!reason || movesRef.current[row.id] || row.status !== 'confirmed' || row.competition_level === level) return
    const undo = undos[row.id]
    if (isUndo && (!undo || undo.version !== row.version || undo.after !== row.competition_level)) {
      notice(row.competition_id, '這筆已有其他更新，不能沿用舊撤回基準，請重新核對。')
      return
    }
    void send({ base: { ...row }, level, reason, requestId: crypto.randomUUID(), status: 'saving', error: '', isUndo })
  }
  function retry(id: string) { const pending = movesRef.current[id]; if (pending?.status === 'unknown') void send(pending) }
  function discard(id: string) {
    const pending = movesRef.current[id]
    if (pending && ['conflict', 'rejected'].includes(pending.status)) {
      put(id, null)
      notice(pending.base.competition_id, '已放棄未完成移動；沒有送出反向異動。請核對最新名單。')
    }
  }
  function reconcile(detail: CompetitionDetail): CompetitionDetail {
    const registrations = detail.registrations.map(row => canonical[row.id]?.version > row.version ? canonical[row.id] : row)
    const summary = { ...detail.competition.summary, confirmed: 0, waitlisted: 0, cancelled: 0,
      diet_counts: { unset: 0, omnivore: 0, vegetarian: 0 }, level_counts: {} as Record<string, number>, competition_level_counts: {} as Record<string, number> }
    for (const row of registrations) {
      summary[row.status]++
      if (row.status === 'confirmed') {
        summary.diet_counts[row.diet]++
        summary.level_counts[row.hard_level_snapshot] = (summary.level_counts[row.hard_level_snapshot] ?? 0) + 1
        summary.competition_level_counts[row.competition_level] = (summary.competition_level_counts[row.competition_level] ?? 0) + 1
      }
    }
    summary.remaining = Math.max(detail.competition.capacity - summary.confirmed, 0)
    summary.pending_promotions = Math.min(summary.remaining, summary.waitlisted)
    return { registrations, competition: { ...detail.competition, summary } }
  }
  return { moves, reasons, notices, undos, canonical, move, retry, discard, reconcile,
    setReason: (id: string, reason: string) => setReasons(current => ({ ...current, [id]: reason })) }
}

export type LevelMovesController = ReturnType<typeof useCompetitionLevelMoves>

import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { ArrangementRow, ArrangementSave, ArrangementState, ArrangementVersion } from './types'

export type PendingMove = { competitionId: string; row: ArrangementRow; level: number; requestId: string; status: 'saving' | 'unknown' | 'rejected' | 'refresh'; error: string; confirmedVersion?: number }
type PendingSave = { payload: ArrangementSave; status: 'saving' | 'unknown' | 'rejected' | 'refresh'; error: string; receipt?: ArrangementVersion }
type Metadata = { label: string; editor_label: string; note: string }
type Workspace = { state?: ArrangementState; loading: boolean; verified: boolean; error: string; notice: string; save?: PendingSave; draft?: Metadata }
const empty = (): Workspace => ({ loading: false, verified: false, error: '', notice: '' })

// The parent owns these records, so switching scenes never retargets an in-flight response.
export function useArrangementWorkspace() {
  const [workspaces, setWorkspaces] = useState<Record<string, Workspace>>({})
  const records = useRef(workspaces)
  const [moves, setMoves] = useState<Record<string, PendingMove>>({})
  const pending = useRef(moves)
  const generations = useRef<Record<string, number>>({})
  const flight = useRef(new Set<string>())
  const bigFlight = useRef(new Set<string>())
  function patch(id: string, change: Partial<Workspace>) {
    records.current = { ...records.current, [id]: { ...(records.current[id] ?? empty()), ...change } }
    setWorkspaces(records.current)
  }
  function putMove(id: string, value?: PendingMove) {
    const next = { ...pending.current }; if (value) next[id] = value; else delete next[id]
    pending.current = next; setMoves(next)
  }
  function invalidate(id: string) { generations.current[id] = (generations.current[id] ?? 0) + 1 }
  async function load(id: string, initialize = false) {
    invalidate(id); const generation = generations.current[id]
    patch(id, { loading: true, verified: false, error: '' })
    try {
      let value = await api.arrangement(id)
      if (initialize && !value.latest) value = await api.initializeArrangement(id)
      if (generation !== generations.current[id]) return
      const previous = records.current[id]
      // An old receipt is never used as the current baseline; this is a fresh, atomic state read.
      if ((previous?.state?.latest?.sequence ?? -1) > (value.latest?.sequence ?? -1)) throw new Error('保存版本狀態較舊，請重新讀取')
      const receipt = previous?.save?.receipt
      const diverged = receipt && (value.latest?.id !== receipt.id || JSON.stringify(value.rows) !== JSON.stringify(receipt.rows))
      patch(id, { state: value, loading: false, verified: true,
        ...(receipt ? { save: undefined, draft: undefined, notice: diverged ? `已確認「${receipt.label}」保存；其後已有其他異動，已載入目前安排，請核對。` : `已保存「${receipt.label}」` } : {}) })
      for (const [key, operation] of Object.entries(pending.current)) {
        const row = value.rows.find(item => item.registration_id === key)
        if (operation.competitionId === id && operation.status === 'refresh' && (!row || row.version >= (operation.confirmedVersion ?? 0))) putMove(key)
      }
    } catch (error) {
      if (generation === generations.current[id]) patch(id, { loading: false, verified: false, error: (error as Error).message })
    }
  }
  function blocked(id: string) { return !!records.current[id]?.save }
  async function sendMove(operation: PendingMove) {
    const key = operation.row.registration_id, id = operation.competitionId
    if (flight.current.has(key) || blocked(id)) return
    flight.current.add(key); invalidate(id)
    putMove(key, { ...operation, status: 'saving', error: '' })
    patch(id, { verified: false, loading: false, notice: '' })
    try {
      const result = await api.updateRegistrationLevel({ id: key, version: operation.row.version }, operation.level, null, operation.requestId)
      putMove(key, { ...operation, level: result.competition_level, status: 'refresh', confirmedVersion: result.version, error: '' })
      const canonical = result.status !== 'confirmed' || result.competition_level !== operation.level || result.version !== operation.row.version + 1
      patch(id, { notice: canonical ? '已確認這次移動；紀錄其後已有異動，正在讀取目前安排。' : '已自動儲存' })
      await load(id)
    } catch (error) {
      const status = (error as Error & { status?: number }).status
      putMove(key, { ...operation, status: !status || status >= 500 ? 'unknown' : 'rejected', error: (error as Error).message })
    } finally { flight.current.delete(key) }
  }
  function move(id: string, row: ArrangementRow, level: number) {
    if (blocked(id) || pending.current[row.registration_id] || row.competition_level === level) return
    void sendMove({ competitionId: id, row: { ...row }, level, requestId: crypto.randomUUID(), status: 'saving', error: '' })
  }
  function retryMove(key: string) { const operation = pending.current[key]; if (operation?.status === 'unknown') void sendMove(operation); else if (operation?.status === 'refresh') void load(operation.competitionId) }
  function discardMove(key: string) {
    const operation = pending.current[key]
    if (operation?.status === 'rejected') { putMove(key); void load(operation.competitionId) }
  }
  async function sendSave(id: string, operation: PendingSave) {
    if (bigFlight.current.has(id)) return
    bigFlight.current.add(id); invalidate(id)
    patch(id, { save: { ...operation, status: 'saving', error: '' }, verified: false, loading: false })
    try {
      const receipt = await api.saveArrangement(id, operation.payload)
      patch(id, { save: { ...operation, status: 'refresh', receipt, error: '' } })
      await load(id)
    } catch (error) {
      const status = (error as Error & { status?: number }).status
      patch(id, { save: { ...operation, status: !status || status >= 500 ? 'unknown' : 'rejected', error: (error as Error).message } })
    } finally { bigFlight.current.delete(id) }
  }
  function save(id: string, metadata: { label: string; editor_label: string; note: string }) {
    const current = records.current[id]
    if (!current?.verified || !current.state?.latest || current.save || Object.values(pending.current).some(row => row.competitionId === id)) return
    void sendSave(id, { payload: { ...metadata, request_id: crypto.randomUUID(), state_token: current.state.state_token, base_version_id: current.state.latest.id }, status: 'saving', error: '' })
  }
  function retrySave(id: string) { const operation = records.current[id]?.save; if (operation?.status === 'unknown') void sendSave(id, operation); else if (operation?.status === 'refresh') void load(id) }
  function discardSave(id: string) { if (records.current[id]?.save?.status === 'rejected') { patch(id, { save: undefined }); void load(id) } }
  const unfinished = Object.keys(moves).length > 0 || Object.values(workspaces).some(value => !!value.save)
  useEffect(() => {
    if (!unfinished) return
    const protect = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect)
  }, [unfinished])
  return { workspaces, moves, load, move, retryMove, discardMove, save, retrySave, discardSave, setDraft: (id: string, draft: Metadata) => patch(id, { draft }) }
}
export type ArrangementController = ReturnType<typeof useArrangementWorkspace>

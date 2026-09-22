import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { ArrangementSave, ArrangementState, ArrangementVersion, GridOperation, GridRequest, GridReceipt } from './types'

type Status = 'saving' | 'unknown' | 'rejected' | 'refresh'
type PendingGrid = { payload: GridRequest; status: Status; error: string; receipt?: GridReceipt }
type PendingSave = { payload: ArrangementSave; status: Status; error: string; receipt?: ArrangementVersion }
type Metadata = { label: string; editor_label: string; note: string }
type Workspace = { undoStack?:string[]; undoToken?:string; confirmedGrid?: {request_id:string;action:GridOperation['action']}; state?: ArrangementState; loading: boolean; verified: boolean; error: string; notice: string; save?: PendingSave; operation?: PendingGrid; draft?: Metadata; texts?: Record<string, string> }
const empty = (): Workspace => ({ loading: false, verified: false, error: '', notice: '' })

export function useArrangementWorkspace() {
  const [workspaces, setWorkspaces] = useState<Record<string, Workspace>>({})
  const records = useRef(workspaces)
  const generations = useRef<Record<string, number>>({})
  const flights = useRef(new Set<string>())
  function patch(id: string, change: Partial<Workspace>) {
    records.current = { ...records.current, [id]: { ...(records.current[id] ?? empty()), ...change } }
    setWorkspaces(records.current)
  }
  function invalidate(id: string) { generations.current[id] = (generations.current[id] ?? 0) + 1 }
  async function load(id: string, initialize = false) {
    invalidate(id); const generation = generations.current[id]
    patch(id, { loading: true, verified: false, error: '' })
    try {
      let value = await api.arrangement(id)
      if (initialize && value.editable && (!value.latest || !value.layout)) value = await api.initializeArrangement(id)
      if (generation !== generations.current[id]) return
      const previous = records.current[id]
      if ((previous?.state?.latest?.sequence ?? -1) > (value.latest?.sequence ?? -1) || (previous?.state?.layout_revision ?? 0) > value.layout_revision) throw new Error('安排狀態較舊，請重新讀取')
      const receipt = previous?.save?.receipt
      const gridReceipt = previous?.operation?.receipt
      if (gridReceipt && value.layout_revision < gridReceipt.revision) throw new Error('尚未讀到已保存的位置，請重新讀取')
      const diverged = receipt && (value.latest?.id !== receipt.id || JSON.stringify(value.layout) !== JSON.stringify(receipt.layout) || JSON.stringify(value.rows) !== JSON.stringify(receipt.rows))
      const textOp = gridReceipt?.operation
      const texts = { ...previous?.texts }
      if (textOp?.action === 'text' || textOp?.action === 'column_title') {
        const key = textOp.action === 'text' ? `${textOp.target.row_id}/${textOp.target.column_id}` : `column/${textOp.column_id}`
        if (texts[key] === textOp.text) delete texts[key]
      }
      if(value.layout && (!previous?.operation || gridReceipt)) {
        const rowIds=new Set(value.layout.rows.map(r=>r.id)), colIds=new Set(value.layout.columns.map(c=>c.id))
        for(const key of Object.keys(texts)) {
          const [row,col]=key.split('/')
          if(row==='column'?!colIds.has(col):!rowIds.has(row)||!colIds.has(col))delete texts[key]
        }
      }
      let undoStack=previous?.undoStack??[],undoToken=previous?.undoToken
      if(receipt){undoStack=[];undoToken=undefined}
      else if(gridReceipt){
        if(gridReceipt.state_token===value.state_token){
          if(gridReceipt.operation.action==='undo')undoStack=undoStack.at(-1)===gridReceipt.operation.target_request_id?undoStack.slice(0,-1):[]
          else undoStack=[...undoStack,gridReceipt.request_id]
          if(undoStack.at(-1)!==gridReceipt.undo_head)undoStack=[]
          undoToken=value.state_token
        }else {undoStack=[];undoToken=undefined}
      }else if(!previous?.operation&&undoToken&&undoToken!==value.state_token){undoStack=[];undoToken=undefined}
      patch(id, { undoStack,undoToken,texts, state: value, loading: false, verified: true,
        ...(gridReceipt ? { operation: undefined, confirmedGrid:{request_id:gridReceipt.request_id,action:gridReceipt.operation.action}, notice: value.layout_revision > gridReceipt.revision ? '已確認原操作；其後另有異動，已載入目前安排。' : '已自動儲存' } : {}),
        ...(receipt ? { save: undefined, draft: undefined, notice: diverged ? `已確認「${receipt.label}」保存；其後另有異動，已載入目前安排。` : `已保存「${receipt.label}」` } : {}) })
    } catch (error) {
      if (generation === generations.current[id]) patch(id, { loading: false, verified: false, error: (error as Error).message })
    }
  }
  const statusOf = (error: unknown): Status => { const status = (error as Error & { status?: number }).status; return !status || status >= 500 ? 'unknown' : 'rejected' }
  async function sendOperation(id: string, operation: PendingGrid) {
    if (flights.current.has(id)) return
    flights.current.add(id); invalidate(id)
    patch(id, { operation: { ...operation, status: 'saving', error: '' }, verified: false, loading: false, notice: '' })
    try {
      const receipt = await api.mutateGrid(id, operation.payload)
      patch(id, { operation: { ...operation, status: 'refresh', receipt, error: '' } })
      await load(id)
    } catch (error) { patch(id, { operation: { ...operation, status: statusOf(error), error: (error as Error).message } }) }
    finally { flights.current.delete(id) }
  }
  function operate(id: string, operation: GridOperation, expectedToken?: string) {
    const current = records.current[id]
    if (!current?.verified || !current.state?.layout || !current.state.editable || current.save || current.operation) return
    void sendOperation(id, { payload: { request_id: crypto.randomUUID(), state_token: expectedToken ?? current.state.state_token, operation }, status: 'saving', error: '' })
  }
  function undo(id:string){
    const current=records.current[id],target=current?.undoStack?.at(-1)
    if(!target||current?.undoToken!==current.state?.state_token)return
    operate(id,{action:'undo',target_request_id:target},current.undoToken)
  }
  function retryOperation(id: string) { const op = records.current[id]?.operation; if (op?.status === 'unknown') void sendOperation(id, op); else if (op?.status === 'refresh') void load(id) }
  function discardOperation(id: string) { if (records.current[id]?.operation?.status === 'rejected') { patch(id, { operation: undefined }); void load(id) } }
  async function sendSave(id: string, operation: PendingSave) {
    if (flights.current.has(id)) return
    flights.current.add(id); invalidate(id)
    patch(id, { save: { ...operation, status: 'saving', error: '' }, verified: false, loading: false })
    try {
      const receipt = await api.saveArrangement(id, operation.payload)
      patch(id, { save: { ...operation, status: 'refresh', receipt, error: '' } })
      await load(id)
    } catch (error) { patch(id, { save: { ...operation, status: statusOf(error), error: (error as Error).message } }) }
    finally { flights.current.delete(id) }
  }
  function save(id: string, metadata: Metadata) {
    const current = records.current[id]
    if (!current?.verified || !current.state?.latest || current.save || current.operation) return
    void sendSave(id, { payload: { ...metadata, request_id: crypto.randomUUID(), state_token: current.state.state_token, base_version_id: current.state.latest.id }, status: 'saving', error: '' })
  }
  function retrySave(id: string) { const op = records.current[id]?.save; if (op?.status === 'unknown') void sendSave(id, op); else if (op?.status === 'refresh') void load(id) }
  function discardSave(id: string) { if (records.current[id]?.save?.status === 'rejected') { patch(id, { save: undefined }); void load(id) } }
  const unfinished = Object.values(workspaces).some(value => !!value.save || !!value.operation)
  useEffect(() => {
    if (!unfinished) return
    const protect = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect)
  }, [unfinished])
  return { workspaces, load, operate, undo, retryOperation, discardOperation, save, retrySave, discardSave, setDraft: (id: string, draft: Metadata) => patch(id, { draft }), setTextDraft: (id: string, key: string, text: string) => patch(id, { texts: { ...records.current[id]?.texts, [key]: text } }) }
}
export type ArrangementController = ReturnType<typeof useArrangementWorkspace>

import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { ArrangementSave, ArrangementState, ArrangementVersion, GridOperation, GridRequest, GridReceipt } from './types'

type Status = 'saving' | 'unknown' | 'rejected' | 'refresh'
type PendingGrid = { payload: GridRequest; status: Status; error: string; receipt?: GridReceipt }
type PendingSave = { payload: ArrangementSave; status: Status; error: string; receipt?: ArrangementVersion }
type Metadata = { label: string; editor_label: string; note: string }
type Workspace = { undoStack?:string[]; redoStack?:string[]; undoToken?:string; confirmedGrid?: {request_id:string;action:GridOperation['action']}; state?: ArrangementState; loading: boolean; verified: boolean; error: string; notice: string; save?: PendingSave; operation?: PendingGrid; draft?: Metadata; texts?: Record<string, string> }
const empty = (): Workspace => ({ loading: false, verified: false, error: '', notice: '' })

const validLayout=(layout:GridReceipt['layout']|null|undefined)=>!!layout&&Array.isArray(layout.rows)&&Array.isArray(layout.columns)&&Array.isArray(layout.cells)&&Array.isArray(layout.merges)

export function useArrangementWorkspace(username:string) {
  const [workspaces, setWorkspaces] = useState<Record<string, Workspace>>({})
  const records = useRef(workspaces)
  const generations = useRef<Record<string, number>>({})
  const flights = useRef(new Set<string>())
  const recovering = useRef(new Set<string>())
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
      const validate=()=>{if(!value||!Array.isArray(value.rows)||!Array.isArray(value.versions)||typeof value.state_token!=='string'||!Number.isInteger(value.layout_revision)||(value.layout!==null&&!validLayout(value.layout)))throw new Error('安排資料不完整，請重新讀取。')}
      validate()
      if (initialize && value.editable && (!value.latest || !value.layout)) value = await api.initializeArrangement(id)
      validate()
      if (generation !== generations.current[id]) return
      const previous = records.current[id]
      if ((previous?.state?.latest?.sequence ?? -1) > (value.latest?.sequence ?? -1) || (previous?.state?.layout_revision ?? 0) > value.layout_revision) throw new Error('安排狀態較舊，請重新讀取')
      const receipt = previous?.save?.receipt
      const gridReceipt = previous?.operation?.receipt
      if (gridReceipt && value.layout_revision < gridReceipt.revision) throw new Error('尚未讀到已保存的位置，請重新讀取')
      const diverged = receipt && (value.latest?.id !== receipt.id || JSON.stringify(value.layout) !== JSON.stringify(receipt.layout) || JSON.stringify(value.rows) !== JSON.stringify(receipt.rows))
      const textOp = gridReceipt?.operation
      const texts = { ...previous?.texts }
      if (textOp?.action === 'text' || textOp?.action === 'column_title' || textOp?.action === 'header_text') {
        const key = textOp.action === 'header_text' ? `header/${textOp.merge_id}` : textOp.action === 'text' ? `${textOp.target.row_id}/${textOp.target.column_id}` : `column/${textOp.column_id}`
        if (texts[key] === textOp.text) delete texts[key]
      }
      if(value.layout && (!previous?.operation || gridReceipt)) {
        const rowIds=new Set(value.layout.rows.map(r=>r.id)), colIds=new Set(value.layout.columns.map(c=>c.id))
        for(const key of Object.keys(texts)) {
          const [row,col]=key.split('/')
          if(row==='header'?!value.layout.header_merges?.some(m=>m.id===col):row==='column'?!colIds.has(col):!rowIds.has(row)||!colIds.has(col))delete texts[key]
        }
      }
      let undoStack=previous?.undoStack??[],redoStack=previous?.redoStack??[],undoToken=previous?.undoToken
      if(receipt){undoStack=[];redoStack=[];undoToken=undefined}
      else if(gridReceipt){
        if(gridReceipt.state_token===value.state_token){
          if(gridReceipt.operation.action==='undo'){
            const target=gridReceipt.operation.target_request_id
            undoStack=undoStack.at(-1)===target?undoStack.slice(0,-1):[]
            redoStack=[...redoStack,target]
          }else if(gridReceipt.operation.action==='redo'){
            const target=gridReceipt.operation.target_request_id
            redoStack=redoStack.at(-1)===target?redoStack.slice(0,-1):[]
            undoStack=[...undoStack,target]
          }else {undoStack=[...undoStack,gridReceipt.request_id];redoStack=[]}
          if(undoStack.at(-1)!==gridReceipt.undo_head)undoStack=[]
          if(redoStack.at(-1)!==gridReceipt.redo_head)redoStack=[]
          undoToken=value.state_token
        }else {undoStack=[];redoStack=[];undoToken=undefined}
      }else if(!previous?.operation&&undoToken&&undoToken!==value.state_token){undoStack=[];redoStack=[];undoToken=undefined}
      patch(id, { undoStack,redoStack,undoToken,texts, state: value, loading: false, verified: true,
        ...(gridReceipt ? { operation: undefined, confirmedGrid:{request_id:gridReceipt.request_id,action:gridReceipt.operation.action}, notice: value.layout_revision > gridReceipt.revision ? '已確認原操作；其後另有異動，已載入目前安排。' : '已自動儲存' } : {}),
        ...(receipt ? { save: undefined, draft: undefined, notice: diverged ? `已確認「${receipt.label}」保存；其後另有異動，已載入目前安排。` : `已保存「${receipt.label}」` } : {}) })
    } catch (error) {
      if (generation === generations.current[id]) patch(id, { loading: false, verified: false, error: (error as Error).message })
    }
  }
  const statusOf = (error: unknown, previous?:Status): Status => { const status = (error as Error & { status?: number }).status; return !status || status >= 500 || (previous==='unknown'&&(status===401||status===403)) ? 'unknown' : 'rejected' }
  async function sendOperation(id: string, operation: PendingGrid) {
    if (flights.current.has(id)) return
    flights.current.add(id); invalidate(id)
    patch(id, { operation: { ...operation, status: 'saving', error: '' }, verified: false, loading: false, notice: '' })
    try {
      const receipt = await api.mutateGrid(id, operation.payload)
      const received=receipt?.operation as unknown as Record<string,unknown>|undefined
      const matches=received&&Object.entries(operation.payload.operation).every(([key,value])=>{
        const actual=received[key]
        return value&&typeof value==='object'?actual&&typeof actual==='object'&&Object.entries(value).every(([k,v])=>(actual as Record<string,unknown>)[k]===v):actual===value
      })
      if(!receipt||receipt.request_id!==operation.payload.request_id||receipt.competition_id!==id||!Number.isInteger(receipt.revision)||receipt.revision<0||!(receipt.undo_head===null||typeof receipt.undo_head==='string')||!(receipt.redo_head===null||typeof receipt.redo_head==='string')||!matches||!validLayout(receipt.layout))throw new Error('操作回執不完整或不符，結果尚未確認；請原樣重試。')
      patch(id, { operation: { ...operation, status: 'refresh', receipt, error: '' } })
      await load(id)
    } catch (error) {
      // Only this exact server rejection guarantees no mutation. Unknown requests
      // retain their original identity; all other validation/conflict errors keep recovery.
      if(operation.status!=='unknown'&&(error as Error & {status?:number}).status===422&&(error as Error).message==='安排沒有變更'){
        patch(id,{operation:undefined,notice:'安排沒有變更；已重新讀取目前安排。'})
        await load(id)
      }else patch(id, { operation: { ...operation, status: statusOf(error,operation.status), error: (error as Error).message } })
    }
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
  function redo(id:string){
    const current=records.current[id],target=current?.redoStack?.at(-1)
    if(!target||current?.undoToken!==current.state?.state_token)return
    operate(id,{action:'redo',target_request_id:target},current.undoToken)
  }
  async function sendSave(id: string, operation: PendingSave) {
    if (flights.current.has(id)) return
    flights.current.add(id); invalidate(id)
    patch(id, { save: { ...operation, status: 'saving', error: '' }, verified: false, loading: false })
    try {
      const receipt = await api.saveArrangement(id, operation.payload)
      if(!receipt||typeof receipt.id!=='string'||!receipt.id||receipt.competition_id!==id||!Number.isInteger(receipt.sequence)||!Array.isArray(receipt.rows)||!validLayout(receipt.layout))throw new Error('保存回執不完整或不符，結果尚未確認；請原樣重試。')
      patch(id, { save: { ...operation, status: 'refresh', receipt, error: '' } })
      await load(id)
    } catch (error) { patch(id, { save: { ...operation, status: statusOf(error,operation.status), error: (error as Error).message } }) }
    finally { flights.current.delete(id) }
  }
  function save(id: string, metadata: Metadata) {
    const current = records.current[id]
    if (!current?.verified || !current.state?.latest || current.save || current.operation) return
    void sendSave(id, { payload: { ...metadata, request_id: crypto.randomUUID(), state_token: current.state.state_token, base_version_id: current.state.latest.id }, status: 'saving', error: '' })
  }
  async function recover(id:string,initialize=false){
    if(recovering.current.has(id)||flights.current.has(id))return
    recovering.current.add(id)
    patch(id,{loading:true,verified:false,error:''})
    try{
      await api.refreshArrangementSession(username)
      const current=records.current[id]
      if(current?.operation?.status==='unknown')await sendOperation(id,current.operation)
      else if(current?.save?.status==='unknown')await sendSave(id,current.save)
      else {
        if(current?.operation?.status==='rejected')patch(id,{operation:undefined})
        if(current?.save?.status==='rejected')patch(id,{save:undefined})
        await load(id,initialize)
      }
    }catch(error){patch(id,{loading:false,verified:false,error:(error as Error).message})}
    finally{recovering.current.delete(id)}
  }
  const unfinished = Object.values(workspaces).some(value => !!value.save || !!value.operation)
  useEffect(() => {
    if (!unfinished) return
    const protect = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect)
  }, [unfinished])
  return { workspaces, load, operate, undo, redo, recover, save, setDraft: (id: string, draft: Metadata) => patch(id, { draft }), setTextDraft: (id: string, key: string, text: string) => patch(id, { texts: { ...records.current[id]?.texts, [key]: text } }) }
}
export type ArrangementController = ReturnType<typeof useArrangementWorkspace>

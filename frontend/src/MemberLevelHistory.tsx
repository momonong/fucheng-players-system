import { useEffect, useState } from 'react'
import { request } from './api'
type Reference={competition_id:string;competition_name:string;competition_date:string;competition_level:number}
export function MemberLevelHistory({competitionId,memberId,historical}:{competitionId:string;memberId:string;historical:boolean}) {
  const [result,setResult]=useState<{key:string;rows?:Reference[];error?:string}>({key:''})
  const key=competitionId+'/'+memberId
  useEffect(()=>{
    let cancelled=false
    setResult({key})
    void request<Reference[]>(`/api/admin/competitions/${competitionId}/members/${memberId}/level-history`).then(rows=>{if(!cancelled)setResult({key,rows})}).catch(error=>{if(!cancelled)setResult({key,error:(error as Error).message})})
    return()=>{cancelled=true}
  },[key])
  const active=result.key===key?result:undefined
  return <section className="member-level-history" aria-label="歷次比賽級數"><h4>歷次比賽級數</h4><small>最近 5 場已結束比賽</small>{historical&&<small className="history-live-note">以下為目前查詢結果</small>}
    {active?.error?<p role="alert">無法讀取歷次紀錄：{active.error}</p>:!active?.rows?<p role="status">讀取歷次紀錄中…</p>:active.rows.length===0?<p>沒有符合條件的歷次紀錄。</p>:<ol>{active.rows.map(r=><li key={r.competition_id}><span><time>{r.competition_date}</time> {r.competition_name}</span><strong>{r.competition_level} 級</strong></li>)}</ol>}
  </section>
}

import type {
  AdminMember,
  AuditEntry,
  Competition,
  CompetitionDetail,
  CompetitionDraft,
  CompetitionRegistration,
  Diet,
  MemberDraft,
  PublicMember,
  RegistrationMember,
  ArrangementState, ArrangementVersion, ArrangementSave,
} from './types'

let csrfToken = ''

export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (options.method && !['GET', 'HEAD'].includes(options.method)) headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(url, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: '無法連線到伺服器' }))
    const error = new Error(body.detail || '操作失敗') as Error & { status: number }
    error.status = response.status
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function publicMembers(search = '', level = ''): Promise<PublicMember[]> {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (level) params.set('level', level)
  return request(`/api/public/members?${params}`)
}

export async function login(username: string, password: string): Promise<string> {
  const auth = await request<{ username: string; csrf_token: string }>('/api/auth/login', {
    method: 'POST', body: JSON.stringify({ username, password }),
  })
  csrfToken = auth.csrf_token
  return auth.username
}

export async function restoreSession(): Promise<string> {
  const auth = await request<{ username: string; csrf_token: string }>('/api/auth/me')
  csrfToken = auth.csrf_token
  return auth.username
}

export async function logout(): Promise<void> {
  await request('/api/auth/logout', { method: 'POST' })
  csrfToken = ''
}

export const adminMembers = () => request<AdminMember[]>('/api/admin/members')

export function saveMember(draft: MemberDraft, id?: string): Promise<AdminMember> {
  const payload = {
    ...draft,
    distinguishing_note: draft.distinguishing_note || null,
    legacy_number: draft.legacy_number || null,
  }
  return request(id ? `/api/admin/members/${id}` : '/api/admin/members', {
    method: id ? 'PUT' : 'POST', body: JSON.stringify(payload),
  })
}

export const memberHistory = (id: string) => request<AuditEntry[]>(`/api/admin/members/${id}/history`)

export const competitions = (deleted = false) => request<Competition[]>(`/api/admin/competitions?deleted=${deleted}`)
export const changeCompetitionDeletion = (item: Competition, restore: boolean) => request<Competition>(`/api/admin/competitions/${item.id}/${restore ? 'restore' : 'delete'}`, {
  method: 'POST', body: JSON.stringify({ version: item.version, confirmed: true }),
})
export const competition = (id: string) => request<CompetitionDetail>(`/api/admin/competitions/${id}`)

export function saveCompetition(draft: CompetitionDraft, id?: string): Promise<Competition> {
  const payload = {
    ...draft,
    notes: draft.notes || null,
    registration_deadline: `${draft.registration_deadline}:00+08:00`,
    reason: draft.reason || null,
  }
  return request(id ? `/api/admin/competitions/${id}` : '/api/admin/competitions', {
    method: id ? 'PUT' : 'POST', body: JSON.stringify(payload),
  })
}

export function registrationMembers(search = '', level = ''): Promise<RegistrationMember[]> {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (level) params.set('level', level)
  return request(`/api/admin/registration-members?${params}`)
}

export function createRegistration(
  competitionId: string,
  memberId: string,
  diet: Diet | null,
  reason: string,
  requestId: string,
): Promise<CompetitionRegistration> {
  return request(`/api/admin/competitions/${competitionId}/registrations`, {
    method: 'POST', body: JSON.stringify({ member_id: memberId, diet, reason: reason || null, request_id: requestId }),
  })
}

export function mutateRegistration(
  registration: CompetitionRegistration,
  action: 'cancel' | 'promote',
  reason: string,
  requestId: string,
): Promise<CompetitionRegistration> {
  return request(`/api/admin/registrations/${registration.id}/${action}`, {
    method: 'POST', body: JSON.stringify({ version: registration.version, reason: reason || null, request_id: requestId }),
  })
}

export function updateRegistrationDiet(
  registration: CompetitionRegistration,
  diet: Diet,
  reason: string,
  requestId: string,
): Promise<CompetitionRegistration> {
  return request(`/api/admin/registrations/${registration.id}/diet`, {
    method: 'PUT', body: JSON.stringify({ version: registration.version, diet, reason: reason || null, request_id: requestId }),
  })
}

export function updateRegistrationLevel(registration: Pick<CompetitionRegistration, 'id' | 'version'>, competitionLevel: number, reason: string | null, requestId: string): Promise<CompetitionRegistration> {
  return request(`/api/admin/registrations/${registration.id}/level`, {
    method: 'PUT', body: JSON.stringify({ version: registration.version, competition_level: competitionLevel, reason, request_id: requestId }),
  })
}

// Bound both transport and body decoding. An aborted write remains unknown to the
// workspace controller: its original request_id/payload is retained for replay.
async function arrangementRequest<T>(url:string,options:RequestInit={}):Promise<T>{
  const controller=new AbortController()
  const timer=setTimeout(()=>controller.abort(),20000)
  try{return await request<T>(url,{...options,signal:controller.signal})}
  catch(error){if(controller.signal.aborted)throw new Error('伺服器未及時回應，請重新核對操作結果。');throw error}
  finally{clearTimeout(timer)}
}

export const arrangement = (id: string) => arrangementRequest<ArrangementState>(`/api/admin/competitions/${id}/arrangement`)
export const initializeArrangement = (id: string) => arrangementRequest<ArrangementState>(`/api/admin/competitions/${id}/arrangement/initialize`, { method: 'POST' })
export const saveArrangement = (id: string, payload: ArrangementSave) => arrangementRequest<ArrangementVersion>(`/api/admin/competitions/${id}/arrangement/versions`, { method: 'POST', body: JSON.stringify(payload) })
export const arrangementVersion = (id: string, versionId: string) => arrangementRequest<ArrangementVersion>(`/api/admin/competitions/${id}/arrangement/versions/${versionId}`)

export const mutateGrid = (id: string, payload: import('./types').GridRequest) => arrangementRequest<import('./types').GridReceipt>(`/api/admin/competitions/${id}/arrangement/operations`, { method: 'POST', body: JSON.stringify(payload) })

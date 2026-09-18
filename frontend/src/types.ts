export type Diet = 'unset' | 'omnivore' | 'vegetarian'

export interface PublicMember {
  id: string
  name: string
  distinguishing_note: string | null
  level: number
}

export interface AdminMember extends PublicMember {
  diet: Diet
  legacy_number: string | null
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface MemberDraft {
  name: string
  distinguishing_note: string
  legacy_number: string
  level: number
  diet: Diet
  is_active: boolean
  version?: number
}

export interface AuditEntry {
  id: string
  action: string
  changes: Record<string, { before: unknown; after: unknown }>
  admin_username: string
  created_at: string
}

export type CompetitionStatus = 'draft' | 'open' | 'closed' | 'ended' | 'cancelled'
export type RegistrationStatus = 'confirmed' | 'waitlisted' | 'cancelled'

export interface CompetitionSummary {
  confirmed: number
  waitlisted: number
  cancelled: number
  remaining: number
  pending_promotions: number
  diet_counts: Record<Diet, number>
  level_counts: Record<string, number>
}

export interface Competition {
  deleted_at: string | null
  id: string
  name: string
  competition_date: string
  capacity: number
  registration_deadline: string
  notes: string | null
  status: CompetitionStatus
  version: number
  created_at: string
  updated_at: string
  effective_registration_open: boolean
  summary: CompetitionSummary
}

export interface CompetitionDraft {
  name: string
  competition_date: string
  capacity: number
  registration_deadline: string
  notes: string
  status: CompetitionStatus
  version?: number
  reason?: string
}

export interface RegistrationMember {
  id: string
  name: string
  distinguishing_note: string | null
  level: number
  diet: Diet
}

export interface CompetitionRegistration {
  id: string
  competition_id: string
  member_id: string
  member_name: string
  distinguishing_note: string | null
  status: RegistrationStatus
  diet: Diet
  hard_level_snapshot: number
  queue_sequence: number
  version: number
  created_by_username: string
  updated_by_username: string
  created_at: string
  updated_at: string
}

export interface CompetitionDetail {
  competition: Competition
  registrations: CompetitionRegistration[]
}

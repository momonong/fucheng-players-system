export type Diet = 'unset' | 'omnivore' | 'vegetarian'

export interface PublicMember {
  id: string
  name: string
  distinguishing_note: string | null
  level: number
  diet: Diet
}

export interface AdminMember extends PublicMember {
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

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
  competition_level_counts: Record<string, number>
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
  competition_level: number
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

export interface ArrangementRow {
  diet: Diet | null
  member_level: number | null
  registration_id: string
  member_id: string
  member_name: string
  distinguishing_note: string | null
  queue_sequence: number
  competition_level: number
  version: number
}
export interface ArrangementVersionSummary {
  id: string; competition_id: string; sequence: number; label: string
  editor_label: string; note: string | null; admin_id: string; actor_name: string; created_at: string
}
export interface ArrangementVersion extends ArrangementVersionSummary { rows: ArrangementRow[]; schema_version: number; layout: GridLayout | null }
export interface ArrangementState {
  schema_version: number; layout: GridLayout | null; layout_baseline: GridLayout | null; layout_revision: number; layout_initialized_at: string | null
  editable: boolean; rows: ArrangementRow[]; state_token: string; latest: ArrangementVersion | null; versions: ArrangementVersionSummary[]
}
export interface ArrangementSave {
  request_id: string; state_token: string; base_version_id: string
  label: string; editor_label: string; note: string
}

export type GridPoint = { row_id: string; column_id: string }
export type GridCell = GridPoint & ({ kind: 'registration'; registration_id: string } | { kind: 'text'; text: string })
export type GridMerge = { id: string; start: GridPoint; end: GridPoint }
export interface GridLayout {
  schema_version: number
  rows: { id: string; role: 'header' | 'body'; shade?: number }[]
  columns: { id: string; kind: 'level' | 'text'; level: number | null; title?: string | null; shade?: number; header_shade?:number|null }[]
  cells: GridCell[]
  cell_shades?: (GridPoint & { shade: number })[]
  merges: GridMerge[]
}
export type GridOperation = { action: 'move'; registration_id: string; target: GridPoint }
  | { action: 'undo'; target_request_id: string }
  | { action: 'swap'; registration_id: string; target_registration_id: string }
  | { action: 'insert'; registration_id: string; target: GridPoint; side: 'before' | 'after' }
  | { action: 'move_empty'; registration_id: string; target: GridPoint }
  | { action: 'shade_header'; column_id:string; shade:number }
  | { action: 'shade_cells'; start: GridPoint; end: GridPoint; shade: number }
  | { action: 'shade_row' | 'shade_column'; axis_id: string; shade: number }
  | { action: 'move_bottom'; registration_id: string; level: number }
  | { action: 'insert_row' | 'insert_column' | 'insert_header'; before_id: string | null }
  | { action: 'delete_row' | 'delete_column'; axis_id: string; confirmed_text: boolean }
  | { action: 'text'; target: GridPoint; text: string }
  | { action: 'column_title'; column_id: string; text: string }
  | { action: 'merge'; start: GridPoint; end: GridPoint }
  | { action: 'unmerge'; merge_id: string }
export type GridRequest = { request_id: string; state_token: string; operation: GridOperation }
export type GridReceipt = { state_token?: string | null; undo_head?: string | null; request_id: string; competition_id: string; revision: number; operation: GridOperation; layout: GridLayout }

// Espejo de las vistas de Python (setid/jobs/views.py y setid/app/bridge.py).

export type JobStatus =
  | 'queued'
  | 'downloading'
  | 'analyzing'
  | 'aggregating'
  | 'done'
  | 'failed'
  | 'cancelled'

export type SourceType = 'youtube' | 'soundcloud' | 'upload'
export type EntrySource = 'fingerprint' | 'community' | 'unknown'
export type ExportFormat = 'txt' | 'csv' | 'json' | 'm3u'
export type ProviderName = 'fake' | 'acrcloud' | 'audd' | 'shazam'

export interface Job {
  id: number
  source_type: SourceType
  source: string
  canonical_id: string | null
  title: string | null
  uploader: string | null
  duration_s: number | null
  provider: string
  status: JobStatus
  progress: number
  message: string | null
  error: string | null
  queries_used: number
  retries: number
  estimated_cost: number
  cached: boolean
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface SearchLinks {
  beatport: string
  spotify: string
  youtube: string
}

export interface Entry {
  position: number
  start_s: number
  end_s: number
  artist: string
  title: string
  label: string | null
  isrc: string | null
  confidence: number | null
  detections: number
  source: EntrySource
  timestamp_url: string | null
  search: SearchLinks | null
  /** Solo en los ID – ID: lo que dice la comunidad sobre ese tramo (sin verificar). */
  suggestions: Hint[]
}

export type HintKind = 'tracklist' | 'comment' | 'reply'

export interface Hint {
  kind: HintKind
  start_s: number | null
  artist: string
  title: string
  unreleased: boolean
  is_id: boolean
  origin: string
  author: string | null
  likes: number
  text: string
  position: number
  /** Lo que acompaña al track en un mashup, p. ej. «/W Artista - Acapella». */
  note: string | null
  timestamp_url: string | null
  search: SearchLinks | null
}

export interface Community {
  tracklist_origin: string | null
  tracklist: Hint[]
  mentions: Hint[]
}

export const EMPTY_COMMUNITY: Community = { tracklist_origin: null, tracklist: [], mentions: [] }

export interface JobDetail extends Job {
  tracklist: Entry[]
  live: boolean
  community: Community
}

export interface SettingsValues {
  provider: ProviderName
  window_s: number
  step_s: number
  concurrency: number | null
  min_interval_s: number | null
  daily_query_budget: number | null
  min_confidence: number
  max_gap_segments: number
  unknown_min_segments: number
  mark_unknown_edges: boolean
  community_enabled: boolean
  community_max_comments: number
  acrcloud_host: string
  audd_confidence: number
  shazam_confidence: number
  cost_per_query_acrcloud: number
  cost_per_query_audd: number
}

export type SecretName = 'acrcloud_access_key' | 'acrcloud_access_secret' | 'audd_api_token'

export interface SettingsView {
  values: SettingsValues
  secrets: Record<SecretName, boolean>
  effective_limits: { concurrency: number; min_interval_s: number }
}

export interface Budget {
  provider: string
  used_today: number
  limit: number | null
  remaining: number | null
}

export interface AppInfo {
  version: string
  data_dir: string
  legal_notice: string
}

export interface ExportedFile {
  filename: string
  media_type: string
  content: string
}

export type BridgeEvent =
  | { type: 'job'; job: Job }
  | { type: 'tracklist'; job_id: number; live: boolean; tracklist: Entry[] }
  | { type: 'job_deleted'; job_id: number }
  | { type: 'community'; job_id: number; community: Community }
  | { type: 'file_dropped'; job: Job }
  | { type: 'error'; error: string }

export const ACTIVE_STATUSES: readonly JobStatus[] = ['downloading', 'analyzing', 'aggregating']
export const FINAL_STATUSES: readonly JobStatus[] = ['done', 'failed', 'cancelled']

export const isActive = (s: JobStatus) => ACTIVE_STATUSES.includes(s)
export const isFinal = (s: JobStatus) => FINAL_STATUSES.includes(s)

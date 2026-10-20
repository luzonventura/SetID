// Backend simulado para desarrollar la interfaz en el navegador y para los tests.
// Imita los tiempos y los eventos del JobManager de Python.

import type { RawApi } from './bridge'
import { emitBridgeEvent } from './bridge'
import type { Community, Entry, Hint, Job, JobDetail, SecretName, SettingsView } from './types'
import { EMPTY_COMMUNITY } from './types'

type Result<T> = { ok: true; data: T } | { ok: false; error: string }
const ok = <T>(data: T): Result<T> => ({ ok: true, data })
const fail = <T>(error: string): Result<T> => ({ ok: false, error })

const enc = encodeURIComponent

function links(artist: string, title: string) {
  const q = enc(`${artist} ${title}`)
  return {
    beatport: `https://www.beatport.com/search?q=${q}`,
    spotify: `https://open.spotify.com/search/${q}`,
    youtube: `https://www.youtube.com/results?search_query=${q}`,
  }
}

function hint(over: Partial<Hint> & Pick<Hint, 'artist' | 'title' | 'kind'>): Hint {
  const isId = over.artist === 'ID' && over.title === 'ID'
  return {
    start_s: null, unreleased: false, is_id: isId, origin: 'descripción', author: null,
    likes: 0, text: `${over.artist} - ${over.title}`, position: 0, note: null, timestamp_url: null,
    search: isId ? null : links(over.artist, over.title), ...over,
  }
}

// Lo que diría la comunidad del set de ejemplo: el tramo ID – ID es de 9:30 a 11:30.
const SAMPLE_COMMUNITY: Community = {
  tracklist_origin: 'comentario fijado',
  tracklist: [
    hint({ kind: 'tracklist', position: 1, start_s: 120, artist: 'Joey Harmless', title: 'So Shady', origin: 'comentario fijado' }),
    hint({ kind: 'tracklist', position: 2, start_s: 390, artist: 'Cris Ocana', title: 'Brasuca Vibes', note: 'Max Dean & Luke Dean - Gets Like That (Acapella)', origin: 'comentario fijado' }),
    hint({ kind: 'tracklist', position: 3, start_s: 570, artist: 'ID', title: 'ID', unreleased: true, origin: 'comentario fijado' }),
    hint({ kind: 'tracklist', position: 4, start_s: 690, artist: 'Daniel Insogna', title: 'Hold On', origin: 'comentario fijado' }),
  ],
  mentions: [
    hint({ kind: 'reply', start_s: 600, artist: 'Toman', title: 'Bounce', unreleased: true, origin: 'respuesta de @digger', author: '@digger', likes: 31, text: "It's Toman - Bounce (unreleased, out on Music On soon)" }),
    hint({ kind: 'comment', start_s: 1500, artist: 'Bassel Darwish', title: 'Lami', origin: 'comentario de @raver', author: '@raver', likes: 4, text: '25:00 Bassel Darwish - Lami 🔥🔥' }),
  ],
}

const SAMPLE: Omit<Entry, 'position' | 'timestamp_url' | 'search' | 'suggestions'>[] = [
  { start_s: 120, end_s: 372, artist: 'Joey Harmless', title: 'So Shady', label: 'Bear Fresh Records', isrc: null, confidence: 0.92, detections: 8, source: 'fingerprint' },
  { start_s: 390, end_s: 552, artist: 'Cris Ocana', title: 'Brasuca Vibes (Extended Mix)', label: 'Klaphouse Records', isrc: null, confidence: 0.81, detections: 5, source: 'fingerprint' },
  { start_s: 570, end_s: 690, artist: 'ID', title: 'ID', label: null, isrc: null, confidence: null, detections: 0, source: 'unknown' },
  { start_s: 690, end_s: 912, artist: 'Daniel Insogna & AJK (US)', title: 'Hold On', label: 'SK LAB', isrc: null, confidence: 0.64, detections: 4, source: 'fingerprint' },
  { start_s: 930, end_s: 1182, artist: 'Souler (ES)', title: 'Brillo', label: 'Nervous Records', isrc: null, confidence: 0.88, detections: 7, source: 'fingerprint' },
  { start_s: 1200, end_s: 1452, artist: 'Ammu & Hoff', title: 'Want Your Time', label: 'Libero X', isrc: null, confidence: 0.47, detections: 2, source: 'fingerprint' },
  { start_s: 1470, end_s: 1680, artist: 'Bassel Darwish', title: 'Lami', label: 'Moon Harbour', isrc: null, confidence: 0.95, detections: 9, source: 'fingerprint' },
]

function withTimestamps(job: Job, community: Community): Community {
  const stamp = (h: Hint): Hint => ({
    ...h,
    timestamp_url:
      job.source_type === 'youtube' && h.start_s !== null ? `${job.source}&t=${Math.floor(h.start_s)}s` : null,
  })
  return {
    ...community,
    tracklist: community.tracklist.map(stamp),
    mentions: community.mentions.map(stamp),
  }
}

function decorate(job: Job, rows: typeof SAMPLE, community: Community): Entry[] {
  // Como en Python: no se sugiere un track que la huella ya ha identificado en el set.
  const known = new Set(rows.filter((r) => r.source !== 'unknown').map((r) => r.title.toLowerCase()))
  const all = [...community.tracklist, ...community.mentions].filter(
    (h) => !known.has(h.title.toLowerCase()),
  )
  return rows.map((row, i) => ({
    ...row,
    position: i + 1,
    timestamp_url:
      job.source_type === 'youtube' ? `${job.source}&t=${Math.floor(row.start_s)}s` : null,
    search: row.source === 'unknown' ? null : links(row.artist, row.title),
    suggestions:
      row.source === 'unknown'
        ? all
            .filter((h) => h.start_s !== null && h.start_s >= row.start_s - 45 && h.start_s <= row.end_s + 45)
            .sort((a, b) => Number(a.is_id) - Number(b.is_id) || b.likes - a.likes)
        : [],
  }))
}

export interface MockOptions {
  tickMs?: number
  stepsPerJob?: number
}

export function createMockApi(options: MockOptions = {}): RawApi {
  const tickMs = options.tickMs ?? 350
  const steps = options.stepsPerJob ?? 40
  let nextId = 1
  const jobs = new Map<number, Job>()
  const tracks = new Map<number, Entry[]>()
  const communities = new Map<number, Community>()
  const timers = new Map<number, ReturnType<typeof setInterval>>()
  const secrets: Record<SecretName, boolean> = {
    acrcloud_access_key: false,
    acrcloud_access_secret: false,
    audd_api_token: false,
  }
  let settings: SettingsView = {
    values: {
      provider: 'shazam', window_s: 12, step_s: 30, concurrency: null, min_interval_s: null,
      daily_query_budget: null, min_confidence: 0.5, max_gap_segments: 2,
      unknown_min_segments: 3, mark_unknown_edges: false, community_enabled: true, community_max_comments: 300,
      acrcloud_host: 'identify-eu-west-1.acrcloud.com', audd_confidence: 0.45,
      shazam_confidence: 0.45, cost_per_query_acrcloud: 0, cost_per_query_audd: 0,
    },
    secrets,
    effective_limits: { concurrency: 1, min_interval_s: 1.5 },
  }
  let used = 0

  const update = (id: number, fields: Partial<Job>): Job => {
    const current = jobs.get(id)
    if (!current) throw new Error(`job ${id} no existe`)
    const job = { ...current, ...fields }
    jobs.set(id, job)
    emitBridgeEvent({ type: 'job', job })
    return job
  }

  const run = (id: number) => {
    let step = 0
    const duration = 1800
    const timer = setInterval(() => {
      step += 1
      const job = jobs.get(id)
      if (!job) return clearInterval(timer)
      if (step <= 4) {
        update(id, {
          status: 'downloading',
          progress: step * 6,
          message: step < 3 ? 'Descargando el audio' : 'Normalizando el audio',
          title: job.title ?? 'Jorgesyn — Live Set at LOAD',
          uploader: job.uploader ?? 'LOAD',
          duration_s: duration,
          started_at: job.started_at ?? new Date().toISOString(),
        })
        return
      }
      if (step < steps) {
        const fraction = (step - 4) / (steps - 4)
        const scanned = fraction * duration
        const visible = SAMPLE.filter((t) => t.start_s < scanned).map((t) => ({
          ...t,
          end_s: Math.min(t.end_s, scanned),
        }))
        const entries = decorate(job, visible, EMPTY_COMMUNITY)
        tracks.set(id, entries)
        used += 1
        update(id, {
          status: 'analyzing',
          progress: 30 + fraction * 65,
          message: `Segmento ${step - 4} de ${steps - 4}`,
          queries_used: step - 4,
        })
        emitBridgeEvent({ type: 'tracklist', job_id: id, live: true, tracklist: entries })
        return
      }
      clearInterval(timer)
      timers.delete(id)
      // Solo los enlaces tienen comentarios; los archivos propios no.
      const community = job.source_type === 'upload' ? EMPTY_COMMUNITY : withTimestamps(job, SAMPLE_COMMUNITY)
      communities.set(id, community)
      const entries = decorate(job, SAMPLE, community)
      tracks.set(id, entries)
      update(id, { status: 'done', progress: 100, message: 'Listo', finished_at: new Date().toISOString() })
      emitBridgeEvent({ type: 'tracklist', job_id: id, live: false, tracklist: entries })
      emitBridgeEvent({ type: 'community', job_id: id, community })
    }, tickMs)
    timers.set(id, timer)
  }

  const create = (source: string, type: Job['source_type'], canonical: string | null): Job => {
    const id = nextId++
    const job: Job = {
      id, source_type: type, source, canonical_id: canonical, title: null, uploader: null,
      duration_s: null, provider: settings.values.provider, status: 'queued', progress: 0,
      message: 'En cola', error: null, queries_used: 0, retries: 0, estimated_cost: 0,
      cached: false, created_at: new Date().toISOString(), started_at: null, finished_at: null,
    }
    jobs.set(id, job)
    emitBridgeEvent({ type: 'job', job })
    run(id)
    return job
  }

  const detail = (id: number): JobDetail | null => {
    const job = jobs.get(id)
    if (!job) return null
    return {
      ...job,
      tracklist: tracks.get(id) ?? [],
      live: job.status !== 'done',
      community: communities.get(id) ?? EMPTY_COMMUNITY,
    }
  }

  return {
    async create_job(url) {
      const match = /(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/.exec(url)
      if (!/^https?:\/\/(www\.|m\.)?(youtube\.com|youtu\.be|soundcloud\.com|on\.soundcloud\.com)\//i.test(url.trim())) {
        return fail('Solo se aceptan enlaces de YouTube o SoundCloud.')
      }
      if (match) {
        return ok(create(`https://www.youtube.com/watch?v=${match[1]}`, 'youtube', `yt:${match[1]}`))
      }
      return ok(create(url.trim(), 'soundcloud', null))
    },
    async create_job_from_file() {
      return ok(create('C:\\Música\\sets\\mi-set.wav', 'upload', null))
    },
    async list_jobs(limit) {
      return ok([...jobs.values()].reverse().slice(0, limit))
    },
    async get_job(id) {
      const d = detail(id)
      return d ? ok(d) : fail('El trabajo no existe.')
    },
    async cancel_job(id) {
      clearInterval(timers.get(id))
      return jobs.has(id) ? ok(update(id, { status: 'cancelled', message: 'Cancelado' })) : fail('El trabajo no existe.')
    },
    async delete_job(id) {
      clearInterval(timers.get(id))
      jobs.delete(id)
      emitBridgeEvent({ type: 'job_deleted', job_id: id })
      return ok(null)
    },
    async export_job(id, fmt) {
      const d = detail(id)
      if (!d) return fail('El trabajo no existe.')
      const lines = d.tracklist.map(
        (e) => `${Math.floor(e.start_s / 60).toString().padStart(2, '0')}:${Math.floor(e.start_s % 60).toString().padStart(2, '0')} ${e.source === 'unknown' ? 'ID – ID' : `${e.artist} – ${e.title}`}`,
      )
      return ok({ filename: `tracklist.${fmt}`, media_type: 'text/plain', content: lines.join('\n') })
    },
    async save_export(_id, fmt) {
      return ok({ path: `C:\\Users\\demo\\Downloads\\tracklist.${fmt}` })
    },
    async get_settings() {
      return ok(settings)
    },
    async update_settings(changes) {
      if (changes.window_s !== undefined && (changes.window_s <= 0 || changes.window_s > 30)) {
        return fail('Valor no válido en: window_s')
      }
      settings = { ...settings, values: { ...settings.values, ...changes } }
      return ok(settings)
    },
    async reset_settings() {
      return ok(settings)
    },
    async set_secret(name, value) {
      secrets[name] = Boolean(value)
      return ok({ ...secrets })
    },
    async get_budget() {
      const limit = settings.values.daily_query_budget
      return ok({ provider: settings.values.provider, used_today: used, limit, remaining: limit === null ? null : Math.max(0, limit - used) })
    },
    async open_external(url) {
      window.open(url, '_blank', 'noopener')
      return ok(null)
    },
    async app_info() {
      return ok({
        version: '0.1.0 (simulado)',
        data_dir: '%LOCALAPPDATA%\\SetID',
        legal_notice:
          'Herramienta de uso personal. Descargar contenido de YouTube puede contravenir sus términos de servicio; la opción recomendada es usar tu propio archivo. El audio nunca se almacena ni se redistribuye.',
      })
    },
  }
}

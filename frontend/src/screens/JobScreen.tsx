import { useEffect, useState } from 'react'

import { api, BridgeError } from '../api/bridge'
import { isActive, isFinal, type Job, type JobStatus } from '../api/types'
import { ExportBar } from '../components/ExportBar'
import { SetTimeline } from '../components/SetTimeline'
import { CommunityPanel } from '../components/Community'
import { Tracklist } from '../components/Tracklist'
import { ExternalLink, Notice, Spinner, StatusPill } from '../components/ui'
import { fileName, formatDuration, sourceLabel } from '../lib/format'
import { navigate } from '../lib/router'
import { useJobs } from '../state/context'

const PHASES: { status: JobStatus; text: string }[] = [
  { status: 'downloading', text: 'Audio' },
  { status: 'analyzing', text: 'Huellas' },
  { status: 'aggregating', text: 'Tracklist' },
  { status: 'done', text: 'Listo' },
]

// Tramos del progreso global que corresponden a cada fase (ver setid/pipeline.py).
const PHASE_RANGES: Partial<Record<JobStatus, [number, number]>> = {
  downloading: [0, 30],
  analyzing: [30, 95],
  aggregating: [95, 100],
}

function phaseProgress(job: Job): number {
  const range = PHASE_RANGES[job.status]
  if (!range) return 0
  const [from, to] = range
  return Math.min(100, Math.max(0, ((job.progress - from) / (to - from)) * 100))
}

function Phases({ job }: { job: Job }) {
  const current = PHASES.findIndex((p) => p.status === job.status)
  const active = isActive(job.status)
  return (
    <div aria-live="polite">
      <ol className="grid grid-cols-4 gap-1" aria-label="Fases">
        {PHASES.map((phase, i) => {
          const done = job.status === 'done' || (current >= 0 && i < current)
          const now = i === current && active
          return (
            <li key={phase.status} aria-current={now ? 'step' : undefined}>
              <div className={`h-1 ${done ? 'bg-signal' : now ? 'bg-signal/50' : 'bg-line'}`}>
                {now && <div className="h-full bg-signal" style={{ width: `${phaseProgress(job)}%` }} />}
              </div>
              <span className={`label mt-2 block ${now || done ? 'text-chalk' : ''}`}>
                {String(i + 1).padStart(2, '0')} {phase.text}
              </span>
            </li>
          )
        })}
      </ol>
      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-chalk/90">{job.message}</p>
        {active && (
          <p className="timecode text-sm text-signal">
            {Math.round(job.progress)}
            <span className="text-fog">%</span>
          </p>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Progreso"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(job.progress)}
        className="sr-only"
      />
    </div>
  )
}

function Stats({ job, tracks }: { job: Job; tracks: number }) {
  const items: [string, string][] = [
    ['Duración', formatDuration(job.duration_s)],
    ['Tracks', String(tracks)],
    ['Consultas', job.cached ? '0 (caché)' : String(job.queries_used)],
    ['Proveedor', job.provider],
  ]
  if (job.estimated_cost > 0) items.push(['Coste est.', `$${job.estimated_cost.toFixed(3)}`])
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-5">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="label">{k}</dt>
          <dd className="timecode mt-1 text-sm">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function JobScreen({ id }: { id: number }) {
  const { jobs, tracklists, community: communities, loadDetail } = useJobs()
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<number | null>(null)
  const [tab, setTab] = useState<'tracklist' | 'community'>('tracklist')
  const job = jobs[id]
  const list = tracklists[id]
  const community = communities[id]
  const status = job?.status

  // El componente se monta de nuevo por cada id (key en App), así que no hay que limpiar.
  useEffect(() => {
    loadDetail(id).catch((e) =>
      setLoadError(e instanceof BridgeError ? e.message : 'No se pudo cargar el trabajo.'),
    )
  }, [id, loadDetail])

  // Al terminar se pide el detalle definitivo (por si se perdió algún evento).
  useEffect(() => {
    if (status && isFinal(status)) void loadDetail(id).catch(() => {})
  }, [id, status, loadDetail])

  if (loadError && !job) {
    return (
      <Notice
        tone="error"
        action={
          <a className="btn-ghost" href="#/">
            Volver
          </a>
        }
      >
        {loadError}
      </Notice>
    )
  }
  if (!job) return <Spinner label="Cargando trabajo" />

  const entries = list?.entries ?? []
  const tracks = entries.filter((e) => e.source !== 'unknown').length
  const communityTotal = community ? community.tracklist.length + community.mentions.length : 0
  const running = isActive(job.status) || job.status === 'queued'
  const title = job.title ?? (job.source_type === 'upload' ? fileName(job.source) : 'Leyendo metadatos…')
  const scanned =
    job.status === 'analyzing' && job.duration_s
      ? (Math.max(0, job.progress - 30) / 65) * job.duration_s
      : job.status === 'downloading' || job.status === 'queued'
        ? 0
        : null

  const act = async (action: () => Promise<unknown>) => {
    setActionError(null)
    try {
      await action()
    } catch (err) {
      setActionError(err instanceof BridgeError ? err.message : 'La acción ha fallado.')
    }
  }

  const reprocess = () =>
    act(async () => {
      const next =
        job.source_type === 'upload'
          ? await api.createJobFromPath(job.source, true)
          : await api.createJob(job.source, true)
      if (next) navigate({ name: 'job', id: next.id })
    })

  const remove = () =>
    act(async () => {
      if (!window.confirm('¿Borrar este trabajo y su tracklist del historial?')) return
      await api.deleteJob(job.id)
      navigate({ name: 'home' })
    })

  const select = (position: number) => {
    setHighlight(position)
    document.getElementById(`track-${position}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <article className="space-y-10" aria-labelledby="job-title">
      <header className="animate-rise space-y-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <StatusPill status={job.status} />
          <span className="label">{sourceLabel(job.source_type)}</span>
          {job.source_type !== 'upload' && (
            <ExternalLink url={job.source} className="label hover:text-signal">
              Abrir original ↗
            </ExternalLink>
          )}
        </div>
        <h1 id="job-title" className="display text-[clamp(2rem,5.5vw,4.25rem)] break-words">
          {title}
        </h1>
        {job.uploader && <p className="text-lg text-fog [font-stretch:110%]">{job.uploader}</p>}
      </header>

      {running && <Phases job={job} />}

      {job.status === 'queued' && job.message && job.message !== 'En cola' && (
        <Notice tone="warn">{job.message}</Notice>
      )}
      {job.status === 'failed' && (
        <Notice
          tone="error"
          action={
            <button type="button" className="btn-ghost" onClick={reprocess}>
              Reintentar
            </button>
          }
        >
          {job.error ?? 'El trabajo ha fallado.'}
        </Notice>
      )}
      {job.status === 'cancelled' && <Notice>Trabajo cancelado. No queda audio en disco.</Notice>}
      {actionError && <Notice tone="error">{actionError}</Notice>}

      {job.duration_s && (job.status !== 'failed' || entries.length > 0) && (
        <section aria-label="Vista general del set">
          <SetTimeline
            duration={job.duration_s}
            entries={entries}
            scannedS={running ? scanned : null}
            onSelect={select}
          />
        </section>
      )}

      {(job.status === 'done' || entries.length > 0) && <Stats job={job} tracks={tracks} />}

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          {communityTotal === 0 ? (
            <h2 id="tab-tracklist" className="display text-2xl">
              Tracklist
            </h2>
          ) : (
            <div role="tablist" aria-label="Resultados" className="flex gap-6">
              {(
                [
                  ['tracklist', 'Tracklist', null],
                  ['community', 'Comunidad', communityTotal],
                ] as const
              ).map(([key, text, count]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  id={`tab-${key}`}
                  aria-selected={tab === key}
                  aria-controls={`panel-${key}`}
                  onClick={() => setTab(key)}
                  className={`display pb-1 text-2xl transition-colors ${
                    tab === key
                      ? 'border-b-2 border-signal text-chalk'
                      : 'border-b-2 border-transparent text-fog hover:text-chalk'
                  }`}
                >
                  {text}
                  {count !== null && <span className="timecode ml-2 align-top text-xs text-fog">{count}</span>}
                </button>
              ))}
            </div>
          )}
          {list?.live && running && <span className="label text-signal">En directo</span>}
        </div>
        <div
          role={communityTotal ? 'tabpanel' : undefined}
          id="panel-tracklist"
          aria-labelledby="tab-tracklist"
          hidden={tab !== 'tracklist'}
        >
          <Tracklist entries={entries} live={running} highlight={highlight} />
        </div>
        {communityTotal > 0 && community && (
          <div role="tabpanel" id="panel-community" aria-labelledby="tab-community" hidden={tab !== 'community'}>
            <CommunityPanel community={community} />
          </div>
        )}
      </section>

      {job.status === 'done' && <ExportBar jobId={job.id} />}

      <div className="flex flex-wrap gap-3 border-t border-line pt-6">
        {running && (
          <button type="button" className="btn-danger" onClick={() => act(() => api.cancelJob(job.id))}>
            Cancelar
          </button>
        )}
        {isFinal(job.status) && (
          <button type="button" className="btn-ghost" onClick={reprocess}>
            Volver a analizar
          </button>
        )}
        {isFinal(job.status) && (
          <button type="button" className="btn-danger" onClick={remove}>
            Borrar
          </button>
        )}
      </div>
    </article>
  )
}

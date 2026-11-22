import { useEffect, useRef, useState } from 'react'

import { api, BridgeError } from '../api/bridge'
import { isActive, isFinal, type Entry, type Job, type JobStatus } from '../api/types'
import { CommunityPanel } from '../components/Community'
import { Cover } from '../components/Cover'
import { PreviewCover } from '../components/PreviewCover'
import { ExportBar } from '../components/ExportBar'
import { RecordStage } from '../components/RecordStage'
import { SetTimeline } from '../components/SetTimeline'
import { Tracklist } from '../components/Tracklist'
import { ExternalLink, Notice, Spinner, StatusPill } from '../components/ui'
import { catalogNumber, fileName, formatDuration, formatTime, sourceLabel } from '../lib/format'
import { stopPreview } from '../lib/preview'
import { href, navigate } from '../lib/router'
import { useJobs } from '../state/context'
import type { TurntableMode } from '../three/model'

const PHASES: { status: JobStatus; text: string }[] = [
  { status: 'downloading', text: 'Audio' },
  { status: 'analyzing', text: 'Huellas' },
  { status: 'aggregating', text: 'Tracklist' },
  { status: 'done', text: 'Listo' },
]

/** Número que se desliza hasta su valor en lugar de saltar. */
function useTween(target: number, ms = 600): number {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    const start = performance.now()
    const origin = from.current
    if (origin === target) return
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      from.current = origin + (target - origin) * eased
      setValue(from.current)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return value
}

const SEGMENTS = 50

function Progress({ job }: { job: Job }) {
  const current = PHASES.findIndex((p) => p.status === job.status)
  const active = isActive(job.status) || job.status === 'queued'
  const percent = job.status === 'done' ? 100 : Math.round(job.progress)
  const shown = useTween(percent)
  const lit = Math.round((shown / 100) * SEGMENTS)
  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <p aria-hidden className="display timecode text-[clamp(4.5rem,8vw,7rem)] leading-[0.78]">
          {String(Math.round(shown)).padStart(2, '0')}
          <span className="voice ml-1 text-[0.4em] text-fog">%</span>
        </p>
        <div className="min-w-0 pb-1 text-right">
          <p className="label">Progreso</p>
          <p aria-live="polite" className="mt-1.5 truncate text-sm text-chalk/85">
            {job.message ?? '—'}
          </p>
        </div>
      </div>
      {/* Escala segmentada, como el vúmetro de una mesa. */}
      <div
        role="progressbar"
        aria-label="Progreso"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="flex h-5 items-end gap-[3px]"
      >
        {Array.from({ length: SEGMENTS }, (_, i) => {
          const on = i < lit
          const head = active && i === lit - 1
          return (
            <span
              key={i}
              className={`flex-1 transition-[height,background-color] duration-300 ${
                head
                  ? 'h-full animate-pulse-dot bg-paper'
                  : on
                    ? 'h-[70%] bg-signal'
                    : 'h-[40%] bg-line-strong'
              }`}
            />
          )
        })}
      </div>
      <ol className="grid grid-cols-4 gap-3" aria-label="Fases">
        {PHASES.map((phase, i) => {
          const done = job.status === 'done' || (current >= 0 && i < current)
          const now = i === current && active
          return (
            <li
              key={phase.status}
              aria-current={now ? 'step' : undefined}
              className={`border-t pt-2 font-mono text-[0.65rem] tracking-[0.12em] uppercase transition-colors duration-500 ${
                done
                  ? 'border-signal text-chalk'
                  : now
                    ? 'border-paper text-signal'
                    : 'border-line text-fog/60'
              }`}
            >
              <span aria-hidden className="mr-1.5 opacity-60">
                {String(i + 1).padStart(2, '0')}
              </span>
              {phase.text}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

/** Ficha técnica con puntos de guía, como la contraportada de un disco. */
function Stats({ job, tracks }: { job: Job; tracks: number }) {
  const items: [string, string][] = [
    ['Duración', formatDuration(job.duration_s)],
    ['Tracks', String(tracks)],
    ['Consultas', job.cached ? '0 · caché' : String(job.queries_used)],
    ['Proveedor', job.provider],
  ]
  if (job.estimated_cost > 0) items.push(['Coste est.', `$${job.estimated_cost.toFixed(3)}`])
  return (
    <dl className="space-y-2.5">
      {items.map(([k, v]) => (
        <div key={k} className="flex items-baseline gap-3">
          <dt className="label">{k}</dt>
          <span aria-hidden className="flex-1 border-b border-dotted border-line-strong" />
          <dd className={`timecode text-sm text-chalk ${k === 'Proveedor' ? 'capitalize' : ''}`}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** Mientras analiza: el último track identificado, como en la pantalla de un CDJ. */
function NowPlaying({ entries }: { entries: Entry[] }) {
  const last = [...entries].reverse().find((e) => e.source !== 'unknown')
  if (!last) return null
  return (
    <div key={`${last.position}-${last.title}`} className="flex animate-rise items-center gap-4">
      <PreviewCover
        url={last.cover_url}
        previewUrl={last.preview_url}
        artist={last.artist}
        title={last.title}
        size={76}
      />
      <span className="min-w-0">
        <span className="label flex items-center gap-2 !text-signal">
          <span className="size-1.5 animate-pulse-dot rounded-full bg-signal" />
          Último identificado
          <span className="timecode text-fog">{formatTime(last.start_s)}</span>
        </span>
        <span className="display mt-2 block truncate text-2xl">{last.artist}</span>
        <span className="voice block truncate text-xl leading-tight text-fog">{last.title}</span>
      </span>
    </div>
  )
}

/** Al terminar: las carátulas del set en un mosaico; cada una lleva a su track. */
function CoverWall({ entries, onSelect }: { entries: Entry[]; onSelect(position: number): void }) {
  const seen = new Set<string>()
  const tracks = entries.filter((e) => {
    if (e.source === 'unknown') return false
    const key = `${e.artist}|${e.title}`.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  if (tracks.length === 0) return null
  const shown = tracks.slice(0, 12)
  const withCover = tracks.filter((e) => e.cover_url).length
  return (
    <div>
      <p className="label mb-3 flex items-baseline justify-between">
        <span>En este set</span>
        <span className="timecode">
          {withCover}/{tracks.length} carátulas
        </span>
      </p>
      <ul className="grid grid-cols-6 gap-1">
        {shown.map((e, i) => (
          <li
            key={`${e.position}-${e.start_s}`}
            className="animate-rise"
            style={{ animationDelay: `${i * 45}ms` }}
          >
            <button
              type="button"
              onClick={() => onSelect(e.position)}
              title={`${e.artist} – ${e.title}`}
              aria-label={`Ir a ${e.artist} – ${e.title}`}
              className="relative block w-full transition-transform duration-300 ease-[var(--ease-out-expo)] hover:z-10 hover:scale-[1.18] focus-visible:z-10 focus-visible:scale-[1.18]"
            >
              <Cover
                url={e.cover_url}
                artist={e.artist}
                title={e.title}
                size="fill"
                rounded=""
                className="aspect-square w-full"
              />
            </button>
          </li>
        ))}
      </ul>
      {tracks.length > shown.length && (
        <p className="label mt-2 text-right">+{tracks.length - shown.length} más</p>
      )}
    </div>
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

  // La preescucha que suene se para al salir de la pantalla del set.
  useEffect(() => stopPreview, [])

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
  const title =
    job.title ?? (job.source_type === 'upload' ? fileName(job.source) : 'Leyendo metadatos…')
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
    setTab('tracklist')
    requestAnimationFrame(() =>
      document
        .getElementById(`track-${position}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
    )
  }

  const deckMode: TurntableMode =
    job.status === 'done'
      ? 'done'
      : job.status === 'queued'
        ? 'cue'
        : isActive(job.status)
          ? 'playing'
          : 'idle'

  return (
    <article className="space-y-12" aria-labelledby="job-title">
      <header>
        <div className="label flex animate-rise flex-wrap items-center gap-x-5 gap-y-2">
          <a href={href({ name: 'home' })} className="link !text-chalk">
            <span aria-hidden>←</span> Historial
          </a>
          <span aria-hidden className="h-3 w-px bg-line-strong" />
          <StatusPill status={job.status} />
          <span className="timecode text-chalk">{catalogNumber(job.id)}</span>
          <span>{sourceLabel(job.source_type)}</span>
          {job.source_type !== 'upload' && (
            <ExternalLink url={job.source} className="link hover:text-signal">
              Abrir original ↗
            </ExternalLink>
          )}
        </div>
        {/* Los títulos de YouTube pueden ser muy largos: el cuerpo baja con la longitud. */}
        <h1 id="job-title" className="mt-6 max-w-6xl [overflow-wrap:anywhere] text-balance">
          <span className="line-mask">
            <span
              className={`display ${
                title.length > 70
                  ? 'text-[clamp(2rem,3.6vw,3.6rem)]'
                  : title.length > 36
                    ? 'text-[clamp(2.4rem,4.8vw,5rem)]'
                    : 'text-[clamp(2.8rem,6.4vw,6.8rem)]'
              }`}
            >
              {title}
            </span>
          </span>
        </h1>
        {job.uploader && (
          <p className="voice mt-3 animate-rise text-[clamp(1.5rem,2.4vw,2.4rem)] text-fog [animation-delay:120ms]">
            {job.uploader}
          </p>
        )}
      </header>

      <div className="grid gap-y-8 border-t border-line lg:grid-cols-12 lg:gap-x-6">
        <RecordStage
          mode={deckMode}
          duration={job.duration_s}
          entries={entries}
          scannedS={running ? scanned : null}
          catalog={catalogNumber(job.id)}
          className="-mx-5 aspect-[1.25] animate-rise [animation-delay:100ms] sm:-mx-10 lg:col-span-7 lg:mx-0 lg:-ml-10"
          onSelect={select}
        />

        <aside
          aria-label="Estado del análisis"
          className="flex animate-rise flex-col gap-8 self-center py-8 [animation-delay:180ms] lg:col-span-5 lg:border-l lg:border-line lg:pl-10"
        >
          <Progress job={job} />

          {job.status === 'queued' && job.message && job.message !== 'En cola' && (
            <Notice tone="warn">{job.message}</Notice>
          )}
          {job.status === 'failed' && (
            <Notice tone="error">{job.error ?? 'El trabajo ha fallado.'}</Notice>
          )}
          {job.status === 'cancelled' && (
            <Notice>Trabajo cancelado. No queda audio en disco.</Notice>
          )}
          {actionError && <Notice tone="error">{actionError}</Notice>}

          {running ? (
            <NowPlaying entries={entries} />
          ) : (
            job.status === 'done' && <CoverWall entries={entries} onSelect={select} />
          )}

          {(job.status === 'done' || entries.length > 0) && <Stats job={job} tracks={tracks} />}

          <div className="flex flex-wrap gap-2">
            {running && (
              <button
                type="button"
                className="btn-danger"
                onClick={() => act(() => api.cancelJob(job.id))}
              >
                Cancelar
              </button>
            )}
            {isFinal(job.status) && (
              <button type="button" className="btn-ghost" onClick={reprocess}>
                {job.status === 'failed' ? 'Reintentar' : 'Volver a analizar'}
              </button>
            )}
            {isFinal(job.status) && (
              <button type="button" className="btn-danger ml-auto" onClick={remove}>
                Borrar
              </button>
            )}
          </div>
        </aside>
      </div>

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

      <section>
        <div className="mb-2 flex flex-wrap items-end justify-between gap-3 border-b border-line">
          {communityTotal === 0 ? (
            <h2 id="tab-tracklist" className="display pb-3 text-[clamp(2.4rem,4.4vw,4rem)]">
              Tracklist
            </h2>
          ) : (
            <div role="tablist" aria-label="Resultados" className="flex items-end gap-8">
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
                  className={`group relative flex items-start gap-2 pb-3 transition-colors duration-300 ${
                    tab === key ? 'text-chalk' : 'text-fog/50 hover:text-chalk'
                  }`}
                >
                  <span className="display text-[clamp(2.4rem,4.4vw,4rem)]">{text}</span>
                  {count !== null && (
                    <span className="timecode mt-1 text-xs text-signal">{count}</span>
                  )}
                  <span
                    aria-hidden
                    className={`absolute inset-x-0 -bottom-px h-0.5 origin-left bg-signal transition-transform duration-500 ease-[var(--ease-out-expo)] ${
                      tab === key ? 'scale-x-100' : 'scale-x-0'
                    }`}
                  />
                </button>
              ))}
            </div>
          )}
          {list?.live && running && (
            <span className="label mb-4 flex items-center gap-2 !text-signal">
              <span className="size-1.5 animate-pulse-dot rounded-full bg-signal" />
              En directo
            </span>
          )}
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
          <div
            role="tabpanel"
            id="panel-community"
            aria-labelledby="tab-community"
            hidden={tab !== 'community'}
            className="pt-6"
          >
            <CommunityPanel community={community} />
          </div>
        )}
      </section>

      {job.status === 'done' && <ExportBar jobId={job.id} />}
    </article>
  )
}

import { useEffect, useId, useMemo, useState, type FormEvent } from 'react'

import { api, BridgeError } from '../api/bridge'
import type { Entry, Job } from '../api/types'
import { Cover } from '../components/Cover'
import { RecordStage } from '../components/RecordStage'
import { StaticRecord } from '../components/StaticRecord'
import { Notice, Spinner, StatusPill } from '../components/ui'
import { catalogNumber, fileName, formatDuration, formatRelative, sourceLabel } from '../lib/format'
import { href, navigate } from '../lib/router'
import { useJobs } from '../state/context'
import { grooveBands } from '../three/model'

function jobTitle(job: Job): string {
  return job.title ?? (job.source_type === 'upload' ? fileName(job.source) : job.source)
}

/** Barra de órdenes flotante: enlace + identificar + archivo propio. */
function CommandBar({ onCue }: { onCue(cueing: boolean): void }) {
  const inputId = useId()
  const errorId = useId()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [focused, setFocused] = useState(false)

  // Con un enlace escrito (o el campo activo), el brazo se levanta y se acerca al disco.
  useEffect(() => onCue(focused || url.trim().length > 0), [focused, url, onCue])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const job = await api.createJob(url.trim())
      navigate({ name: 'job', id: job.id })
    } catch (err) {
      setError(err instanceof BridgeError ? err.message : 'No se pudo crear el trabajo.')
    } finally {
      setBusy(false)
    }
  }

  const pick = async () => {
    setError(null)
    try {
      const job = await api.pickFile()
      if (job) navigate({ name: 'job', id: job.id })
    } catch (err) {
      setError(err instanceof BridgeError ? err.message : 'No se pudo abrir el archivo.')
    }
  }

  return (
    <div className="w-full max-w-xl">
      <form onSubmit={submit} noValidate>
        <label htmlFor={inputId} className="label flex items-center gap-3">
          <span className="text-signal">01</span>
          Enlace de YouTube o SoundCloud
        </label>
        <div
          className={`mt-3 flex items-stretch border transition-colors duration-300 ${
            focused ? 'border-signal' : 'border-line-strong'
          }`}
        >
          <input
            id={inputId}
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="https://…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            className="timecode min-w-0 flex-1 bg-transparent px-4 py-4 text-[0.95rem] text-chalk placeholder:text-fog/50 focus:outline-none"
          />
          <button
            type="submit"
            className="group/go flex shrink-0 items-center gap-3 bg-paper px-6 font-mono text-[0.72rem] font-medium tracking-[0.12em] text-ink uppercase transition-colors duration-200 hover:bg-signal disabled:cursor-not-allowed disabled:bg-deck disabled:text-fog"
            disabled={!url.trim() || busy}
          >
            {busy ? 'Comprobando…' : 'Identificar'}
            <span
              aria-hidden
              className="transition-transform duration-300 ease-[var(--ease-out-expo)] group-hover/go:translate-x-1"
            >
              →
            </span>
          </button>
        </div>
      </form>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        <button
          type="button"
          onClick={pick}
          onPointerEnter={() => onCue(true)}
          onPointerLeave={() => onCue(focused || url.trim().length > 0)}
          className="label link flex items-center gap-3 !text-chalk"
          title="Recomendado: arrástralo a la ventana o haz clic para elegirlo."
        >
          <span className="text-signal">02</span>
          Usa tu propio archivo
          <span aria-hidden>↑</span>
        </button>
        <p className="text-xs text-fog">
          {error ? (
            <span id={errorId} role="alert" className="text-bad">
              {error}
            </span>
          ) : (
            'o suéltalo en cualquier parte de la ventana.'
          )}
        </p>
      </div>
    </div>
  )
}

/** La funda de un set: un mosaico con sus carátulas y el disco asomando por la derecha. */
function Sleeve({
  job,
  entries,
  index,
}: {
  job: Job
  entries: Entry[] | undefined
  index: number
}) {
  const bands = useMemo(() => grooveBands(entries ?? [], job.duration_s), [entries, job.duration_s])
  const identified = entries?.filter((e) => e.source !== 'unknown') ?? []
  const covers = useMemo(() => {
    const seen = new Set<string>()
    const out: Entry[] = []
    for (const e of entries ?? []) {
      if (!e.cover_url || seen.has(e.cover_url)) continue
      seen.add(e.cover_url)
      out.push(e)
    }
    return out
  }, [entries])
  const mosaic = covers.length >= 4 ? covers.slice(0, 4) : covers.slice(0, 1)
  return (
    <li className="animate-rise" style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}>
      <a href={href({ name: 'job', id: job.id })} className="group block">
        <span className="relative block aspect-square">
          {/* El disco: asoma un poco y sale de la funda al pasar el ratón. */}
          <span
            aria-hidden
            className="absolute inset-y-[4%] right-0 aspect-square translate-x-[14%] transition-transform duration-700 ease-[var(--ease-out-expo)] will-change-transform group-hover:translate-x-[46%] group-hover:rotate-[70deg] group-focus-visible:translate-x-[46%]"
          >
            <StaticRecord bands={bands} cover={covers[0]?.cover_url} className="size-full" />
          </span>
          <span className="relative z-10 block size-full overflow-hidden border border-line bg-deck shadow-[8px_0_24px_-8px_rgb(0_0_0/0.9)]">
            {mosaic.length > 0 ? (
              <span className={`grid size-full ${mosaic.length === 4 ? 'grid-cols-2' : ''}`}>
                {mosaic.map((e) => (
                  <Cover
                    key={e.cover_url}
                    url={e.cover_url}
                    artist={e.artist}
                    title={e.title}
                    size="fill"
                    rounded=""
                    className="size-full !ring-0"
                  />
                ))}
              </span>
            ) : (
              <span className="hatch flex size-full flex-col justify-between p-4">
                <span className="label">{sourceLabel(job.source_type)}</span>
                <span className="display text-[clamp(2.5rem,5vw,4.5rem)] text-chalk/25">
                  {catalogNumber(job.id).replace('SID-', '')}
                </span>
              </span>
            )}
            <span className="timecode absolute left-0 top-0 bg-ink px-2 py-1 text-[0.62rem] tracking-[0.12em] text-chalk">
              {catalogNumber(job.id)}
            </span>
          </span>
        </span>
        <span className="mt-4 block">
          <span className="line-clamp-2 text-[0.95rem] leading-snug font-medium text-chalk">
            {jobTitle(job)}
          </span>
          <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fog">
            <StatusPill status={job.status} />
            {job.duration_s !== null && (
              <span className="timecode">{formatDuration(job.duration_s)}</span>
            )}
            {entries !== undefined && job.status === 'done' && (
              <span>{identified.length} tracks</span>
            )}
            <span className="ml-auto">{formatRelative(job.created_at)}</span>
          </span>
        </span>
      </a>
    </li>
  )
}

/** Cinta con los últimos tracks identificados, como el rótulo en marcha de una cabina. */
function Ticker({ tracks }: { tracks: Entry[] }) {
  if (tracks.length < 3) return null
  const run = (hidden: boolean) => (
    <span aria-hidden={hidden || undefined} className="flex shrink-0 items-center">
      {tracks.map((e, i) => (
        <span key={i} className="flex items-center whitespace-nowrap">
          <span className="display px-5 text-2xl text-chalk/85">{e.artist}</span>
          <span className="voice text-2xl text-fog">{e.title}</span>
          <span className="px-5 text-signal">✳</span>
        </span>
      ))}
    </span>
  )
  return (
    <div
      aria-label="Últimos tracks identificados"
      className="relative left-1/2 w-screen -translate-x-1/2 overflow-hidden border-y border-line py-4"
    >
      <div
        className="flex w-max animate-marquee will-change-transform hover:[animation-play-state:paused]"
        style={{ animationDuration: `${Math.max(30, tracks.length * 6)}s` }}
      >
        {run(false)}
        {run(true)}
      </div>
    </div>
  )
}

/** Carga los tracklists de los últimos sets para dibujar sus discos y el del plato. */
function useRecentTracklists(jobs: Job[]): Record<number, { entries: Entry[] } | undefined> {
  const { tracklists, loadDetail } = useJobs()
  const pending = jobs
    .filter((j) => j.status === 'done' && !tracklists[j.id])
    .map((j) => j.id)
    .join(',')
  useEffect(() => {
    if (!pending) return
    for (const id of pending.split(',').map(Number)) void loadDetail(id).catch(() => {})
  }, [pending, loadDetail])
  return tracklists
}

export function Home() {
  const { sortedJobs, loaded, error, refresh } = useJobs()
  const [cueing, setCueing] = useState(false)
  const recent = sortedJobs.slice(0, 12)
  const tracklists = useRecentTracklists(recent)
  const deck = sortedJobs.find((j) => j.status === 'done') ?? null
  const deckEntries = deck ? (tracklists[deck.id]?.entries ?? []) : []

  const ticker = useMemo(() => {
    const out: Entry[] = []
    for (const job of recent) {
      for (const e of tracklists[job.id]?.entries ?? []) {
        if (e.source !== 'unknown' && out.length < 24) out.push(e)
      }
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps -- depende de los tracklists cargados
  }, [tracklists, sortedJobs])

  return (
    <div className="space-y-16">
      <section
        aria-labelledby="hero"
        className="grid items-center gap-y-6 lg:grid-cols-12 lg:gap-x-6"
      >
        <div className="relative z-10 lg:col-span-5">
          <p className="label flex animate-rise items-center gap-3">
            <span className="size-1.5 animate-pulse-dot rounded-full bg-signal" />
            Huella acústica
            <span aria-hidden className="h-px w-8 bg-line-strong" />
            Tracklist de la comunidad
          </p>
          <h1 id="hero" className="mt-7">
            <span className="line-mask">
              <span className="display text-[clamp(4.2rem,9.4vw,10rem)]">¿Qué está</span>
            </span>{' '}
            <span className="line-mask -mt-[0.06em]">
              <span className="voice text-[clamp(4rem,9vw,9.6rem)] leading-[0.9] text-signal [animation-delay:90ms]">
                pinchando?
              </span>
            </span>
          </h1>
          <p className="mt-7 max-w-md animate-rise text-[1.05rem] leading-relaxed text-fog [animation-delay:220ms]">
            Pega un set y SetID lo escucha de principio a fin. Te devuelve cada track con su marca
            de tiempo, su sello, su carátula y dónde encontrarlo.
          </p>
          <div className="mt-10 animate-rise [animation-delay:300ms]">
            <CommandBar onCue={setCueing} />
          </div>
        </div>

        <figure className="relative -mx-5 animate-rise [animation-delay:160ms] sm:-mx-10 lg:col-span-7 lg:mx-0 lg:-mr-10">
          <RecordStage
            mode={cueing ? 'cue' : 'idle'}
            duration={deck?.duration_s ?? null}
            entries={deckEntries}
            scannedS={null}
            catalog={deck ? catalogNumber(deck.id) : 'SID-000'}
            className="aspect-[4/3] w-full lg:aspect-[1.12]"
            onSelect={() => deck && navigate({ name: 'job', id: deck.id })}
          />
          {deck && (
            <figcaption className="absolute right-5 bottom-4 max-w-64 border-l border-signal pl-3 sm:right-10">
              <span className="label text-signal">En el plato</span>
              <a
                href={href({ name: 'job', id: deck.id })}
                className="link mt-1 block truncate text-sm text-chalk/85 hover:text-chalk"
              >
                {jobTitle(deck)}
              </a>
            </figcaption>
          )}
        </figure>
      </section>

      <Ticker tracks={ticker} />

      <section aria-labelledby="history">
        <div className="mb-8 flex items-end justify-between gap-6 border-b border-line pb-4">
          <h2 id="history" className="display text-[clamp(2.4rem,4.4vw,4rem)]">
            La caja <span className="voice text-fog">de discos</span>
          </h2>
          {sortedJobs.length > 0 && (
            <span className="label pb-1">
              {String(sortedJobs.length).padStart(2, '0')}{' '}
              {sortedJobs.length === 1 ? 'set' : 'sets'}
            </span>
          )}
        </div>
        {!loaded && <Spinner label="Cargando historial" />}
        {loaded && error && (
          <Notice
            tone="error"
            action={
              <button type="button" className="btn-ghost" onClick={() => void refresh()}>
                Reintentar
              </button>
            }
          >
            {error}
          </Notice>
        )}
        {loaded && !error && sortedJobs.length === 0 && (
          <div className="hatch flex flex-col items-start gap-5 border border-line px-8 py-12 sm:flex-row sm:items-center">
            <StaticRecord bands={[]} className="size-24 shrink-0 animate-spin-slow opacity-80" />
            <p className="max-w-md text-fog">
              <span className="display mb-2 block text-2xl text-chalk">Caja vacía</span>
              Aún no has analizado ningún set. Pega un enlace arriba o suelta un archivo en la
              ventana.
            </p>
          </div>
        )}
        {sortedJobs.length > 0 && (
          <ul className="grid grid-cols-2 gap-x-10 gap-y-12 pr-6 md:grid-cols-3 xl:grid-cols-4">
            {recent.map((job, i) => (
              <Sleeve key={job.id} job={job} entries={tracklists[job.id]?.entries} index={i} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

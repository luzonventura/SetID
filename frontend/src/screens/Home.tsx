import { useId, useState, type FormEvent } from 'react'

import { api, BridgeError } from '../api/bridge'
import type { Job } from '../api/types'
import { Notice, Spinner, StatusPill } from '../components/ui'
import { fileName, formatDuration, formatRelative, sourceLabel } from '../lib/format'
import { href, navigate } from '../lib/router'
import { useJobs } from '../state/context'

function SubmitForm() {
  const inputId = useId()
  const errorId = useId()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    <div className="grid gap-6 lg:grid-cols-[1fr_17rem]">
      <form onSubmit={submit} className="animate-rise [animation-delay:120ms]" noValidate>
        <label htmlFor={inputId} className="label">
          Enlace de YouTube o SoundCloud
        </label>
        <div className="mt-3 flex flex-col gap-3 border-b-2 border-line-strong pb-3 focus-within:border-signal sm:flex-row sm:items-end">
          <input
            id={inputId}
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="https://youtu.be/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            className="timecode min-w-0 flex-1 bg-transparent py-2 text-lg text-chalk placeholder:text-fog/50 focus:outline-none sm:text-2xl"
          />
          <button type="submit" className="btn-primary px-6 py-3" disabled={!url.trim() || busy}>
            {busy ? 'Comprobando…' : 'Identificar'}
            <span aria-hidden>→</span>
          </button>
        </div>
        {error && (
          <p id={errorId} role="alert" className="mt-3 text-sm text-bad">
            {error}
          </p>
        )}
      </form>

      <button
        type="button"
        onClick={pick}
        className="group animate-rise border border-dashed border-line-strong p-5 text-left transition-colors [animation-delay:200ms] hover:border-signal hover:bg-signal-soft"
      >
        <span className="label group-hover:text-signal">Recomendado</span>
        <span className="mt-2 block text-lg font-semibold [font-stretch:115%]">
          Usa tu propio archivo
        </span>
        <span className="mt-1 block text-sm text-fog">
          Arrástralo a la ventana o haz clic para elegirlo.
        </span>
      </button>
    </div>
  )
}

function HistoryRow({ job }: { job: Job }) {
  const title = job.title ?? (job.source_type === 'upload' ? fileName(job.source) : job.source)
  return (
    <li>
      <a
        href={href({ name: 'job', id: job.id })}
        className="group grid grid-cols-[1fr_auto] items-center gap-x-6 gap-y-1 border-b border-line py-4 transition-colors hover:border-line-strong sm:grid-cols-[7rem_1fr_8rem_6rem]"
      >
        <span className="order-3 sm:order-none">
          <StatusPill status={job.status} />
        </span>
        <span className="min-w-0">
          <span className="block truncate font-semibold group-hover:text-signal">{title}</span>
          <span className="label block truncate normal-case tracking-normal">
            {sourceLabel(job.source_type)}
            {job.uploader ? ` · ${job.uploader}` : ''}
            {job.cached ? ' · caché' : ''}
          </span>
        </span>
        <span className="timecode hidden text-sm text-fog sm:block">
          {formatDuration(job.duration_s)}
        </span>
        <span className="label order-4 text-right normal-case tracking-normal sm:order-none">
          {formatRelative(job.created_at)}
        </span>
      </a>
    </li>
  )
}

export function Home() {
  const { sortedJobs, loaded, error, refresh } = useJobs()

  return (
    <div className="space-y-16">
      <section aria-labelledby="hero" className="relative">
        <p className="label animate-rise">Extractor de tracklists</p>
        <h1 id="hero" className="display mt-4 animate-rise text-[clamp(3rem,10vw,8.5rem)] [animation-delay:60ms]">
          ¿Qué está
          <br />
          <span className="text-signal">pinchando?</span>
        </h1>
        <div className="mt-10">
          <SubmitForm />
        </div>
      </section>

      <section aria-labelledby="history" className="animate-rise [animation-delay:280ms]">
        <div className="flex items-baseline justify-between border-b border-line-strong pb-3">
          <h2 id="history" className="display text-2xl">
            Historial
          </h2>
          {sortedJobs.length > 0 && <span className="label">{sortedJobs.length} sets</span>}
        </div>
        {!loaded && <Spinner label="Cargando historial" />}
        {loaded && error && (
          <div className="mt-4">
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
          </div>
        )}
        {loaded && !error && sortedJobs.length === 0 && (
          <p className="py-10 text-fog">
            Aún no has analizado ningún set. Pega un enlace arriba o suelta un archivo en la
            ventana.
          </p>
        )}
        {sortedJobs.length > 0 && (
          <ul>
            {sortedJobs.slice(0, 20).map((job) => (
              <HistoryRow key={job.id} job={job} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

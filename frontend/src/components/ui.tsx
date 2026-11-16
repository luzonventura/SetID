// Piezas pequeñas compartidas.

import type { ReactNode } from 'react'

import { api } from '../api/bridge'
import type { JobStatus } from '../api/types'

const STATUS_TEXT: Record<JobStatus, string> = {
  queued: 'En cola',
  downloading: 'Descargando',
  analyzing: 'Analizando',
  aggregating: 'Agrupando',
  done: 'Listo',
  failed: 'Error',
  cancelled: 'Cancelado',
}

// Como el piloto de un equipo: un LED y su rótulo, sin cápsula alrededor.
const STATUS_STYLE: Record<JobStatus, { dot: string; pill: string }> = {
  queued: { dot: 'bg-fog', pill: 'text-fog' },
  downloading: { dot: 'bg-signal', pill: 'text-signal' },
  analyzing: { dot: 'bg-signal', pill: 'text-signal' },
  aggregating: { dot: 'bg-signal', pill: 'text-signal' },
  done: { dot: 'bg-ok', pill: 'text-ok' },
  failed: { dot: 'bg-bad', pill: 'text-bad' },
  cancelled: { dot: 'bg-fog/60', pill: 'text-fog' },
}

export function StatusPill({ status }: { status: JobStatus }) {
  const live = status === 'downloading' || status === 'analyzing' || status === 'aggregating'
  const style = STATUS_STYLE[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[0.65rem] font-medium tracking-[0.14em] uppercase ${style.pill}`}
    >
      <span
        aria-hidden
        className={`size-1.5 rounded-full ${style.dot} ${live ? 'animate-pulse-dot' : ''}`}
      />
      <span>{STATUS_TEXT[status]}</span>
    </span>
  )
}

/** Enlace que se abre en el navegador del sistema (nunca dentro de la ventana de la app). */
export function ExternalLink({
  url,
  children,
  className = '',
  label,
}: {
  url: string
  children: ReactNode
  className?: string
  label?: string
}) {
  return (
    <a
      href={url}
      aria-label={label}
      className={className}
      rel="noreferrer noopener"
      onClick={(e) => {
        e.preventDefault()
        void api.openExternal(url)
      }}
    >
      {children}
    </a>
  )
}

export function Notice({
  tone = 'info',
  children,
  action,
}: {
  tone?: 'info' | 'error' | 'warn'
  children: ReactNode
  action?: ReactNode
}) {
  const colors = {
    info: 'border-l-fog text-chalk',
    warn: 'border-l-warn text-warn',
    error: 'border-l-bad text-bad',
  }[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex flex-wrap items-center justify-between gap-3 border border-l-2 border-line bg-booth px-4 py-3 text-sm ${colors}`}
    >
      <div>{children}</div>
      {action}
    </div>
  )
}

export function Spinner({ label = 'Cargando' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-10 text-fog">
      <span className="relative h-px w-24 overflow-hidden bg-line-strong">
        <span className="absolute inset-y-0 w-1/4 animate-scan bg-signal" />
      </span>
      <span className="label">{label}</span>
    </div>
  )
}

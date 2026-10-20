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

const STATUS_COLOR: Record<JobStatus, string> = {
  queued: 'bg-fog',
  downloading: 'bg-signal',
  analyzing: 'bg-signal',
  aggregating: 'bg-signal',
  done: 'bg-ok',
  failed: 'bg-bad',
  cancelled: 'bg-line-strong',
}

export function StatusPill({ status }: { status: JobStatus }) {
  const live = status === 'downloading' || status === 'analyzing' || status === 'aggregating'
  return (
    <span className="label inline-flex items-center gap-2 text-chalk">
      <span
        aria-hidden
        className={`size-2 rounded-full ${STATUS_COLOR[status]} ${live ? 'animate-pulse-dot' : ''}`}
      />
      {STATUS_TEXT[status]}
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
    info: 'border-line-strong text-chalk',
    warn: 'border-warn/60 text-warn',
    error: 'border-bad/60 text-bad',
  }[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex flex-wrap items-center justify-between gap-3 border-l-2 bg-booth px-4 py-3 text-sm ${colors}`}
    >
      <div>{children}</div>
      {action}
    </div>
  )
}

export function Spinner({ label = 'Cargando' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-10 text-fog">
      <span className="relative h-0.5 w-24 overflow-hidden bg-line">
        <span className="absolute inset-y-0 w-1/4 animate-scan bg-signal" />
      </span>
      <span className="label">{label}</span>
    </div>
  )
}

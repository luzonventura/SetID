// Carátula que, si el track tiene preescucha, es también el botón para escucharla.
//
// Discreto: una pastilla redonda en la esquina con ▶. Al pasar el ratón se enciende en azul;
// mientras suena muestra un ecualizador y un anillo con el progreso, y al pasar por encima
// cambia a pausa.

import { safePreviewUrl } from '../lib/cover'
import { togglePreview, usePreview, type PreviewStatus } from '../lib/preview'
import { Cover } from './Cover'

const RING = 2 * Math.PI * 10.5 // circunferencia del anillo de progreso (r = 10,5)

function Play({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`size-[9px] translate-x-[0.5px] ${className}`} aria-hidden>
      <path d="M6 3.5v17l15-8.5z" fill="currentColor" />
    </svg>
  )
}

function Pause({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`size-[9px] ${className}`} aria-hidden>
      <rect x="5" y="4" width="5" height="16" fill="currentColor" />
      <rect x="14" y="4" width="5" height="16" fill="currentColor" />
    </svg>
  )
}

/** Tres barras que laten mientras suena (quietas si se pide menos movimiento). */
function Equalizer({ className = '' }: { className?: string }) {
  return (
    <span aria-hidden className={`flex h-[9px] items-end gap-[1.5px] ${className}`}>
      {[0, 180, 90].map((delay) => (
        <span
          key={delay}
          className="h-full w-[2px] origin-bottom animate-eq bg-current"
          style={{ animationDelay: `-${delay}ms` }}
        />
      ))}
    </span>
  )
}

function Glyph({ status }: { status: PreviewStatus }) {
  if (status === 'loading') {
    return (
      <span className="size-[11px] animate-spin rounded-full border-[1.5px] border-current border-t-transparent" />
    )
  }
  if (status === 'error') return <span className="font-mono text-[10px] font-bold">!</span>
  if (status === 'playing') {
    // Suena: ecualizador; al pasar por encima, pausa.
    return (
      <>
        <Equalizer className="group-hover/pv:hidden group-focus-visible/pv:hidden" />
        <Pause className="hidden group-hover/pv:block group-focus-visible/pv:block" />
      </>
    )
  }
  return <Play />
}

export function PreviewCover({
  url,
  previewUrl,
  artist,
  title,
  size,
  className = '',
}: {
  url: string | null | undefined
  previewUrl: string | null | undefined
  artist: string
  title: string
  size: number
  className?: string
}) {
  const preview = safePreviewUrl(previewUrl)
  const { status, progress } = usePreview(preview)
  const cover = <Cover url={url} artist={artist} title={title} size={size} />

  if (!preview) {
    return (
      <span className={`block shrink-0 ${className}`} title="Sin preescucha">
        {cover}
      </span>
    )
  }

  const busy = status === 'playing' || status === 'loading'
  const name = `${artist} – ${title}`
  const label = busy
    ? `Pausar la preescucha de ${name}`
    : status === 'error'
      ? `No se pudo reproducir ${name}. Reintentar`
      : `Escuchar la preescucha de ${name}`

  const chip =
    status === 'error'
      ? 'bg-bad text-ink'
      : busy || status === 'paused'
        ? 'bg-ink/85 text-signal group-hover/pv:bg-signal group-hover/pv:text-ink'
        : 'bg-ink/75 text-paper group-hover/pv:bg-signal group-hover/pv:text-ink group-focus-visible/pv:bg-signal group-focus-visible/pv:text-ink'

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        togglePreview(preview)
      }}
      aria-label={label}
      aria-pressed={busy}
      title={label}
      className={`group/pv relative block shrink-0 cursor-pointer ${className}`}
    >
      {cover}
      {/* Mientras suena, la carátula se oscurece un poco para que destaque el control. */}
      <span
        aria-hidden
        className={`pointer-events-none absolute inset-0 bg-ink transition-opacity duration-300 ${
          busy ? 'opacity-25' : 'opacity-0'
        }`}
      />
      <span
        aria-hidden
        className={`absolute right-[3px] bottom-[3px] grid size-[22px] place-items-center rounded-full shadow-[0_1px_6px_rgb(0_0_0/0.55)] ring-1 ring-white/15 transition-[background-color,color,scale] duration-200 ease-out group-hover/pv:scale-110 group-focus-visible/pv:scale-110 ${chip}`}
      >
        {/* Anillo de progreso alrededor de la pastilla. */}
        {(busy || status === 'paused') && (
          <svg viewBox="0 0 24 24" className="absolute inset-[-1px] -rotate-90" aria-hidden>
            <circle
              cx="12"
              cy="12"
              r="10.5"
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.9"
              strokeWidth="1.5"
              strokeDasharray={RING}
              strokeDashoffset={RING * (1 - progress)}
              className="transition-[stroke-dashoffset] duration-300 ease-linear"
            />
          </svg>
        )}
        <Glyph status={status} />
      </span>
    </button>
  )
}

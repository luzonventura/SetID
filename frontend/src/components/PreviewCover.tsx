// Carátula que, si el track tiene preescucha, es también el botón para escucharla: al pasar
// el ratón aparece ▶, mientras suena muestra ❚❚ y una barra de progreso en su borde inferior.

import { safePreviewUrl } from '../lib/cover'
import { togglePreview, usePreview } from '../lib/preview'
import { Cover } from './Cover'

function Icon({ status }: { status: string }) {
  if (status === 'loading') {
    return (
      <span className="size-5 animate-spin rounded-full border-2 border-paper/30 border-t-paper" />
    )
  }
  if (status === 'playing') {
    return (
      <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
        <rect x="6" y="5" width="4" height="14" fill="currentColor" />
        <rect x="14" y="5" width="4" height="14" fill="currentColor" />
      </svg>
    )
  }
  if (status === 'error') {
    return <span className="display text-xl">!</span>
  }
  return (
    <svg viewBox="0 0 24 24" className="ml-0.5 size-5" aria-hidden>
      <path d="M7 4.5v15l13-7.5z" fill="currentColor" />
    </svg>
  )
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

  const active = status !== 'idle'
  const name = `${artist} – ${title}`
  const label =
    status === 'playing' || status === 'loading'
      ? `Pausar la preescucha de ${name}`
      : status === 'error'
        ? `No se pudo reproducir ${name}. Reintentar`
        : `Escuchar la preescucha de ${name}`

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        togglePreview(preview)
      }}
      aria-label={label}
      aria-pressed={status === 'playing' || status === 'loading'}
      title={label}
      className={`group/pv relative block shrink-0 cursor-pointer ${className}`}
    >
      {cover}
      <span
        aria-hidden
        className={`absolute inset-0 grid place-items-center bg-ink/60 text-paper transition-opacity duration-200 ${
          active
            ? 'opacity-100'
            : 'opacity-0 group-hover/pv:opacity-100 group-focus-visible/pv:opacity-100'
        }`}
      >
        <Icon status={status} />
      </span>
      {active && (
        <span aria-hidden className="absolute inset-x-0 bottom-0 h-[3px] bg-ink/70">
          <span
            className="block h-full origin-left bg-signal transition-transform duration-300 ease-linear"
            style={{ transform: `scaleX(${progress})` }}
          />
        </span>
      )}
    </button>
  )
}

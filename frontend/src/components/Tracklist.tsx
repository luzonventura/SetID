import type { Entry } from '../api/types'
import { confidenceLevel, formatTime } from '../lib/format'
import { Suggestions } from './Community'
import { Cover } from './Cover'
import { ExternalLink } from './ui'

const LEVEL_TEXT = { high: 'alta', medium: 'media', low: 'baja' }
const LEVEL_COLOR = { high: 'bg-signal', medium: 'bg-signal/60', low: 'bg-warn/80' }

function ConfidenceMeter({ value, detections }: { value: number | null; detections: number }) {
  if (value === null) return null
  const level = confidenceLevel(value)
  const filled = Math.max(1, Math.round(value * 5))
  return (
    <span
      className="inline-flex items-end gap-[3px]"
      role="img"
      aria-label={`Confianza ${LEVEL_TEXT[level]} (${value.toFixed(2)}), ${detections} segmentos`}
      title={`Confianza ${value.toFixed(2)} · ${detections} segmentos`}
    >
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={`w-[3px] ${i < filled ? LEVEL_COLOR[level] : 'bg-line-strong'}`}
          style={{ height: `${6 + i * 3}px` }}
        />
      ))}
    </span>
  )
}

function Timestamp({ entry, withHours }: { entry: Entry; withHours: boolean }) {
  const text = formatTime(entry.start_s, withHours)
  const base = 'timecode text-sm'
  if (!entry.timestamp_url) return <span className={`${base} text-fog`}>{text}</span>
  return (
    <ExternalLink
      url={entry.timestamp_url}
      label={`Abrir el set en ${text}`}
      className={`${base} link w-fit text-chalk transition-colors hover:text-signal`}
    >
      {text}
    </ExternalLink>
  )
}

function SearchLinks({ entry }: { entry: Entry }) {
  if (!entry.search) return null
  const name = `${entry.artist} – ${entry.title}`
  const search = entry.search
  const links: [keyof typeof search, string, string][] = [
    ['beatport', 'BP', 'Beatport'],
    ['spotify', 'SP', 'Spotify'],
    ['youtube', 'YT', 'YouTube'],
  ]
  return (
    <span className="flex gap-px opacity-60 transition-opacity duration-300 group-hover:opacity-100">
      {links.map(([key, short, site]) => (
        <ExternalLink
          key={key}
          url={search[key]}
          label={`Buscar ${name} en ${site}`}
          className="timecode grid size-8 place-items-center border border-line-strong text-[0.62rem] tracking-[0.08em] text-fog transition-colors duration-200 hover:border-paper hover:bg-paper hover:text-ink"
        >
          {short}
        </ExternalLink>
      ))}
    </span>
  )
}

export function Tracklist({
  entries,
  live,
  highlight,
}: {
  entries: Entry[]
  live: boolean
  highlight: number | null
}) {
  const withHours = entries.some((e) => e.start_s >= 3600)

  if (entries.length === 0) {
    return (
      <p className="hatch border-b border-line px-5 py-14 text-center text-fog">
        {live
          ? 'Los tracks aparecerán aquí según se vayan identificando.'
          : 'No se ha identificado ningún track en este set.'}
      </p>
    )
  }

  return (
    <ol aria-label="Tracklist" aria-live={live ? 'polite' : undefined}>
      {entries.map((e, i) => {
        const unknown = e.source === 'unknown'
        const active = highlight === e.position
        return (
          <li
            key={`${e.position}-${e.start_s}`}
            id={`track-${e.position}`}
            style={live ? undefined : { animationDelay: `${Math.min(i, 14) * 35}ms` }}
            className={`group relative grid animate-rise scroll-mt-24 grid-cols-[2.75rem_4rem_1fr] items-center gap-x-5 gap-y-2 border-b border-line px-2 py-3.5 transition-colors duration-300 sm:grid-cols-[3.5rem_4.5rem_1fr_auto_auto] ${
              unknown ? 'hatch' : 'hover:bg-booth'
            } ${active ? '!bg-signal/[0.08]' : ''}`}
          >
            {/* Filete que se dibuja en el borde al pasar o al seleccionar desde el disco. */}
            <span
              aria-hidden
              className={`absolute inset-y-0 left-0 w-0.5 origin-top bg-signal transition-transform duration-500 ease-[var(--ease-out-expo)] ${
                active ? 'scale-y-100' : 'scale-y-0 group-hover:scale-y-100'
              }`}
            />
            <span
              className={`display text-[1.9rem] transition-colors duration-300 ${
                active ? 'text-signal' : 'text-chalk/20 group-hover:text-chalk/60'
              }`}
            >
              {String(e.position).padStart(2, '0')}
            </span>
            <Timestamp entry={e} withHours={withHours} />
            {unknown ? (
              <span className="flex min-w-0 items-center gap-4">
                <span
                  aria-hidden
                  className="voice grid size-12 shrink-0 place-items-center border border-dashed border-line-strong text-2xl text-fog/70"
                >
                  ?
                </span>
                <span className="min-w-0">
                  <span className="display text-xl text-fog">ID – ID</span>
                  <span className="ml-3 text-xs text-fog/80">
                    sin identificar · {formatTime(e.end_s - e.start_s)}
                  </span>
                </span>
              </span>
            ) : (
              <span className="flex min-w-0 items-center gap-4">
                <Cover
                  url={e.cover_url}
                  artist={e.artist}
                  title={e.title}
                  size={48}
                  rounded="rounded-[2px]"
                  className="transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover:scale-[1.08]"
                />
                <span className="min-w-0">
                  <span className="block truncate text-[1.02rem] font-medium text-chalk">
                    {e.artist}
                  </span>
                  <span className="flex min-w-0 items-baseline gap-3">
                    <span className="truncate text-sm text-chalk/65">{e.title}</span>
                    {e.label && (
                      <span className="label hidden shrink-0 !text-[0.6rem] md:inline">
                        {e.label}
                      </span>
                    )}
                  </span>
                </span>
              </span>
            )}
            <span className="col-start-3 sm:col-start-auto">
              {!unknown && <ConfidenceMeter value={e.confidence} detections={e.detections} />}
            </span>
            <span className="col-start-3 sm:col-start-auto">
              <SearchLinks entry={e} />
            </span>
            {unknown && <Suggestions hints={e.suggestions ?? []} />}
          </li>
        )
      })}
    </ol>
  )
}

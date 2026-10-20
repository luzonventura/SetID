import type { Entry } from '../api/types'
import { confidenceLevel, formatTime } from '../lib/format'
import { Suggestions } from './Community'
import { ExternalLink } from './ui'

const LEVEL_TEXT = { high: 'alta', medium: 'media', low: 'baja' }
const LEVEL_COLOR = { high: 'bg-ok', medium: 'bg-warn', low: 'bg-bad' }

export function ConfidenceMeter({
  value,
  detections,
}: {
  value: number | null
  detections: number
}) {
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
          className={`w-[5px] ${i < filled ? LEVEL_COLOR[level] : 'bg-line-strong'}`}
          style={{ height: `${6 + i * 3}px` }}
        />
      ))}
    </span>
  )
}

function Timestamp({ entry, withHours }: { entry: Entry; withHours: boolean }) {
  const text = formatTime(entry.start_s, withHours)
  if (!entry.timestamp_url) return <span className="timecode text-sm text-fog">{text}</span>
  return (
    <ExternalLink
      url={entry.timestamp_url}
      label={`Abrir el set en ${text}`}
      className="timecode text-sm text-chalk underline decoration-line-strong underline-offset-4 hover:text-signal hover:decoration-signal"
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
    <span className="flex gap-1">
      {links.map(([key, short, site]) => (
        <ExternalLink
          key={key}
          url={search[key]}
          label={`Buscar ${name} en ${site}`}
          className="timecode grid h-7 w-8 place-items-center border border-line-strong text-[10px] text-fog transition-colors hover:border-signal hover:text-signal"
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
      <p className="border border-dashed border-line px-5 py-10 text-center text-fog">
        {live
          ? 'Los tracks aparecerán aquí según se vayan identificando.'
          : 'No se ha identificado ningún track en este set.'}
      </p>
    )
  }

  return (
    <ol
      aria-label="Tracklist"
      aria-live={live ? 'polite' : undefined}
      className="border-t border-line"
    >
      {entries.map((e) => {
        const unknown = e.source === 'unknown'
        return (
          <li
            key={`${e.position}-${e.start_s}`}
            id={`track-${e.position}`}
            className={`grid scroll-mt-24 grid-cols-[2.5rem_4.5rem_1fr] items-center gap-x-4 gap-y-2 border-b border-line px-1 py-3.5 transition-colors sm:grid-cols-[2.5rem_5rem_1fr_auto_auto] ${
              unknown ? 'hatch' : ''
            } ${highlight === e.position ? 'bg-signal-soft' : ''} ${live ? 'animate-rise' : ''}`}
          >
            <span className="timecode text-xs text-fog">{String(e.position).padStart(2, '0')}</span>
            <Timestamp entry={e} withHours={withHours} />
            {unknown ? (
              <span className="min-w-0">
                <span className="display text-base tracking-wider text-fog">ID – ID</span>
                <span className="label ml-3 normal-case tracking-normal">
                  sin identificar · {formatTime(e.end_s - e.start_s)}
                </span>
              </span>
            ) : (
              <span className="min-w-0">
                <span className="block truncate font-semibold [font-stretch:110%]">{e.artist}</span>
                <span className="block truncate text-sm text-chalk/80">
                  {e.title}
                  {e.label && (
                    <span className="label ml-2 normal-case tracking-normal">· {e.label}</span>
                  )}
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

// Vista general del set, como la forma de onda resumida de un CDJ: un bloque por track,
// los ID – ID rayados y, mientras se analiza, el cabezal avanzando.

import type { Entry } from '../api/types'
import { confidenceLevel, formatTime } from '../lib/format'

const FILL = { high: 'bg-signal', medium: 'bg-signal/65', low: 'bg-signal/35' }

function ticks(duration: number): number[] {
  const step = duration > 2 * 3600 ? 1800 : duration > 3600 ? 900 : duration > 1200 ? 600 : 300
  const out: number[] = []
  for (let t = step; t < duration; t += step) out.push(t)
  return out
}

export function SetTimeline({
  duration,
  entries,
  scannedS,
  onSelect,
}: {
  duration: number
  entries: Entry[]
  /** Hasta dónde se ha analizado (solo mientras el trabajo está en curso). */
  scannedS: number | null
  onSelect(position: number): void
}) {
  if (duration <= 0) return null
  const pct = (s: number) => `${Math.min(100, Math.max(0, (s / duration) * 100))}%`

  return (
    <div className="select-none">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="label">Vista general</p>
        <p className="label">Pulsa un bloque para ir a su track</p>
      </div>
      <div className="relative h-16 overflow-hidden border-y border-line-strong">
        {/* Zona aún sin analizar */}
        {scannedS !== null && (
          <div
            className="hatch absolute inset-y-0 right-0 bg-ink/70"
            style={{ left: pct(scannedS) }}
            aria-hidden
          />
        )}
        {entries.map((e) => {
          const unknown = e.source === 'unknown'
          const name = unknown ? 'ID – ID' : `${e.artist} – ${e.title}`
          return (
            <button
              key={e.position}
              type="button"
              onClick={() => onSelect(e.position)}
              title={`${formatTime(e.start_s)}  ${name}`}
              aria-label={`Ir al ${e.position}: ${name}, ${formatTime(e.start_s)}`}
              className={`absolute inset-y-2.5 origin-bottom transition-[transform,background-color] duration-300 ease-[var(--ease-out-expo)] hover:scale-y-[1.3] hover:!bg-paper focus-visible:z-10 ${
                unknown ? 'hatch bg-deck' : FILL[confidenceLevel(e.confidence)]
              }`}
              style={{
                left: `calc(${pct(e.start_s)} + 1px)`,
                width: `max(3px, calc(${pct(e.end_s - e.start_s)} - 3px))`,
              }}
            />
          )
        })}
        {scannedS !== null && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-0 w-full transition-transform duration-700 ease-linear will-change-transform"
            style={{ transform: `translateX(${pct(scannedS)})` }}
          >
            <span className="absolute inset-y-0 left-0 w-px bg-paper" />
            <span className="absolute -left-[3px] top-0 size-[7px] bg-paper" />
          </div>
        )}
      </div>
      <div className="ruler h-1.5 opacity-60" aria-hidden />
      <div className="relative mt-1.5 h-4" aria-hidden>
        <span className="timecode absolute left-0 text-[10px] text-fog">0:00</span>
        {ticks(duration).map((t) => (
          <span
            key={t}
            className="timecode absolute -translate-x-1/2 text-[10px] text-fog/70"
            style={{ left: pct(t) }}
          >
            {formatTime(t)}
          </span>
        ))}
        <span className="timecode absolute right-0 text-[10px] text-fog">
          {formatTime(duration)}
        </span>
      </div>
    </div>
  )
}

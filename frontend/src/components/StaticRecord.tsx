// Versión estática del disco (SVG, vista cenital). Se usa mientras carga el 3D, si no hay
// WebGL o si falla, y transmite lo mismo: el set como bandas de surcos sobre el vinilo.

import { useId } from 'react'

import { safeCoverUrl } from '../lib/cover'
import {
  GROOVE_INNER,
  GROOVE_OUTER,
  LABEL_R,
  RECORD_R,
  bandIntensity,
  type GrooveBand,
} from '../three/model'

const S = 100 / RECORD_R // unidades de escena → viewBox (radio 100)

export function StaticRecord({
  bands,
  cover,
  className = '',
}: {
  bands: GrooveBand[]
  /** Carátula para la etiqueta central (p. ej. la del primer track del set). */
  cover?: string | null
  className?: string
}) {
  const clip = useId()
  const coverSrc = safeCoverUrl(cover)
  const grooves = []
  for (let r = GROOVE_INNER * S; r < GROOVE_OUTER * S; r += 2.2) grooves.push(r)
  return (
    <svg viewBox="-110 -110 220 220" aria-hidden className={className}>
      <circle r={RECORD_R * S + 6} fill="#1d1e21" />
      <circle r={RECORD_R * S} fill="#0c0c0e" />
      {grooves.map((r) => (
        <circle
          key={r}
          r={r}
          fill="none"
          stroke="#ffffff"
          strokeOpacity={0.045}
          strokeWidth={0.6}
        />
      ))}
      {bands.map((b) => {
        const mid = ((b.inner + b.outer) / 2) * S
        const width = (b.outer - b.inner) * S
        return (
          <circle
            key={`${b.position}-${b.startS}`}
            r={mid}
            fill="none"
            stroke={b.unknown ? '#8c8c96' : 'var(--color-signal)'}
            strokeOpacity={b.unknown ? 0.25 : Math.min(1, 0.35 + bandIntensity(b) / 3)}
            strokeWidth={width}
          />
        )
      })}
      {/* Reflejo de estudio */}
      <path
        d="M -80 -60 A 100 100 0 0 1 60 -82"
        fill="none"
        stroke="#ffffff"
        strokeOpacity={0.08}
        strokeWidth={14}
        strokeLinecap="round"
      />
      <circle r={LABEL_R * S} fill="var(--color-signal)" />
      {coverSrc ? (
        <>
          <clipPath id={clip}>
            <circle r={LABEL_R * S} />
          </clipPath>
          <image
            href={coverSrc}
            x={-LABEL_R * S}
            y={-LABEL_R * S}
            width={LABEL_R * S * 2}
            height={LABEL_R * S * 2}
            preserveAspectRatio="xMidYMid slice"
            clipPath={`url(#${clip})`}
          />
          <circle r={LABEL_R * S} fill="none" stroke="#000" strokeOpacity={0.5} strokeWidth={1} />
        </>
      ) : (
        <>
          <circle r={LABEL_R * S * 0.9} fill="none" stroke="#0a0a0b" strokeWidth={0.6} />
          <g transform={`scale(${(LABEL_R * S * 0.22) / 128}) translate(-128 -128)`}>
            <path
              d="M 198.91 115.50 A 72 72 0 1 1 140.50 57.09"
              fill="none"
              stroke="#0a0a0b"
              strokeWidth={26}
              strokeLinecap="round"
            />
            <circle cx={128} cy={128} r={23} fill="#0a0a0b" />
          </g>
        </>
      )}
      <circle r={coverSrc ? 2.4 : 1.6} fill={coverSrc ? '#0a0a0b' : '#d6d7db'} />
    </svg>
  )
}

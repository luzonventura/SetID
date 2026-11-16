// Geometría del tocadiscos y la correspondencia set ↔ disco. Sin WebGL: se puede testear.
//
// Un vinilo se lee de fuera hacia dentro, así que el minuto 0 del set está en el borde y el
// final junto a la etiqueta. Cada track identificado es una banda de surcos en su sitio.

import type { Entry } from '../api/types'
import { safeCoverUrl } from '../lib/cover'
import { confidenceLevel, type ConfidenceLevel } from '../lib/format'

// Escala: 1 unidad = 100 mm, con las proporciones de un plato de tracción directa de club
// (chasis 453 × 353 mm, plato de 332 mm, brazo de 230 mm). Un LP de 12" mide 305 mm.
export const PLATTER_R = 1.55
export const RECORD_R = 1.42
export const LABEL_R = 0.5
export const GROOVE_OUTER = 1.36
export const GROOVE_INNER = 0.62
const BAND_GAP = 0.009

/** Pivote del brazo respecto al centro del plato, en el plano (x, z). */
export const ARM_PIVOT = { x: 1.91, z: -0.95 } as const
/** Distancia del pivote a la aguja. */
export const ARM_LENGTH = 2.3
/** Radio «de reposo»: la aguja fuera del disco, sobre el soporte del brazo. */
export const ARM_REST_R = 2.2

export type TurntableMode = 'idle' | 'cue' | 'playing' | 'done'

export interface GrooveBand {
  position: number
  inner: number
  outer: number
  unknown: boolean
  level: ConfidenceLevel | null
  label: string
  startS: number
  cover: string | null
}

export function radiusAt(seconds: number, duration: number): number {
  const t = duration > 0 ? Math.min(1, Math.max(0, seconds / duration)) : 0
  return GROOVE_OUTER - t * (GROOVE_OUTER - GROOVE_INNER)
}

export function grooveBands(entries: readonly Entry[], duration: number | null): GrooveBand[] {
  if (!duration || duration <= 0) return []
  const bands: GrooveBand[] = []
  for (const e of entries) {
    const outer = radiusAt(e.start_s, duration) - BAND_GAP / 2
    const inner = radiusAt(e.end_s, duration) + BAND_GAP / 2
    if (outer - inner < 0.004) continue
    const unknown = e.source === 'unknown'
    bands.push({
      position: e.position,
      inner,
      outer,
      unknown,
      level: unknown ? null : confidenceLevel(e.confidence),
      label: unknown ? 'ID – ID' : `${e.artist} – ${e.title}`,
      startS: e.start_s,
      cover: unknown ? null : safeCoverUrl(e.cover_url),
    })
  }
  return bands
}

/**
 * Brillo de cada banda (luz aditiva sobre el vinilo negro): los tracks seguros iluminan más.
 * Por debajo de 1, así solo la banda bajo el ratón (×2) llega a activar el bloom.
 */
export function bandIntensity(band: GrooveBand): number {
  if (band.unknown) return 0.18
  return { high: 0.6, medium: 0.42, low: 0.26 }[band.level ?? 'low']
}

/**
 * Giro del brazo (rotación en Y, radianes) para que la aguja quede a ``radius`` del centro.
 * Ley de los cosenos sobre el triángulo centro–pivote–aguja; se elige la solución que pasa
 * por el lado derecho del disco, como en un tocadiscos real.
 */
export function tonearmYaw(radius: number): number {
  const { x: px, z: pz } = ARM_PIVOT
  const d = Math.hypot(px, pz)
  const l = ARM_LENGTH
  const cos = (d * d + l * l - radius * radius) / (2 * d * l)
  const alpha = Math.acos(Math.min(1, Math.max(-1, cos)))
  const toCenter = Math.atan2(-pz, -px)
  const candidates = [toCenter + alpha, toCenter - alpha].map((angle) => ({
    angle,
    x: px + l * Math.cos(angle),
  }))
  const chosen = candidates[0].x >= candidates[1].x ? candidates[0] : candidates[1]
  // El brazo apunta por su eje local +X; en three.js un giro θ en Y lleva +X a (cos θ, -sin θ).
  return -chosen.angle
}

export function stylusPosition(yaw: number): { x: number; z: number } {
  const angle = -yaw
  return {
    x: ARM_PIVOT.x + ARM_LENGTH * Math.cos(angle),
    z: ARM_PIVOT.z + ARM_LENGTH * Math.sin(angle),
  }
}

/** Velocidad de giro objetivo (rad/s). 33⅓ rpm reales al analizar. */
export function targetSpin(mode: TurntableMode): number {
  const rpm33 = (33.333 / 60) * Math.PI * 2
  return { idle: 0.22, cue: 0.9, playing: rpm33, done: 0 }[mode]
}

export function needleRadius(
  mode: TurntableMode,
  scannedS: number | null,
  duration: number | null,
): number {
  if (mode === 'playing' && duration) return radiusAt(scannedS ?? 0, duration)
  if (mode === 'cue') return GROOVE_OUTER + 0.03
  return ARM_REST_R
}

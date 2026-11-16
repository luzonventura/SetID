import { describe, expect, it } from 'vitest'

import type { Entry } from '../api/types'
import {
  ARM_REST_R,
  GROOVE_INNER,
  GROOVE_OUTER,
  bandIntensity,
  grooveBands,
  needleRadius,
  radiusAt,
  stylusPosition,
  targetSpin,
  tonearmYaw,
} from './model'

const entry = (over: Partial<Entry>): Entry => ({
  position: 1,
  start_s: 0,
  end_s: 600,
  artist: 'A',
  title: 'T',
  label: null,
  isrc: null,
  confidence: 0.9,
  detections: 4,
  source: 'fingerprint',
  timestamp_url: null,
  search: null,
  suggestions: [],
  ...over,
})

describe('turntable model', () => {
  it('maps the set from the outer edge to the label, like a real record', () => {
    expect(radiusAt(0, 3600)).toBeCloseTo(GROOVE_OUTER)
    expect(radiusAt(3600, 3600)).toBeCloseTo(GROOVE_INNER)
    expect(radiusAt(1800, 3600)).toBeCloseTo((GROOVE_OUTER + GROOVE_INNER) / 2)
    expect(radiusAt(-5, 3600)).toBeCloseTo(GROOVE_OUTER)
    expect(radiusAt(9999, 3600)).toBeCloseTo(GROOVE_INNER)
  })

  it('turns each track into a band of grooves in its place', () => {
    const bands = grooveBands(
      [
        entry({ position: 1, start_s: 0, end_s: 900, confidence: 0.95 }),
        entry({ position: 2, start_s: 900, end_s: 1200, source: 'unknown', confidence: null }),
        entry({ position: 3, start_s: 1200, end_s: 1205 }), // demasiado fina: se omite
      ],
      3600,
    )
    expect(bands.map((b) => b.position)).toEqual([1, 2])
    expect(bands[0].outer).toBeGreaterThan(bands[0].inner)
    expect(bands[0].inner).toBeGreaterThan(bands[1].outer) // separadas, sin solaparse
    expect(bands[1].unknown).toBe(true)
    expect(bands[1].label).toBe('ID – ID')
    // Los tracks seguros brillan más que los ID – ID, y nada pasa del umbral del bloom
    // salvo la banda resaltada (×2).
    expect(bandIntensity(bands[0])).toBeGreaterThan(bandIntensity(bands[1]))
    expect(bandIntensity(bands[0])).toBeLessThan(1)
    expect(bandIntensity(bands[0]) * 2).toBeGreaterThan(1)
  })

  it('needs a duration', () => {
    expect(grooveBands([entry({})], null)).toEqual([])
  })

  it('places the stylus exactly at the requested radius', () => {
    for (const r of [GROOVE_OUTER, 1.1, GROOVE_INNER, ARM_REST_R]) {
      const { x, z } = stylusPosition(tonearmYaw(r))
      expect(Math.hypot(x, z)).toBeCloseTo(r, 5)
    }
  })

  it('sweeps across the right-hand side of the record', () => {
    const outer = stylusPosition(tonearmYaw(GROOVE_OUTER))
    const inner = stylusPosition(tonearmYaw(GROOVE_INNER))
    expect(outer.x).toBeGreaterThan(0)
    expect(inner.x).toBeGreaterThan(-0.2)
  })

  it('spins at 33⅓ rpm while analysing and parks the arm otherwise', () => {
    expect(targetSpin('playing')).toBeCloseTo(3.49, 2)
    expect(targetSpin('done')).toBe(0)
    expect(needleRadius('idle', null, 3600)).toBe(ARM_REST_R)
    expect(needleRadius('playing', 1800, 3600)).toBeCloseTo(radiusAt(1800, 3600))
  })
})

// Texturas procedurales dibujadas en canvas: no hay imágenes que cargar ni que permitir en
// la CSP, y todo sale de la misma paleta que la interfaz.

import * as THREE from 'three'

import { GROOVE_INNER, GROOVE_OUTER, LABEL_R, RECORD_R } from './model'

const SIGNAL = '#7dd3fc'
const INK = '#0a0a0b'

export function canvas(
  width: number,
  height = width,
): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const el = document.createElement('canvas')
  el.width = width
  el.height = height
  const ctx = el.getContext('2d')
  if (!ctx) throw new Error('canvas 2D no disponible')
  return [el, ctx]
}

/** Generador pseudoaleatorio con semilla: las texturas salen siempre iguales. */
function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Ruido suave en 1D (para la «dinámica» de la música a lo largo del radio). */
function smoothNoise(random: () => number, length: number, step: number): (x: number) => number {
  const knots = Array.from({ length: Math.ceil(length / step) + 2 }, random)
  return (x) => {
    const i = Math.floor(x / step)
    const f = x / step - i
    const t = f * f * (3 - 2 * f)
    return knots[i] * (1 - t) + knots[i + 1] * t
  }
}

/**
 * Rugosidad del vinilo. En la zona de surcos se ven bandas más claras y más oscuras, como las
 * pasajes fuertes y suaves de la música en un disco real; encima, polvo y micro-arañazos. La
 * zona de entrada y la de salida son lisas (brillan como espejo) y en la de salida va grabada
 * la matriz, como en los discos de verdad.
 */
export function vinylRoughnessTexture(size = 2048, matrix = 'SID-001'): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  const c = size / 2
  const scale = c / RECORD_R
  const random = seeded(0x5e71d)

  ctx.fillStyle = 'rgb(60,60,60)'
  ctx.fillRect(0, 0, size, size)

  // Surcos: un anillo por píxel de radio; la dinámica cambia despacio y los surcos alternan.
  const inner = Math.floor(GROOVE_INNER * scale)
  const outer = Math.ceil(GROOVE_OUTER * scale)
  const dynamics = smoothNoise(random, outer, 9)
  for (let px = inner; px < outer; px += 1) {
    const shade = 104 + dynamics(px) * 46 + (px % 2 === 0 ? 14 : -6)
    ctx.strokeStyle = `rgb(${shade},${shade},${shade})`
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.arc(c, c, px + 0.5, 0, Math.PI * 2)
    ctx.stroke()
  }

  // Matriz grabada a mano en la zona de salida (más rugosa que el vinilo liso que la rodea).
  ctx.fillStyle = 'rgb(150,150,150)'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = `500 ${size * 0.0105}px "Geist Mono Variable", ui-monospace, monospace`
  const runout = ((LABEL_R + GROOVE_INNER) / 2) * scale
  curvedText(ctx, `${matrix}-A1  ·  SETID`, c, c, runout, Math.PI * 0.62)
  ctx.font = `italic 400 ${size * 0.009}px "Geist Mono Variable", ui-monospace, monospace`
  curvedText(ctx, 'ice ⁂', c, c, runout, -Math.PI * 0.3)

  // Polvo: motas sueltas, más rugosas.
  for (let i = 0; i < 900; i += 1) {
    const angle = random() * Math.PI * 2
    const radius = (LABEL_R + random() * (RECORD_R - LABEL_R)) * scale
    const tone = 150 + random() * 90
    ctx.fillStyle = `rgba(${tone},${tone},${tone},${0.35 + random() * 0.5})`
    ctx.fillRect(c + Math.cos(angle) * radius, c + Math.sin(angle) * radius, 1.2, 1.2)
  }
  // Micro-arañazos: arcos cortos casi tangentes al surco (como los de un uso normal).
  ctx.lineCap = 'round'
  for (let i = 0; i < 70; i += 1) {
    const start = random() * Math.PI * 2
    const radius = (GROOVE_INNER + random() * (GROOVE_OUTER - GROOVE_INNER)) * scale
    ctx.strokeStyle = `rgba(200,200,200,${0.08 + random() * 0.2})`
    ctx.lineWidth = 0.6 + random() * 0.6
    ctx.beginPath()
    ctx.arc(
      c + (random() - 0.5) * 6,
      c + (random() - 0.5) * 6,
      radius,
      start,
      start + 0.05 + random() * 0.25,
    )
    ctx.stroke()
  }

  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.NoColorSpace
  texture.anisotropy = 8
  return texture
}

/** Escribe una textura a partir de una función por píxel (con UV: arriba es v = 1). */
function pixelTexture(
  size: number,
  pixel: (rx: number, ry: number, r: number) => [number, number, number],
): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  const image = ctx.createImageData(size, size)
  const c = size / 2
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      // Radio en unidades de escena y dirección radial en el espacio UV (la v crece hacia
      // arriba y la fila 0 del canvas es la de arriba).
      const dx = (x + 0.5 - c) / c
      const dy = (c - y - 0.5) / c
      const len = Math.hypot(dx, dy) || 1
      const [r, g, b] = pixel(dx / len, dy / len, len * RECORD_R)
      const i = (y * size + x) * 4
      image.data[i] = r
      image.data[i + 1] = g
      image.data[i + 2] = b
      image.data[i + 3] = 255
    }
  }
  ctx.putImageData(image, 0, 0)
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.NoColorSpace
  texture.anisotropy = 8
  return texture
}

/**
 * Relieve del vinilo: micro-crestas de los surcos y los escalones donde empiezan (entrada) y
 * acaban (salida). La normal se inclina hacia dentro o hacia fuera del radio.
 */
function vinylNormalTexture(size = 1024): THREE.CanvasTexture {
  const ridge = (RECORD_R / (size / 2)) * 3 // tres píxeles por surco
  return pixelTexture(size, (rx, ry, r) => {
    let tilt = 0
    if (r > GROOVE_INNER && r < GROOVE_OUTER) {
      tilt = Math.sin((r / ridge) * Math.PI * 2) * 0.07
    }
    // Escalones suaves (en coseno, sin aristas que hagan dientes de sierra): el surco está
    // ligeramente hundido respecto a la zona lisa.
    const step = (edge: number, sign: number) => {
      const d = (r - edge) / 0.016
      return Math.abs(d) < 1 ? sign * (0.5 + 0.5 * Math.cos(d * Math.PI)) * 0.22 : 0
    }
    tilt += step(GROOVE_OUTER, 1) + step(GROOVE_INNER, -1)
    const nx = rx * tilt
    const ny = ry * tilt
    const nz = 1
    const k = 1 / Math.hypot(nx, ny, nz)
    return [(nx * k * 0.5 + 0.5) * 255, (ny * k * 0.5 + 0.5) * 255, (nz * k * 0.5 + 0.5) * 255]
  })
}

let sharedMaps: { normal: THREE.CanvasTexture; anisotropy: THREE.CanvasTexture } | null = null

/**
 * Relieve y anisotropía del vinilo: son iguales para todos los discos, así que se calculan
 * una sola vez por sesión (unos 200 ms) y se comparten. No se liberan nunca.
 */
export function sharedVinylMaps(): {
  normal: THREE.CanvasTexture
  anisotropy: THREE.CanvasTexture
} {
  sharedMaps ??= { normal: vinylNormalTexture(), anisotropy: vinylAnisotropyTexture() }
  return sharedMaps
}

/**
 * Dirección de la anisotropía: tangente al surco en cada punto. Es lo que hace que la luz se
 * vea como una estela radial que cruza el disco, como en un vinilo de verdad. Azul = fuerza:
 * plena en los surcos, casi nula en las zonas lisas.
 */
function vinylAnisotropyTexture(size = 1024): THREE.CanvasTexture {
  // Rampa suave en los bordes de la zona de surcos: un salto brusco haría dientes de sierra.
  const ramp = (x: number) => Math.min(1, Math.max(0, x / 0.02))
  return pixelTexture(size, (rx, ry, r) => {
    const inside = Math.min(ramp(r - GROOVE_INNER), ramp(GROOVE_OUTER - r))
    return [(-ry * 0.5 + 0.5) * 255, (rx * 0.5 + 0.5) * 255, 40 + inside * 215]
  })
}

function drawMark(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number): void {
  // Mismo trazo que el logo (backend/scripts/make_icon.py): anillo con hueco y punto.
  const k = size / 256
  ctx.save()
  ctx.translate(cx - 128 * k, cy - 128 * k)
  ctx.scale(k, k)
  ctx.strokeStyle = INK
  ctx.lineWidth = 26
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.arc(128, 128, 72, (-10 * Math.PI) / 180, (280 * Math.PI) / 180)
  ctx.stroke()
  ctx.fillStyle = INK
  ctx.beginPath()
  ctx.arc(128, 128, 23, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}

function curvedText(
  ctx: CanvasRenderingContext2D,
  text: string,
  cx: number,
  cy: number,
  radius: number,
  centerAngle: number,
): void {
  const chars = [...text]
  const widths = chars.map((ch) => ctx.measureText(ch).width)
  const total = widths.reduce((a, b) => a + b, 0)
  let angle = centerAngle - total / radius / 2
  chars.forEach((ch, i) => {
    const half = widths[i] / 2 / radius
    angle += half
    ctx.save()
    ctx.translate(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius)
    ctx.rotate(angle + Math.PI / 2)
    ctx.fillText(ch, 0, 0)
    ctx.restore()
    angle += half
  })
}

/** Etiqueta del disco (azul hielo): logo, nombre, cara y velocidad, como un white label de sello. */
export function labelTexture(size = 1024, catalog = 'SID-001'): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  const c = size / 2
  ctx.fillStyle = SIGNAL
  ctx.fillRect(0, 0, size, size)

  // Anillo impreso cerca del borde.
  ctx.strokeStyle = INK
  ctx.lineWidth = size * 0.006
  ctx.beginPath()
  ctx.arc(c, c, c * 0.9, 0, Math.PI * 2)
  ctx.stroke()

  ctx.fillStyle = INK
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  ctx.font = `800 ${size * 0.13}px "Archivo Variable", "Arial Narrow", sans-serif`
  ctx.fontStretch = 'expanded'
  ctx.fillText('SETID', c, c * 0.52)

  drawMark(ctx, c, c * 1.0, size * 0.22)

  ctx.font = `500 ${size * 0.034}px "Geist Mono Variable", ui-monospace, monospace`
  ctx.fontStretch = 'normal'
  curvedText(
    ctx,
    'TRACK IDENTIFICATION · FOR DJ USE ONLY · NOT FOR SALE',
    c,
    c,
    c * 0.8,
    -Math.PI / 2,
  )

  ctx.font = `600 ${size * 0.04}px "Geist Mono Variable", ui-monospace, monospace`
  ctx.textAlign = 'left'
  ctx.fillText('SIDE A', c * 0.3, c * 1.42)
  ctx.textAlign = 'right'
  ctx.fillText('33⅓ RPM', c * 1.7, c * 1.42)
  ctx.textAlign = 'center'
  ctx.font = `500 ${size * 0.03}px "Geist Mono Variable", ui-monospace, monospace`
  ctx.fillText(catalog, c, c * 1.6)

  // Agujero central (lo tapa el eje, pero da sombra al borde).
  ctx.fillStyle = '#1a1a1c'
  ctx.beginPath()
  ctx.arc(c, c, size * 0.022, 0, Math.PI * 2)
  ctx.fill()

  // Papel: grano fino y algo de sombra hacia el borde, donde la etiqueta se pega al vinilo.
  const random = seeded(0x1abe1)
  for (let i = 0; i < size * 60; i += 1) {
    const dark = random() < 0.5
    ctx.fillStyle = dark ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.06)'
    ctx.fillRect(random() * size, random() * size, 1, 1)
  }
  const edge = ctx.createRadialGradient(c, c, c * 0.72, c, c, c)
  edge.addColorStop(0, 'rgba(0,0,0,0)')
  edge.addColorStop(1, 'rgba(0,0,0,0.22)')
  ctx.fillStyle = edge
  ctx.fillRect(0, 0, size, size)

  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

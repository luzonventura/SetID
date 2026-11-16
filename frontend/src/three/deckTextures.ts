// Texturas del plato de tracción directa (dibujadas en canvas, sin imágenes externas).

import * as THREE from 'three'

import { canvas } from './textures'

/** Ruido fino reutilizable (fieltro, pintura texturizada). Determinista. */
function speckle(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  base: [number, number, number],
  spread: number,
  count: number,
): void {
  ctx.fillStyle = `rgb(${base.join(',')})`
  ctx.fillRect(0, 0, w, h)
  let seed = 7
  const rand = () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }
  for (let i = 0; i < count; i += 1) {
    const v = (rand() - 0.5) * spread
    const rgb = base.map((c) => Math.max(0, Math.min(255, Math.round(c + v))))
    ctx.fillStyle = `rgb(${rgb.join(',')})`
    ctx.fillRect(rand() * w, rand() * h, 1 + rand() * 1.5, 1 + rand() * 1.5)
  }
}

const SLAB = '700 {size}px Rockwell, "Roboto Slab", Georgia, serif'

/** Alfombrilla de fieltro con la marca impresa dos veces, la segunda en espejo. */
export function slipmatTexture(size = 2048, brand = 'SetID'): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  speckle(ctx, size, size, [30, 31, 34], 26, Math.round(size * size * 0.18))
  const c = size / 2
  ctx.strokeStyle = 'rgba(120,126,136,0.55)'
  ctx.lineWidth = size * 0.0035
  ctx.beginPath()
  ctx.arc(c, c, c * 0.955, 0, Math.PI * 2)
  ctx.stroke()

  ctx.fillStyle = 'rgba(84,90,101,0.9)'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'alphabetic'
  ctx.font = SLAB.replace('{size}', String(Math.round(size * 0.17)))
  const width = ctx.measureText(brand).width
  const scaleX = Math.min(1.3, (size * 0.7) / width)
  ctx.save()
  ctx.translate(c, c - size * 0.012)
  ctx.scale(scaleX, 1)
  ctx.fillText(brand, 0, 0)
  ctx.restore()
  // Reflejo: la misma palabra volteada en vertical, como en las alfombrillas clásicas.
  ctx.save()
  ctx.translate(c, c + size * 0.012)
  ctx.scale(scaleX, -1)
  ctx.fillText(brand, 0, 0)
  ctx.restore()

  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

/** Bisel del plato: aluminio anodizado negro con cuatro filas de puntos estroboscópicos. */
export function strobeRimTexture(width = 4096, height = 160): THREE.CanvasTexture {
  const [el, ctx] = canvas(width, height)
  ctx.fillStyle = '#0d0e10'
  ctx.fillRect(0, 0, width, height)
  // De fuera (v = 0) hacia dentro (v = 1): puntos cada vez más pequeños.
  const rows = [
    { v: 0.2, count: 183, r: 0.085 },
    { v: 0.42, count: 222, r: 0.068 },
    { v: 0.63, count: 216, r: 0.056 },
    { v: 0.83, count: 180, r: 0.045 },
  ]
  for (const row of rows) {
    const y = height * (1 - row.v)
    const step = width / row.count
    const radius = height * row.r
    for (let i = 0; i < row.count; i += 1) {
      const x = (i + 0.5) * step
      const g = ctx.createRadialGradient(x - radius * 0.3, y - radius * 0.3, 0, x, y, radius)
      g.addColorStop(0, '#f2f4f8')
      g.addColorStop(0.7, '#b9bec6')
      g.addColorStop(1, '#4c5058')
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.arc(x, y, radius, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.anisotropy = 16
  return texture
}

/** Moleteado (patas, rueda de encendido): relieve en rejilla para un bumpMap. */
export function knurlTexture(width = 1024, height = 96, cells = 128): THREE.CanvasTexture {
  const [el, ctx] = canvas(width, height)
  ctx.fillStyle = '#808080'
  ctx.fillRect(0, 0, width, height)
  const cw = width / cells
  const rows = Math.max(4, Math.round(height / cw))
  const ch = height / rows
  for (let i = 0; i < cells; i += 1) {
    for (let j = 0; j < rows; j += 1) {
      const g = ctx.createLinearGradient(i * cw, j * ch, (i + 1) * cw, (j + 1) * ch)
      g.addColorStop(0, '#e6e6e6')
      g.addColorStop(1, '#1c1c1c')
      ctx.fillStyle = g
      ctx.fillRect(i * cw + 1, j * ch + 1, cw - 2, ch - 2)
    }
  }
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.NoColorSpace
  texture.wrapS = THREE.RepeatWrapping
  return texture
}

/** Aluminio torneado (tapas de la rueda, del RESET, del contrapeso). */
export function brushedDiscTexture(size = 512, base = 70): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  const c = size / 2
  ctx.fillStyle = `rgb(${base},${base + 2},${base + 6})`
  ctx.fillRect(0, 0, size, size)
  for (let r = 2; r < c; r += 1.5) {
    const v = base + ((r * 53) % 40) - 20
    ctx.strokeStyle = `rgb(${v},${v + 2},${v + 6})`
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.arc(c, c, r, 0, Math.PI * 2)
    ctx.stroke()
  }
  // Reflejo cónico típico del aluminio torneado.
  const g = ctx.createConicGradient(0.6, c, c)
  g.addColorStop(0, 'rgba(255,255,255,0.4)')
  g.addColorStop(0.12, 'rgba(255,255,255,0)')
  g.addColorStop(0.5, 'rgba(255,255,255,0.32)')
  g.addColorStop(0.62, 'rgba(255,255,255,0)')
  g.addColorStop(1, 'rgba(255,255,255,0.4)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/** Texto serigrafiado sobre una tecla (START · STOP, 33, 45…). */
export function keyLabelTexture(
  text: string,
  { w = 512, h = 384, size = 0.13, align = 'center' as CanvasTextAlign } = {},
): THREE.CanvasTexture {
  const [el, ctx] = canvas(w, h)
  speckle(ctx, w, h, [24, 25, 28], 10, Math.round(w * h * 0.05))
  ctx.fillStyle = '#c9ccd2'
  ctx.textAlign = align
  ctx.textBaseline = 'middle'
  ctx.font = `500 ${Math.round(h * size * 2)}px "Archivo Variable", Arial, sans-serif`
  ctx.fillText(text, align === 'left' ? w * 0.12 : w / 2, h / 2)
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

export interface DeckMarks {
  width: number
  depth: number
  scale: number
  fader: { x: number; z0: number; z1: number }
  reset: { x: number; z: number }
  knob: { x: number; z: number }
  logo: { x: number; z: number }
  model: string
}

/**
 * Serigrafía de la cubierta (fondo transparente, va en un plano sobre el chasis): escala del
 * pitch, línea del 0 hacia RESET, PITCH ADJ, la escala de la rueda y la inscripción.
 */
export function deckPrintTexture(m: DeckMarks): THREE.CanvasTexture {
  const { width, depth, scale } = m
  const [el, ctx] = canvas(Math.round(width * scale), Math.round(depth * scale))
  const px = (x: number) => (x + width / 2) * scale
  const pz = (z: number) => (z + depth / 2) * scale
  const ink = '#b4b8bf'
  ctx.fillStyle = ink
  ctx.strokeStyle = ink
  ctx.textBaseline = 'middle'

  // Escala del pitch: −8 arriba, +8 abajo; marca en cada punto, número en los pares.
  const { fader } = m
  const tickX = px(fader.x) - 0.2 * scale
  for (let i = -8; i <= 8; i += 1) {
    const y = pz(fader.z0 + ((i + 8) / 16) * (fader.z1 - fader.z0))
    const major = i % 2 === 0
    const len = (major ? 0.05 : 0.028) * scale
    ctx.fillRect(tickX - len, y - 1.5, len, 3)
    if (major && i !== 0) {
      ctx.font = `500 ${Math.round(0.07 * scale)}px "Geist Mono Variable", monospace`
      ctx.textAlign = 'right'
      const label = i === -8 ? '−8' : i === 8 ? '+8' : String(Math.abs(i))
      ctx.fillText(label, tickX - 0.08 * scale, y)
    }
  }
  // Línea guía del 0 hacia el RESET.
  const zero = pz((fader.z0 + fader.z1) / 2)
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(tickX - 0.06 * scale, zero)
  ctx.lineTo(px(m.reset.x), zero)
  ctx.lineTo(px(m.reset.x), pz(m.reset.z) - 0.13 * scale)
  ctx.stroke()

  ctx.textAlign = 'center'
  ctx.font = `500 ${Math.round(0.065 * scale)}px "Archivo Variable", Arial, sans-serif`
  ctx.fillText('RESET', px(m.reset.x), pz(m.reset.z) + 0.17 * scale)
  ctx.fillText('PITCH ADJ', px(fader.x), pz(fader.z1) + 0.2 * scale)

  // Escala de la rueda de encendido.
  ctx.textAlign = 'left'
  ctx.font = `500 ${Math.round(0.05 * scale)}px "Geist Mono Variable", monospace`
  ;['• +6.4', '•  3.3', '•  0   %', '• −3.3'].forEach((line, i) =>
    ctx.fillText(line, px(m.knob.x + 0.2), pz(m.knob.z + 0.1) + i * 0.065 * scale),
  )

  // Inscripción de la marca.
  ctx.textAlign = 'left'
  ctx.font = SLAB.replace('{size}', String(Math.round(0.13 * scale)))
  ctx.fillText('SetID', px(m.logo.x), pz(m.logo.z))
  ctx.font = `500 ${Math.round(0.048 * scale)}px "Archivo Variable", Arial, sans-serif`
  ctx.fillText(
    `DIRECT DRIVE TRACK IDENTIFICATION SYSTEM   ${m.model}`,
    px(m.logo.x),
    pz(m.logo.z) + 0.12 * scale,
  )

  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

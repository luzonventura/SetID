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

/** Mapa de rugosidad de los surcos: anillos finísimos con «pistas» entre canciones. */
export function grooveRoughnessTexture(size = 2048): THREE.CanvasTexture {
  const [el, ctx] = canvas(size)
  const c = size / 2
  const scale = c / RECORD_R
  ctx.fillStyle = '#7a7a7a'
  ctx.fillRect(0, 0, size, size)
  // Surcos: cada píxel de radio alterna ligeramente la rugosidad (el brillo «anisótropo»).
  for (let px = Math.floor(GROOVE_INNER * scale); px < GROOVE_OUTER * scale; px += 1) {
    const shade = 92 + ((px * 37) % 23) + (px % 2 === 0 ? 18 : 0)
    ctx.strokeStyle = `rgb(${shade},${shade},${shade})`
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.arc(c, c, px, 0, Math.PI * 2)
    ctx.stroke()
  }
  // Zonas lisas: borde, área de salida y zona de la etiqueta (brillan como espejo).
  ctx.fillStyle = '#3c3c3c'
  for (const [from, to] of [
    [GROOVE_OUTER, RECORD_R],
    [LABEL_R, GROOVE_INNER],
  ]) {
    ctx.beginPath()
    ctx.arc(c, c, to * scale, 0, Math.PI * 2)
    ctx.arc(c, c, from * scale, 0, Math.PI * 2, true)
    ctx.fill()
  }
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.NoColorSpace
  texture.anisotropy = 8
  return texture
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

/** Etiqueta naranja del disco: logo, nombre, cara y velocidad, como un white label de sello. */
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

  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

/** Lateral del plato: aluminio cepillado con las filas de puntos estroboscópicos. */
export function strobeTexture(width = 2048, height = 128): THREE.CanvasTexture {
  const [el, ctx] = canvas(width, height)
  const gradient = ctx.createLinearGradient(0, 0, 0, height)
  gradient.addColorStop(0, '#9a9ca2')
  gradient.addColorStop(0.5, '#c9cbd0')
  gradient.addColorStop(1, '#7c7e84')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)
  // Cepillado horizontal.
  for (let y = 0; y < height; y += 2) {
    ctx.fillStyle = `rgba(255,255,255,${0.03 + ((y * 13) % 7) / 200})`
    ctx.fillRect(0, y, width, 1)
  }
  // Cuatro filas de puntos (50/60 Hz a 33⅓ y 45 rpm), como en los platos clásicos.
  const rows = [180, 183, 216, 222]
  rows.forEach((count, row) => {
    const y = height * (0.2 + row * 0.2)
    const r = height * 0.045
    ctx.fillStyle = '#26272b'
    for (let i = 0; i < count; i += 1) {
      ctx.beginPath()
      ctx.arc((i + 0.5) * (width / count), y, r, 0, Math.PI * 2)
      ctx.fill()
    }
  })
  const texture = new THREE.CanvasTexture(el)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.anisotropy = 8
  return texture
}

/** Espera a que las fuentes de la interfaz estén cargadas antes de dibujar texto en canvas. */
export async function fontsReady(): Promise<void> {
  if (!('fonts' in document)) return
  await Promise.allSettled([
    document.fonts.load('800 64px "Archivo Variable"'),
    document.fonts.load('500 24px "Geist Mono Variable"'),
  ])
}

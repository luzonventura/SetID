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

// --- Acabado del chasis ---------------------------------------------------------------

/** Pseudoaleatorio con semilla (mismo resultado en cada arranque). */
function random(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export interface FinishMaps {
  roughness: THREE.CanvasTexture
  normal: THREE.CanvasTexture
}

/**
 * Acabado granallado (aluminio con chorro de microesferas y pintura negra mate), repetible
 * sin costuras: una altura de grano fino de la que salen la rugosidad (con algún destello
 * metálico más pulido) y el relieve. `perUnit` = repeticiones por unidad de escena (100 mm).
 */
function blastedFinish(seed: number, perUnit: number, size = 512): FinishMaps {
  const rand = random(seed)
  const height = new Float32Array(size * size)
  // Grano: muchas «microesferas» con caída suave, envueltas en los bordes (repetible).
  const bumps = Math.round(size * size * 0.09)
  for (let i = 0; i < bumps; i += 1) {
    const cx = rand() * size
    const cy = rand() * size
    const radius = 0.8 + rand() * 1.6
    const amp = rand() < 0.5 ? -1 : 1
    const r = Math.ceil(radius)
    for (let dy = -r; dy <= r; dy += 1) {
      for (let dx = -r; dx <= r; dx += 1) {
        const d = Math.hypot(dx + (cx % 1), dy + (cy % 1)) / radius
        if (d >= 1) continue
        const x = (Math.floor(cx) + dx + size) % size
        const y = (Math.floor(cy) + dy + size) % size
        height[y * size + x] += amp * (1 - d * d) * 0.5
      }
    }
  }

  const [rEl, rCtx] = canvas(size)
  const [nEl, nCtx] = canvas(size)
  const rough = rCtx.createImageData(size, size)
  const normal = nCtx.createImageData(size, size)
  const at = (x: number, y: number) => height[((y + size) % size) * size + ((x + size) % size)]
  const flecks = new Set<number>()
  for (let i = 0; i < size * size * 0.004; i += 1) {
    flecks.add(Math.floor(rand() * size * size))
  }
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const i = y * size + x
      const o = i * 4
      // Rugosidad: mate (≈0,7) con variación del grano y destellos metálicos sueltos (≈0,3).
      const r = flecks.has(i) ? 70 : 178 + height[i] * 40
      rough.data[o] = rough.data[o + 1] = rough.data[o + 2] = Math.max(0, Math.min(255, r))
      rough.data[o + 3] = 255
      // Relieve por diferencias centrales (envolviendo en los bordes).
      const nx = (at(x - 1, y) - at(x + 1, y)) * 1.4
      const ny = (at(x, y + 1) - at(x, y - 1)) * 1.4
      const k = 1 / Math.hypot(nx, ny, 1)
      normal.data[o] = (nx * k * 0.5 + 0.5) * 255
      normal.data[o + 1] = (ny * k * 0.5 + 0.5) * 255
      normal.data[o + 2] = (k * 0.5 + 0.5) * 255
      normal.data[o + 3] = 255
    }
  }
  rCtx.putImageData(rough, 0, 0)
  nCtx.putImageData(normal, 0, 0)

  const wrap = (el: HTMLCanvasElement) => {
    const texture = new THREE.CanvasTexture(el)
    texture.colorSpace = THREE.NoColorSpace
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping
    texture.repeat.set(perUnit, perUnit)
    texture.anisotropy = 8
    return texture
  }
  return { roughness: wrap(rEl), normal: wrap(nEl) }
}

export interface Wear {
  /** Color y opacidad: polvo claro y huellas algo más oscuras. */
  map: THREE.CanvasTexture
  /** Las huellas son grasa: más pulidas (brillan); el polvo, muy mate. */
  roughness: THREE.CanvasTexture
}

/**
 * Uso: huellas y roces donde se apoyan las manos (alrededor de START · STOP, del pitch y del
 * brazo) y un poco de polvo repartido. Se pinta sobre una capa transparente encima de la
 * cubierta. Las posiciones van en unidades de escena, con el origen en el centro del chasis.
 */
export function wearTexture(
  deck: { width: number; depth: number },
  hands: { x: number; z: number; spread: number; amount: number }[],
  pxPerUnit = 220,
): Wear {
  const w = Math.round(deck.width * pxPerUnit)
  const h = Math.round(deck.depth * pxPerUnit)
  const rand = random(0x0d0)
  const [mEl, mCtx] = canvas(w, h)
  const [rEl, rCtx] = canvas(w, h)
  rCtx.fillStyle = 'rgb(150,150,150)'
  rCtx.fillRect(0, 0, w, h)
  const toPx = (x: number, z: number): [number, number] => [
    (x / deck.width + 0.5) * w,
    (z / deck.depth + 0.5) * h,
  ]

  // Huellas: manchas ovaladas, suaves, con algo de estría (la piel deja surcos).
  for (const spot of hands) {
    const [cx, cy] = toPx(spot.x, spot.z)
    const n = Math.round(14 * spot.amount)
    for (let i = 0; i < n; i += 1) {
      const angle = rand() * Math.PI * 2
      const dist = Math.sqrt(rand()) * spot.spread * pxPerUnit
      const x = cx + Math.cos(angle) * dist
      const y = cy + Math.sin(angle) * dist
      const rx = (0.05 + rand() * 0.06) * pxPerUnit
      const ry = rx * (0.6 + rand() * 0.3)
      const rot = rand() * Math.PI
      for (const [ctx, colour] of [
        [mCtx, 'rgba(0,0,0,'],
        [rCtx, 'rgba(40,40,40,'],
      ] as const) {
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(rot)
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rx)
        g.addColorStop(0, `${colour}${ctx === mCtx ? 0.16 : 0.75})`)
        g.addColorStop(1, `${colour}0)`)
        ctx.fillStyle = g
        ctx.scale(1, ry / rx)
        ctx.beginPath()
        ctx.arc(0, 0, rx, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }
    }
  }

  // Polvo: motas claras sueltas (y algún hilo de pelusa).
  for (let i = 0; i < w * h * 0.00035; i += 1) {
    const x = rand() * w
    const y = rand() * h
    const a = 0.08 + rand() * 0.22
    mCtx.fillStyle = `rgba(170,170,175,${a})`
    rCtx.fillStyle = 'rgb(255,255,255)'
    const s = 0.5 + rand() * 0.6
    mCtx.fillRect(x, y, s, s)
    rCtx.fillRect(x, y, s, s)
  }
  mCtx.lineCap = 'round'
  for (let i = 0; i < 14; i += 1) {
    const x = rand() * w
    const y = rand() * h
    const angle = rand() * Math.PI * 2
    const len = 6 + rand() * 14
    mCtx.strokeStyle = 'rgba(170,170,175,0.18)'
    mCtx.lineWidth = 0.6
    mCtx.beginPath()
    mCtx.moveTo(x, y)
    mCtx.quadraticCurveTo(
      x + Math.cos(angle + 0.8) * len * 0.6,
      y + Math.sin(angle + 0.8) * len * 0.6,
      x + Math.cos(angle) * len,
      y + Math.sin(angle) * len,
    )
    mCtx.stroke()
  }

  const map = new THREE.CanvasTexture(mEl)
  map.colorSpace = THREE.SRGBColorSpace
  map.anisotropy = 8
  const roughness = new THREE.CanvasTexture(rEl)
  roughness.colorSpace = THREE.NoColorSpace
  roughness.anisotropy = 8
  return { map, roughness }
}

const finishes = new Map<string, FinishMaps>()

/**
 * Acabado compartido: el plato se vuelve a montar al cambiar de pantalla y estas texturas son
 * siempre iguales, así que se calculan una vez por sesión (~60 ms cada una) y no se liberan.
 */
export function sharedFinish(seed: number, perUnit: number): FinishMaps {
  const key = `${seed}:${perUnit}`
  let finish = finishes.get(key)
  if (!finish) {
    finish = blastedFinish(seed, perUnit)
    finishes.set(key, finish)
  }
  return finish
}

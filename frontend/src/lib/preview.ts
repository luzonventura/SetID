// Reproductor único de preescuchas: suena una sola a la vez, en toda la app.
//
// Es un pequeño almacén fuera de React (un único <audio>) al que los componentes se suscriben
// con useSyncExternalStore; así dos filas con el mismo track muestran el mismo estado.

import { useSyncExternalStore } from 'react'

export type PreviewStatus = 'idle' | 'loading' | 'playing' | 'paused' | 'error'

export interface PreviewState {
  url: string | null
  status: PreviewStatus
  /** De 0 a 1. */
  progress: number
}

const IDLE: PreviewState = { url: null, status: 'idle', progress: 0 }

let state: PreviewState = IDLE
let audio: HTMLAudioElement | null = null
const listeners = new Set<() => void>()

function set(next: Partial<PreviewState>): void {
  state = { ...state, ...next }
  for (const listener of listeners) listener()
}

function element(): HTMLAudioElement {
  if (audio) return audio
  const el = new Audio()
  el.preload = 'none'
  el.volume = 0.85
  el.addEventListener('timeupdate', () => {
    if (el.duration > 0) set({ progress: Math.min(1, el.currentTime / el.duration) })
  })
  el.addEventListener('playing', () => set({ status: 'playing' }))
  el.addEventListener('waiting', () => set({ status: 'loading' }))
  el.addEventListener('ended', () => set(IDLE))
  el.addEventListener('error', () => {
    if (state.url) set({ status: 'error' })
  })
  audio = el
  return el
}

function play(el: HTMLAudioElement): void {
  try {
    const started = el.play() as Promise<void> | undefined
    started?.catch(() => set({ status: 'error' }))
  } catch {
    set({ status: 'error' })
  }
}

/** Reproduce la preescucha, o la pausa si es la que ya suena. */
export function togglePreview(url: string): void {
  const el = element()
  if (state.url === url && (state.status === 'playing' || state.status === 'loading')) {
    el.pause()
    set({ status: 'paused' })
    return
  }
  if (state.url !== url || state.status === 'error') {
    el.src = url
    set({ url, status: 'loading', progress: 0 })
  } else {
    set({ status: 'loading' })
  }
  play(el)
}

/** Para y olvida la preescucha en curso (p. ej. al salir de la pantalla del set). */
export function stopPreview(): void {
  if (audio) {
    audio.pause()
    audio.removeAttribute('src')
  }
  if (state !== IDLE) set(IDLE)
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Estado de la preescucha de ``url`` (IDLE si la que suena es otra). */
export function usePreview(url: string | null): PreviewState {
  const current = useSyncExternalStore(subscribe, () => state)
  return url !== null && current.url === url ? current : IDLE
}

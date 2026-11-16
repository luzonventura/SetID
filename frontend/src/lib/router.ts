import { useSyncExternalStore } from 'react'

export type Route = { name: 'home' } | { name: 'job'; id: number } | { name: 'settings' }

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '')
  const job = /^\/job\/(\d+)$/.exec(path)
  if (job) return { name: 'job', id: Number(job[1]) }
  if (path === '/settings') return { name: 'settings' }
  return { name: 'home' }
}

export function href(route: Route): string {
  if (route.name === 'job') return `#/job/${route.id}`
  if (route.name === 'settings') return '#/settings'
  return '#/'
}

type TransitionDocument = Document & {
  startViewTransition?: (update: () => Promise<void>) => {
    ready: Promise<void>
    finished: Promise<void>
  }
}

/**
 * Cambia de pantalla con una View Transition (Chromium/WebView2) si está disponible y el
 * usuario no ha pedido reducir el movimiento. La captura «nueva» se toma cuando React ya ha
 * pintado la ruta: tras el ``hashchange`` y un fotograma.
 */
function withTransition(update: () => void): void {
  const doc = document as TransitionDocument
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  if (!doc.startViewTransition || reduced) {
    update()
    return
  }
  const transition = doc.startViewTransition(
    () =>
      new Promise<void>((resolve) => {
        let settled = false
        const done = () => {
          if (settled) return
          settled = true
          window.removeEventListener('hashchange', done)
          // Un fotograma para que React pinte; con la ventana oculta rAF no corre, así
          // que un temporizador corto hace de respaldo.
          requestAnimationFrame(() => resolve())
          setTimeout(resolve, 60)
        }
        window.addEventListener('hashchange', done)
        update()
        setTimeout(done, 250) // por si el hash no cambia
      }),
  )
  // Si el navegador aborta la transición (ventana oculta, otra en curso) no pasa nada: la
  // pantalla ya ha cambiado.
  transition.ready.catch(() => {})
  transition.finished.catch(() => {})
}

export function navigate(route: Route): void {
  const next = href(route)
  if (window.location.hash === next) return
  withTransition(() => {
    window.location.hash = next
  })
}

/** Los enlaces internos (`#/…`) también navegan con transición. */
export function interceptLinks(): () => void {
  const onClick = (e: MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return
    }
    const anchor = (e.target as Element | null)?.closest?.('a[href^="#/"]')
    if (!anchor) return
    e.preventDefault()
    navigate(parseRoute(anchor.getAttribute('href') ?? '#/'))
  }
  document.addEventListener('click', onClick)
  return () => document.removeEventListener('click', onClick)
}

function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return parseRoute(hash)
}

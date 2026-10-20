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

export function navigate(route: Route): void {
  window.location.hash = href(route)
}

function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return parseRoute(hash)
}

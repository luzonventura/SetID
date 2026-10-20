import { useEffect, useState, type ReactNode } from 'react'

import { api, onBridgeEvent } from '../api/bridge'
import type { AppInfo, Budget } from '../api/types'
import { href, type Route } from '../lib/router'

/** El mismo trazo que el icono de la app (backend/scripts/make_icon.py), sin el fondo. */
function Logo({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="40 40 176 176" aria-hidden className={className}>
      <path
        d="M 198.91 115.50 A 72 72 0 1 1 140.50 57.09"
        fill="none"
        stroke="var(--color-signal)"
        strokeWidth="26"
        strokeLinecap="round"
      />
      <circle cx="128" cy="128" r="23" fill="var(--color-signal)" />
    </svg>
  )
}

function BudgetChip() {
  const [budget, setBudget] = useState<Budget | null>(null)
  useEffect(() => {
    let alive = true
    const load = () => api.getBudget().then((b) => alive && setBudget(b), () => {})
    void load()
    // Se refresca cuando termina un trabajo (es cuando cambian las consultas usadas).
    const off = onBridgeEvent((e) => {
      if (e.type === 'job' && e.job.status === 'done') void load()
    })
    return () => {
      alive = false
      off()
    }
  }, [])
  if (!budget) return null
  const text =
    budget.limit === null
      ? `${budget.used_today} consultas hoy`
      : `${budget.remaining} / ${budget.limit} consultas`
  return (
    <span className="label hidden sm:inline" title={`Proveedor: ${budget.provider}`}>
      <span className="text-chalk">{budget.provider}</span> · {text}
    </span>
  )
}

export function Shell({ route, children }: { route: Route; children: ReactNode }) {
  const [info, setInfo] = useState<AppInfo | null>(null)
  useEffect(() => {
    api.appInfo().then(setInfo, () => {})
  }, [])

  const navItem = (target: Route, text: string) => {
    const current = route.name === target.name
    return (
      <a
        href={href(target)}
        aria-current={current ? 'page' : undefined}
        className={`label px-1 py-1 transition-colors hover:text-chalk ${
          current ? 'text-chalk underline decoration-signal decoration-2 underline-offset-8' : ''
        }`}
      >
        {text}
      </a>
    )
  }

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-signal focus:px-3 focus:py-2 focus:text-ink"
      >
        Saltar al contenido
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <a href="#/" className="group flex items-center gap-3" aria-label="SetID, inicio">
            <Logo className="size-7 transition-transform duration-500 group-hover:rotate-[120deg]" />
            <span className="display text-xl tracking-tight">
              Set<span className="text-signal">ID</span>
            </span>
          </a>
          <nav aria-label="Principal" className="flex items-center gap-5">
            <BudgetChip />
            {navItem({ name: 'home' }, 'Nuevo')}
            {navItem({ name: 'settings' }, 'Ajustes')}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-12">
        {children}
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-5 text-xs text-fog sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="max-w-3xl leading-relaxed">
            {info?.legal_notice ??
              'Herramienta de uso personal. El audio nunca se almacena ni se redistribuye.'}
          </p>
          {info && <p className="label shrink-0">v{info.version}</p>}
        </div>
      </footer>
    </div>
  )
}

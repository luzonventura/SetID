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
    const load = () =>
      api.getBudget().then(
        (b) => alive && setBudget(b),
        () => {},
      )
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
    <span
      className="label hidden items-center gap-2.5 md:inline-flex"
      title={`Proveedor: ${budget.provider}`}
    >
      <span className="size-1.5 rounded-full bg-signal shadow-[0_0_8px_1px_rgb(125_211_252/0.7)]" />
      <span className="text-chalk">{budget.provider}</span>
      <span aria-hidden className="h-3 w-px bg-line-strong" />
      <span className="timecode">{text}</span>
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
        className={`group relative flex h-full items-center px-4 font-mono text-[0.7rem] tracking-[0.14em] uppercase transition-colors ${
          current ? 'text-chalk' : 'text-fog hover:text-chalk'
        }`}
      >
        {text}
        <span
          aria-hidden
          className={`absolute inset-x-4 -bottom-px h-px origin-left bg-signal transition-transform duration-500 ease-[var(--ease-out-expo)] ${
            current ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'
          }`}
        />
      </a>
    )
  }

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-signal focus:px-4 focus:py-2 focus:text-ink"
      >
        Saltar al contenido
      </a>
      {/* Tira de estado, como el rótulo superior de un equipo: opaca y a todo el ancho. */}
      <header className="sticky top-0 z-40 border-b border-line bg-ink [view-transition-name:site-header]">
        <div className="mx-auto flex h-12 max-w-[1400px] items-stretch justify-between gap-6 px-5 sm:px-10">
          <a href="#/" className="group flex items-center gap-2.5" aria-label="SetID, inicio">
            <Logo className="size-5 transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:rotate-[240deg]" />
            <span className="display text-[1.35rem] leading-none">
              Set<span className="text-signal">ID</span>
            </span>
          </a>
          <div className="flex items-center gap-6">
            <BudgetChip />
            <nav aria-label="Principal" className="flex h-full items-stretch">
              {navItem({ name: 'home' }, 'Nuevo')}
              {navItem({ name: 'settings' }, 'Ajustes')}
            </nav>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-5 py-10 sm:px-10 sm:py-12">
        {children}
      </main>

      <footer className="mx-auto w-full max-w-[1400px] px-5 pb-7 sm:px-10">
        <div className="flex flex-col gap-3 border-t border-line pt-5 text-xs text-fog/80 sm:flex-row sm:items-start sm:justify-between">
          <p className="max-w-3xl leading-relaxed">
            {info?.legal_notice ??
              'Herramienta de uso personal. El audio nunca se almacena ni se redistribuye.'}
          </p>
          {info && <p className="label shrink-0">SetID · v{info.version}</p>}
        </div>
      </footer>
    </div>
  )
}

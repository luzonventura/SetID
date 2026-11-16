// Escenario del tocadiscos: elige entre el 3D (cargado bajo demanda) y el disco estático, y
// muestra qué track es cada banda al pasar el ratón (en un portal: los contenedores
// animados con transform desplazarían un position: fixed).

import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

import type { Entry } from '../api/types'
import { formatTime } from '../lib/format'
import { grooveBands, type GrooveBand, type TurntableMode } from '../three/model'
import { Cover } from './Cover'
import { StaticRecord } from './StaticRecord'

const Turntable = lazy(() => import('../three/Turntable'))

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

const motionQuery = '(prefers-reduced-motion: reduce)'
function subscribeMotion(callback: () => void) {
  const mq = window.matchMedia?.(motionQuery)
  mq?.addEventListener('change', callback)
  return () => mq?.removeEventListener('change', callback)
}
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia?.(motionQuery).matches ?? false,
  )
}

/** Pausa el render cuando el tocadiscos no está en pantalla. */
function useOnScreen<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null)
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, visible]
}

class WebGLBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export interface RecordStageProps {
  mode: TurntableMode
  duration: number | null
  entries: Entry[]
  scannedS: number | null
  catalog?: string
  className?: string
  onSelect?(position: number): void
}

export function RecordStage({
  mode,
  duration,
  entries,
  scannedS,
  catalog,
  className = '',
  onSelect,
}: RecordStageProps) {
  const [webgl] = useState(supportsWebGL)
  const reducedMotion = useReducedMotion()
  const [ref, visible] = useOnScreen<HTMLDivElement>()
  const bands = useMemo(() => grooveBands(entries, duration), [entries, duration])
  const [tip, setTip] = useState<{ band: GrooveBand; x: number; y: number } | null>(null)

  const fallback = (
    <div className="grid h-full place-items-center p-[8%]">
      <StaticRecord bands={bands} className="h-full max-h-full w-full drop-shadow-2xl" />
    </div>
  )

  const stage = webgl ? (
    <WebGLBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <Turntable
          mode={mode}
          duration={duration}
          bands={bands}
          scannedS={scannedS}
          catalog={catalog}
          reducedMotion={reducedMotion}
          frameloop={!visible ? 'never' : reducedMotion ? 'demand' : 'always'}
          hovered={tip?.band.position ?? null}
          onHover={(band, x, y) => setTip(band ? { band, x, y } : null)}
          onSelect={(band) => onSelect?.(band.position)}
        />
      </Suspense>
    </WebGLBoundary>
  ) : (
    fallback
  )

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* Charco de luz cálida bajo el plato y bordes fundidos con el fondo. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_48%_40%_at_50%_58%,rgba(56,189,248,0.09),transparent_70%)]"
      />
      <div className="absolute inset-0 [mask-image:radial-gradient(ellipse_47%_49%_at_50%_50%,black_58%,transparent_100%)]">
        {stage}
      </div>
      {tip &&
        createPortal(
          <div
            className="pointer-events-none fixed z-50 flex -translate-x-1/2 -translate-y-[120%] items-center gap-3 rounded-xl border border-line-strong bg-ink/90 p-2 pr-4 shadow-2xl backdrop-blur-md"
            // Centrado sobre el cursor, sin salirse de la ventana (mide hasta ~340 px).
            style={{
              left: Math.min(Math.max(tip.x, 175), window.innerWidth - 175),
              top: Math.max(tip.y, 90),
            }}
          >
            {!tip.band.unknown && (
              <Cover
                url={tip.band.cover}
                artist={tip.band.label}
                title=""
                size={48}
                rounded="rounded-md"
              />
            )}
            <span className="min-w-0">
              <span className="timecode block text-[11px] text-signal">
                {String(tip.band.position).padStart(2, '0')} · {formatTime(tip.band.startS)}
              </span>
              <span className="block max-w-64 truncate text-sm font-semibold">
                {tip.band.label}
              </span>
            </span>
          </div>,
          document.body,
        )}
    </div>
  )
}

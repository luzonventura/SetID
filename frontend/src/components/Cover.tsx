// Carátula de un track con un marcador de posición elegante mientras carga o si no hay.

import { useState } from 'react'

import { hueFor, safeCoverUrl } from '../lib/cover'

export function Cover({
  url,
  artist,
  title,
  size = 44,
  className = '',
  rounded = 'rounded-[2px]',
}: {
  url: string | null | undefined
  artist: string
  title: string
  /** Lado en px, o «fill» para ocupar el contenedor (el ancho lo pone ``className``). */
  size?: number | 'fill'
  className?: string
  rounded?: string
}) {
  const src = safeCoverUrl(url)
  const [state, setState] = useState<{ src: string | null; loaded: boolean; failed: boolean }>({
    src,
    loaded: false,
    failed: false,
  })
  // Si cambia la URL (llega la carátula después), se reinicia el estado de carga.
  const current = state.src === src ? state : { src, loaded: false, failed: false }
  if (current !== state) setState(current)

  const hue = hueFor(`${artist}|${title}`)
  const initials = artist
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('')

  return (
    <span
      className={`@container relative inline-block shrink-0 overflow-hidden ${rounded} ring-1 ring-white/10 ${className}`}
      style={size === 'fill' ? undefined : { width: size, height: size }}
      aria-hidden
    >
      <span
        className="absolute inset-0 grid place-items-center"
        style={{
          background: `radial-gradient(circle at 30% 25%, hsl(${hue} 70% 32%), hsl(${hue + 30} 55% 10%) 75%)`,
        }}
      >
        {/* Vinilo en miniatura: surcos y etiqueta */}
        <span className="absolute inset-[14%] rounded-full bg-[repeating-radial-gradient(circle,rgba(255,255,255,.07)_0_1px,transparent_1px_3px)] opacity-70" />
        <span
          className="timecode relative font-semibold text-white/75"
          style={{
            fontSize: size === 'fill' ? 'clamp(9px, 28cqw, 18px)' : Math.max(9, size * 0.26),
          }}
        >
          {initials || '♪'}
        </span>
      </span>
      {src && !current.failed && (
        <img
          src={src}
          alt=""
          width={size === 'fill' ? 600 : size}
          height={size === 'fill' ? 600 : size}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          draggable={false}
          onLoad={() => setState({ src, loaded: true, failed: false })}
          onError={() => setState({ src, loaded: false, failed: true })}
          className={`absolute inset-0 h-full w-full object-cover transition-[opacity,scale] duration-500 ${
            current.loaded ? 'scale-100 opacity-100' : 'scale-105 opacity-0'
          }`}
        />
      )}
    </span>
  )
}

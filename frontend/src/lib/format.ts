export function formatTime(seconds: number, withHours = false): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h || withHours ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const total = Math.round(seconds / 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`
}

const relative = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })

export function formatRelative(iso: string, now = Date.now()): string {
  const diff = (new Date(iso).getTime() - now) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return 'ahora'
  if (abs < 3600) return relative.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return relative.format(Math.round(diff / 3600), 'hour')
  if (abs < 86400 * 7) return relative.format(Math.round(diff / 86400), 'day')
  return new Date(iso).toLocaleDateString('es', { day: 'numeric', month: 'short' })
}

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export function confidenceLevel(value: number | null): ConfidenceLevel {
  if (value === null || value < 0.5) return 'low'
  return value >= 0.8 ? 'high' : 'medium'
}

export function sourceLabel(type: 'youtube' | 'soundcloud' | 'upload'): string {
  return { youtube: 'YouTube', soundcloud: 'SoundCloud', upload: 'Archivo' }[type]
}

export function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

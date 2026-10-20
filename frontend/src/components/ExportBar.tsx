import { useState } from 'react'

import { api, BridgeError } from '../api/bridge'
import type { ExportFormat } from '../api/types'

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Respaldo si el portapapeles asíncrono no está disponible en la vista web.
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.append(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
}

const FILES: { fmt: ExportFormat; text: string; hint: string }[] = [
  { fmt: 'csv', text: 'CSV', hint: 'Hoja de cálculo' },
  { fmt: 'json', text: 'JSON', hint: 'Datos completos' },
  { fmt: 'm3u', text: 'M3U', hint: 'Lista con enlaces de búsqueda' },
]

export function ExportBar({ jobId }: { jobId: number }) {
  const [status, setStatus] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  const run = async (action: () => Promise<string | null>) => {
    setStatus(null)
    try {
      const message = await action()
      if (message) setStatus({ tone: 'ok', text: message })
    } catch (err) {
      setStatus({ tone: 'error', text: err instanceof BridgeError ? err.message : 'No se pudo exportar.' })
    }
  }

  return (
    <section aria-labelledby="export" className="border border-line bg-booth p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id="export" className="label">
          Exportar
        </h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary"
            onClick={() =>
              run(async () => {
                const file = await api.exportJob(jobId, 'txt')
                await copyText(file.content)
                return 'Tracklist copiado al portapapeles'
              })
            }
          >
            Copiar como texto
          </button>
          {FILES.map(({ fmt, text, hint }) => (
            <button
              key={fmt}
              type="button"
              className="btn-ghost"
              title={hint}
              onClick={() =>
                run(async () => {
                  const { path } = await api.saveExport(jobId, fmt)
                  return path ? `Guardado en ${path}` : null
                })
              }
            >
              {text}
            </button>
          ))}
        </div>
      </div>
      <p
        role="status"
        className={`mt-3 min-h-5 text-sm ${status?.tone === 'error' ? 'text-bad' : 'text-ok'}`}
      >
        {status?.text}
      </p>
    </section>
  )
}

// Aviso a pantalla completa al arrastrar un archivo sobre la ventana.
//
// En la app de escritorio, la ruta real del archivo soltado solo la conoce Python (el
// navegador no la expone por seguridad), así que el `drop` lo procesa el motor y nos avisa
// con un evento `file_dropped`. En el navegador de desarrollo se simula con el mock.

import { useEffect, useState } from 'react'

import { api } from '../api/bridge'
import { navigate } from '../lib/router'

const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')

export function DropOverlay() {
  const [active, setActive] = useState(false)

  useEffect(() => {
    let depth = 0
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth += 1
      setActive(true)
    }
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const leave = () => {
      depth = Math.max(0, depth - 1)
      if (depth === 0) setActive(false)
    }
    const drop = (e: DragEvent) => {
      e.preventDefault()
      depth = 0
      setActive(false)
      if (!window.pywebview && e.dataTransfer?.files.length) {
        void api.pickFile().then((job) => job && navigate({ name: 'job', id: job.id }))
      }
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [])

  if (!active) return null
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[60] grid place-items-center bg-ink/85 backdrop-blur-sm"
    >
      <div className="m-6 grid w-full max-w-3xl place-items-center border-2 border-dashed border-signal px-8 py-24 text-center">
        <p className="label text-signal">Archivo de audio</p>
        <p className="display mt-4 text-5xl sm:text-7xl">Suéltalo</p>
        <p className="mt-4 text-fog">WAV, MP3, FLAC, AIFF, M4A… se detecta por el contenido</p>
      </div>
    </div>
  )
}

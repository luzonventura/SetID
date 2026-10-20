import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { setRawApi, type RawApi } from '../api/bridge'
import { createMockApi } from '../api/mock'
import type { Entry } from '../api/types'
import { Tracklist } from '../components/Tracklist'

let mock: RawApi

beforeEach(() => {
  mock = createMockApi({ tickMs: 5, stepsPerJob: 12 })
  setRawApi(mock)
})

afterEach(() => setRawApi(null))

describe('Home', () => {
  it('shows the empty history and the legal notice', async () => {
    render(<App />)
    expect(await screen.findByText(/Aún no has analizado ningún set/)).toBeInTheDocument()
    expect(await screen.findByText(/términos de servicio/)).toBeInTheDocument()
  })

  it('rejects links outside the whitelist with an accessible error', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText(/Enlace de YouTube o SoundCloud/), 'https://evil.com/x')
    await user.click(screen.getByRole('button', { name: /Identificar/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo se aceptan enlaces')
    expect(screen.getByLabelText(/Enlace de YouTube/)).toHaveAttribute('aria-invalid', 'true')
    expect(window.location.hash).toBe('')
  })

  it('creates a job, follows its progress and shows the final tracklist', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText(/Enlace de YouTube/), 'https://youtu.be/FNKmF7v7pNg')
    await user.click(screen.getByRole('button', { name: /Identificar/ }))
    await waitFor(() => expect(window.location.hash).toBe('#/job/1'))

    await screen.findByRole('heading', { name: /Jorgesyn/ }, { timeout: 2000 })
    await waitFor(() => expect(screen.getByText('Listo', { selector: 'span' })).toBeInTheDocument(), {
      timeout: 3000,
    })
    const list = screen.getByRole('list', { name: 'Tracklist' })
    expect(list.children).toHaveLength(7)
    // Una vez como fila y otra como sugerencia (el tracklist de la comunidad también dice ID).
    expect(within(list).getAllByText('ID – ID')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Copiar como texto' })).toBeInTheDocument()

    // La comunidad sugiere un nombre para el tramo ID – ID, marcado como sin verificar.
    expect(within(list).getByText(/La comunidad sugiere · sin verificar/)).toBeInTheDocument()
    expect(within(list).getByText('Toman')).toBeInTheDocument()
    expect(within(list).getAllByText('unreleased').length).toBeGreaterThan(0)

    // Y todo lo que ha escrito la gente va en su propia pestaña.
    const tab = screen.getByRole('tab', { name: /Comunidad/ })
    await user.click(tab)
    expect(tab).toHaveAttribute('aria-selected', 'true')
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Tracklist publicado')).toBeInTheDocument()
    expect(within(panel).getByText(/No está verificado/)).toBeInTheDocument()
    expect(within(panel).getByText(/out on Music On soon/)).toBeInTheDocument()
    // Los mashups muestran el acapella aparte, no dentro del título.
    expect(within(panel).getByText('+ Max Dean & Luke Dean - Gets Like That (Acapella)')).toBeInTheDocument()
    expect(within(panel).getByText('– Brasuca Vibes')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Tracklist' })).not.toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Tracklist', hidden: true })).not.toBeVisible()
  })

  it('does not show the community tab for uploaded files', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /Usa tu propio archivo/ }))
    await waitFor(() => expect(screen.getByText('Listo', { selector: 'span' })).toBeInTheDocument(), {
      timeout: 3000,
    })
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.queryByText(/La comunidad sugiere/)).not.toBeInTheDocument()
  })
})

const entry = (over: Partial<Entry>): Entry => ({
  position: 1, start_s: 125, end_s: 300, artist: 'Marco Carola', title: 'Space', label: 'Music On',
  isrc: null, confidence: 0.92, detections: 6, source: 'fingerprint',
  timestamp_url: 'https://www.youtube.com/watch?v=abcdefghijk&t=125s', suggestions: [],
  search: { beatport: 'https://www.beatport.com/search?q=x', spotify: 'https://open.spotify.com/search/x', youtube: 'https://www.youtube.com/results?search_query=x' },
  ...over,
})

describe('Tracklist', () => {
  it('renders unknown stretches differently and labels everything', () => {
    render(
      <Tracklist
        live={false}
        highlight={null}
        entries={[
          entry({}),
          entry({ position: 2, start_s: 400, end_s: 520, artist: 'ID', title: 'ID', source: 'unknown', confidence: null, search: null, timestamp_url: null }),
        ]}
      />,
    )
    expect(screen.getByRole('img', { name: /Confianza alta \(0\.92\), 6 segmentos/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir el set en 02:05' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Buscar Marco Carola – Space en Beatport' })).toBeInTheDocument()
    expect(screen.getByText(/sin identificar · 02:00/)).toBeInTheDocument()
  })

  it('opens external links through the bridge, never inside the window', async () => {
    const spy = vi.spyOn(mock, 'open_external').mockResolvedValue({ ok: true, data: null })
    render(<Tracklist live={false} highlight={null} entries={[entry({})]} />)
    const link = screen.getByRole('link', { name: /en Spotify/ })
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    act(() => {
      link.dispatchEvent(event)
    })
    expect(event.defaultPrevented).toBe(true)
    await waitFor(() => expect(spy).toHaveBeenCalledWith('https://open.spotify.com/search/x'))
  })

  it('shows a helpful empty state while analysing', () => {
    render(<Tracklist live highlight={null} entries={[]} />)
    expect(screen.getByText(/aparecerán aquí/)).toBeInTheDocument()
  })
})

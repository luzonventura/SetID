// Estado global de trabajos: historial + tracklists en vivo, alimentado por los eventos
// del motor de la app.

import { useCallback, useEffect, useMemo, useReducer, useState, type ReactNode } from 'react'

import { api, BridgeError, onBridgeEvent } from '../api/bridge'
import { navigate } from '../lib/router'
import { JobsContext } from './context'
import { initialState, reducer } from './reducer'

export function JobsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [lastError, setLastError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      dispatch({ type: 'loaded', jobs: await api.listJobs(50) })
    } catch (e) {
      dispatch({ type: 'load_failed', error: e instanceof BridgeError ? e.message : String(e) })
    }
  }, [])

  const loadDetail = useCallback(async (id: number) => {
    dispatch({ type: 'detail', detail: await api.getJob(id) })
  }, [])

  useEffect(() => {
    const off = onBridgeEvent((event) => {
      dispatch({ type: 'event', event })
      // Un archivo soltado sobre la ventana lo recoge Python; aquí solo se navega.
      if (event.type === 'file_dropped') navigate({ name: 'job', id: event.job.id })
      if (event.type === 'error') setLastError(event.error)
    })
    void refresh()
    return off
  }, [refresh])

  const sortedJobs = useMemo(
    () => Object.values(state.jobs).sort((a, b) => b.id - a.id),
    [state.jobs],
  )

  const value = useMemo(
    () => ({ ...state, sortedJobs, refresh, loadDetail, lastError }),
    [state, sortedJobs, refresh, loadDetail, lastError],
  )
  return <JobsContext value={value}>{children}</JobsContext>
}

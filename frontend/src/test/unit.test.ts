import { afterEach, describe, expect, it } from 'vitest'

import { api, BridgeError, setRawApi, type RawApi } from '../api/bridge'
import type { Job } from '../api/types'
import { confidenceLevel, formatDuration, formatTime } from '../lib/format'
import { parseRoute } from '../lib/router'
import { initialState, reducer } from '../state/reducer'

describe('format', () => {
  it('formats timecodes', () => {
    expect(formatTime(0)).toBe('00:00')
    expect(formatTime(95.9)).toBe('01:35')
    expect(formatTime(3700)).toBe('1:01:40')
    expect(formatTime(65, true)).toBe('0:01:05')
  })
  it('formats durations', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(1800)).toBe('30 min')
    expect(formatDuration(3497)).toBe('58 min')
    expect(formatDuration(7260)).toBe('2 h 01 min')
  })
  it('maps confidence to levels', () => {
    expect(confidenceLevel(null)).toBe('low')
    expect(confidenceLevel(0.45)).toBe('low')
    expect(confidenceLevel(0.6)).toBe('medium')
    expect(confidenceLevel(0.8)).toBe('high')
  })
})

describe('router', () => {
  it('parses routes', () => {
    expect(parseRoute('')).toEqual({ name: 'home' })
    expect(parseRoute('#/job/12')).toEqual({ name: 'job', id: 12 })
    expect(parseRoute('#/settings')).toEqual({ name: 'settings' })
    expect(parseRoute('#/job/abc')).toEqual({ name: 'home' })
    expect(parseRoute('#/job/1/../../x')).toEqual({ name: 'home' })
  })
})

const job = (id: number, extra: Partial<Job> = {}): Job => ({
  id, source_type: 'upload', source: 'a.wav', canonical_id: null, title: null, uploader: null,
  duration_s: null, provider: 'fake', status: 'queued', progress: 0, message: null, error: null,
  queries_used: 0, retries: 0, estimated_cost: 0, cached: false,
  created_at: '2026-10-18T00:00:00Z', started_at: null, finished_at: null, ...extra,
})

describe('reducer', () => {
  it('applies job, tracklist and delete events', () => {
    let state = reducer(initialState, { type: 'loaded', jobs: [job(1), job(2)] })
    state = reducer(state, { type: 'event', event: { type: 'job', job: job(2, { status: 'analyzing' }) } })
    expect(state.jobs[2].status).toBe('analyzing')
    state = reducer(state, { type: 'event', event: { type: 'tracklist', job_id: 2, live: true, tracklist: [] } })
    expect(state.tracklists[2]).toEqual({ entries: [], live: true })
    state = reducer(state, { type: 'event', event: { type: 'job_deleted', job_id: 2 } })
    expect(state.jobs[2]).toBeUndefined()
    expect(state.tracklists[2]).toBeUndefined()
    expect(state.jobs[1]).toBeDefined()
  })
})

describe('bridge', () => {
  afterEach(() => setRawApi(null))

  it('unwraps ok responses and throws BridgeError on failures', async () => {
    setRawApi({
      list_jobs: async () => ({ ok: true, data: [job(1)] }),
      get_job: async () => ({ ok: false, error: 'El trabajo no existe.' }),
      get_budget: async () => {
        throw new Error('boom')
      },
    } as unknown as RawApi)
    await expect(api.listJobs()).resolves.toHaveLength(1)
    await expect(api.getJob(9)).rejects.toThrow(new BridgeError('El trabajo no existe.'))
    await expect(api.getBudget()).rejects.toBeInstanceOf(BridgeError)
  })
})

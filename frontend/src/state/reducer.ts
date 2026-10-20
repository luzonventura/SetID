import type { BridgeEvent, Community, Entry, Job, JobDetail } from '../api/types'

export interface State {
  loaded: boolean
  error: string | null
  jobs: Record<number, Job>
  tracklists: Record<number, { entries: Entry[]; live: boolean }>
  community: Record<number, Community>
}

export type Action =
  | { type: 'loaded'; jobs: Job[] }
  | { type: 'load_failed'; error: string }
  | { type: 'event'; event: BridgeEvent }
  | { type: 'detail'; detail: JobDetail }

export const initialState: State = {
  loaded: false,
  error: null,
  jobs: {},
  tracklists: {},
  community: {},
}

const without = <T>(record: Record<number, T>, id: number): Record<number, T> =>
  Object.fromEntries(Object.entries(record).filter(([key]) => Number(key) !== id))

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'loaded':
      return {
        ...state,
        loaded: true,
        error: null,
        jobs: Object.fromEntries(action.jobs.map((j) => [j.id, j])),
      }
    case 'load_failed':
      return { ...state, loaded: true, error: action.error }
    case 'detail': {
      const { tracklist, live, community, ...job } = action.detail
      return {
        ...state,
        jobs: { ...state.jobs, [job.id]: job },
        tracklists: { ...state.tracklists, [job.id]: { entries: tracklist, live } },
        community: { ...state.community, [job.id]: community },
      }
    }
    case 'event': {
      const event = action.event
      switch (event.type) {
        case 'job':
        case 'file_dropped':
          return { ...state, jobs: { ...state.jobs, [event.job.id]: event.job } }
        case 'tracklist':
          return {
            ...state,
            tracklists: {
              ...state.tracklists,
              [event.job_id]: { entries: event.tracklist, live: event.live },
            },
          }
        case 'community':
          return { ...state, community: { ...state.community, [event.job_id]: event.community } }
        case 'job_deleted':
          return {
            ...state,
            jobs: without(state.jobs, event.job_id),
            tracklists: without(state.tracklists, event.job_id),
            community: without(state.community, event.job_id),
          }
        default:
          return state
      }
    }
  }
}

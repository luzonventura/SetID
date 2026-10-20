import { createContext, use } from 'react'

import type { Job } from '../api/types'
import type { State } from './reducer'

export interface JobsContextValue extends State {
  sortedJobs: Job[]
  lastError: string | null
  refresh(): Promise<void>
  loadDetail(id: number): Promise<void>
}

export const JobsContext = createContext<JobsContextValue | null>(null)

export function useJobs(): JobsContextValue {
  const ctx = use(JobsContext)
  if (!ctx) throw new Error('useJobs fuera de JobsProvider')
  return ctx
}

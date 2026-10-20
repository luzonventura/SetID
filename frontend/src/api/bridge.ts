// Cliente tipado del puente de pywebview (window.pywebview.api).
//
// Cada método de Python devuelve {ok, data} o {ok: false, error}; aquí se convierte en
// una promesa que se resuelve con `data` o se rechaza con un BridgeError con el mensaje
// listo para mostrar.

import type {
  AppInfo,
  Budget,
  BridgeEvent,
  ExportedFile,
  ExportFormat,
  Job,
  JobDetail,
  SecretName,
  SettingsValues,
  SettingsView,
} from './types'

type Result<T> = { ok: true; data: T } | { ok: false; error: string }

export interface RawApi {
  create_job(url: string, force: boolean): Promise<Result<Job>>
  create_job_from_file(path: string | null, force: boolean): Promise<Result<Job | null>>
  list_jobs(limit: number): Promise<Result<Job[]>>
  get_job(id: number): Promise<Result<JobDetail>>
  cancel_job(id: number): Promise<Result<Job>>
  delete_job(id: number): Promise<Result<null>>
  export_job(id: number, fmt: ExportFormat): Promise<Result<ExportedFile>>
  save_export(id: number, fmt: ExportFormat): Promise<Result<{ path: string | null }>>
  get_settings(): Promise<Result<SettingsView>>
  update_settings(changes: Partial<SettingsValues>): Promise<Result<SettingsView>>
  reset_settings(names: string[]): Promise<Result<SettingsView>>
  set_secret(name: SecretName, value: string | null): Promise<Result<Record<SecretName, boolean>>>
  get_budget(): Promise<Result<Budget>>
  open_external(url: string): Promise<Result<null>>
  app_info(): Promise<Result<AppInfo>>
}

declare global {
  interface Window {
    pywebview?: { api: RawApi }
  }
}

export const EVENT_NAME = 'setid:event'

export class BridgeError extends Error {}

let rawApi: Promise<RawApi> | null = null

function waitForPywebview(timeoutMs: number): Promise<RawApi | null> {
  if (window.pywebview?.api) return Promise.resolve(window.pywebview.api)
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs)
    window.addEventListener(
      'pywebviewready',
      () => {
        clearTimeout(timer)
        resolve(window.pywebview?.api ?? null)
      },
      { once: true },
    )
  })
}

async function loadApi(): Promise<RawApi> {
  const native = await waitForPywebview(import.meta.env.DEV ? 400 : 5000)
  if (native) return native
  if (import.meta.env.DEV || import.meta.env.MODE === 'test') {
    // Fuera de la app de escritorio (navegador en desarrollo): backend simulado.
    const { createMockApi } = await import('./mock')
    return createMockApi()
  }
  throw new BridgeError('No se encuentra el motor de la app. Abre SetID desde su acceso directo.')
}

export function setRawApi(api: RawApi | null): void {
  rawApi = api ? Promise.resolve(api) : null
}

async function call<T>(fn: (api: RawApi) => Promise<Result<T>>): Promise<T> {
  rawApi ??= loadApi()
  const api = await rawApi
  let result: Result<T>
  try {
    result = await fn(api)
  } catch {
    throw new BridgeError('La app no ha respondido. Inténtalo de nuevo.')
  }
  if (!result || typeof result !== 'object' || !('ok' in result)) {
    throw new BridgeError('Respuesta inesperada del motor de la app.')
  }
  if (!result.ok) throw new BridgeError(result.error)
  return result.data
}

export const api = {
  createJob: (url: string, force = false) => call((a) => a.create_job(url, force)),
  pickFile: (force = false) => call((a) => a.create_job_from_file(null, force)),
  createJobFromPath: (path: string, force = false) =>
    call((a) => a.create_job_from_file(path, force)),
  listJobs: (limit = 50) => call((a) => a.list_jobs(limit)),
  getJob: (id: number) => call((a) => a.get_job(id)),
  cancelJob: (id: number) => call((a) => a.cancel_job(id)),
  deleteJob: (id: number) => call((a) => a.delete_job(id)),
  exportJob: (id: number, fmt: ExportFormat) => call((a) => a.export_job(id, fmt)),
  saveExport: (id: number, fmt: ExportFormat) => call((a) => a.save_export(id, fmt)),
  getSettings: () => call((a) => a.get_settings()),
  updateSettings: (changes: Partial<SettingsValues>) => call((a) => a.update_settings(changes)),
  resetSettings: (names: string[]) => call((a) => a.reset_settings(names)),
  setSecret: (name: SecretName, value: string | null) => call((a) => a.set_secret(name, value)),
  getBudget: () => call((a) => a.get_budget()),
  openExternal: (url: string) => call((a) => a.open_external(url)),
  appInfo: () => call((a) => a.app_info()),
}

export function onBridgeEvent(listener: (event: BridgeEvent) => void): () => void {
  const handler = (e: Event) => listener((e as CustomEvent<BridgeEvent>).detail)
  window.addEventListener(EVENT_NAME, handler)
  return () => window.removeEventListener(EVENT_NAME, handler)
}

export function emitBridgeEvent(event: BridgeEvent): void {
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: event }))
}

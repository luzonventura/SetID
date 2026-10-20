import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'

import { api, BridgeError } from '../api/bridge'
import type { ProviderName, SecretName, SettingsValues, SettingsView } from '../api/types'
import { Notice, Spinner } from '../components/ui'

const PROVIDERS: { id: ProviderName; name: string; cost: string; note: string }[] = [
  {
    id: 'shazam',
    name: 'Shazam',
    cost: 'Gratis',
    note: 'API no oficial. Puede dejar de funcionar sin aviso. Va despacio a propósito para no ser bloqueada.',
  },
  {
    id: 'acrcloud',
    name: 'ACRCloud',
    cost: 'Prueba gratuita',
    note: 'La mejor base de datos para electrónica. Devuelve puntuación de confianza real.',
  },
  {
    id: 'audd',
    name: 'AudD',
    cost: 'Pocas consultas gratis',
    note: 'Sin puntuación de confianza: hace falta que dos segmentos coincidan.',
  },
  {
    id: 'fake',
    name: 'Demo',
    cost: 'Sin red',
    note: 'Solo reconoce el set sintético de pruebas (setid --make-demo).',
  },
]

const SECRETS: Record<'acrcloud' | 'audd', { name: SecretName; label: string }[]> = {
  acrcloud: [
    { name: 'acrcloud_access_key', label: 'Access key' },
    { name: 'acrcloud_access_secret', label: 'Access secret' },
  ],
  audd: [{ name: 'audd_api_token', label: 'API token' }],
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="grid gap-6 border-t border-line pt-8 lg:grid-cols-[16rem_1fr]">
      <div>
        <h2 className="display text-xl">{title}</h2>
        {hint && <p className="mt-2 text-sm leading-relaxed text-fog">{hint}</p>}
      </div>
      <div className="space-y-5">{children}</div>
    </section>
  )
}

function NumberField({
  label,
  hint,
  value,
  onChange,
  step = 1,
  min,
  max,
  placeholder,
}: {
  label: string
  hint?: string
  value: number | null
  onChange(v: number | null): void
  step?: number
  min?: number
  max?: number
  placeholder?: string
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="label block">
        {label}
      </label>
      <input
        id={id}
        type="number"
        className="field timecode mt-2 max-w-48"
        value={value ?? ''}
        placeholder={placeholder}
        step={step}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      />
      {hint && <p className="mt-1.5 text-xs text-fog">{hint}</p>}
    </div>
  )
}

function SecretField({
  name,
  label,
  stored,
  onSaved,
}: {
  name: SecretName
  label: string
  stored: boolean
  onSaved(secrets: SettingsView['secrets']): void
}) {
  const id = useId()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const save = async (next: string | null) => {
    setError(null)
    try {
      onSaved(await api.setSecret(name, next))
      setValue('')
    } catch (e) {
      setError(e instanceof BridgeError ? e.message : 'No se pudo guardar.')
    }
  }

  return (
    <div>
      <label htmlFor={id} className="label flex items-center gap-2">
        {label}
        <span className={stored ? 'text-ok' : ''}>{stored ? '· guardada' : '· sin configurar'}</span>
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <input
          id={id}
          type="password"
          autoComplete="off"
          className="field timecode max-w-sm flex-1"
          placeholder={stored ? '•••••••• (escribe para sustituirla)' : 'Pega aquí la clave'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="button" className="btn-ghost" disabled={!value} onClick={() => save(value)}>
          Guardar
        </button>
        {stored && (
          <button type="button" className="btn-danger" onClick={() => save(null)}>
            Quitar
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-1.5 text-xs text-bad">
          {error}
        </p>
      )}
    </div>
  )
}

export function Settings() {
  const [view, setView] = useState<SettingsView | null>(null)
  const [draft, setDraft] = useState<SettingsValues | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [status, setStatus] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => {
    api.getSettings().then(
      (v) => {
        setView(v)
        setDraft(v.values)
      },
      (e) => setLoadError(e instanceof BridgeError ? e.message : 'No se pudieron cargar los ajustes.'),
    )
  }, [])

  if (loadError) return <Notice tone="error">{loadError}</Notice>
  if (!view || !draft) return <Spinner label="Cargando ajustes" />

  const set = <K extends keyof SettingsValues>(key: K, value: SettingsValues[K]) =>
    setDraft({ ...draft, [key]: value })

  const changes = Object.fromEntries(
    Object.entries(draft).filter(([k, v]) => view.values[k as keyof SettingsValues] !== v),
  ) as Partial<SettingsValues>
  const dirty = Object.keys(changes).length > 0
  const queriesPerHour = Math.ceil(3600 / (draft.step_s || 30))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setStatus(null)
    try {
      const next = await api.updateSettings(changes)
      setView(next)
      setDraft(next.values)
      setStatus({ tone: 'ok', text: 'Ajustes guardados.' })
    } catch (err) {
      setStatus({ tone: 'error', text: err instanceof BridgeError ? err.message : 'No se pudo guardar.' })
    }
  }

  const providerSecrets =
    draft.provider === 'acrcloud' || draft.provider === 'audd' ? SECRETS[draft.provider] : []

  return (
    <form onSubmit={submit} className="space-y-10 pb-24">
      <header className="animate-rise">
        <p className="label">Configuración</p>
        <h1 className="display mt-3 text-[clamp(2.5rem,6vw,4.5rem)]">Ajustes</h1>
      </header>

      <Section title="Proveedor" hint="Quién identifica los fragmentos. Puedes cambiarlo cuando quieras; los resultados ya guardados no se pierden.">
        <fieldset>
          <legend className="sr-only">Proveedor de reconocimiento</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {PROVIDERS.map((p) => {
              const selected = draft.provider === p.id
              return (
                <label
                  key={p.id}
                  className={`relative cursor-pointer border p-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-signal ${
                    selected ? 'border-signal bg-signal-soft' : 'border-line-strong hover:border-chalk'
                  }`}
                >
                  <input
                    type="radio"
                    name="provider"
                    value={p.id}
                    checked={selected}
                    onChange={() => set('provider', p.id)}
                    className="sr-only"
                  />
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="text-lg font-semibold [font-stretch:115%]">{p.name}</span>
                    <span className={`label ${selected ? 'text-signal' : ''}`}>{p.cost}</span>
                  </span>
                  <span className="mt-1.5 block text-sm leading-relaxed text-fog">{p.note}</span>
                </label>
              )
            })}
          </div>
        </fieldset>
        {providerSecrets.length > 0 && (
          <div className="space-y-4 border-l-2 border-line-strong pl-5">
            <p className="text-sm text-fog">
              Se guardan en el Administrador de credenciales de Windows, nunca en un archivo.
            </p>
            {providerSecrets.map((s) => (
              <SecretField
                key={s.name}
                name={s.name}
                label={s.label}
                stored={view.secrets[s.name]}
                onSaved={(secrets) => setView({ ...view, secrets })}
              />
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Consultas"
        hint={`Con el paso actual, una hora de set son unas ${queriesPerHour} consultas.`}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <NumberField
            label="Presupuesto diario"
            hint="Vacío = sin límite. Si un set no cabe, espera en cola."
            value={draft.daily_query_budget}
            min={0}
            placeholder="Sin límite"
            onChange={(v) => set('daily_query_budget', v)}
          />
          <NumberField
            label="Consultas en paralelo"
            hint={`Vacío = recomendado (${view.effective_limits.concurrency}).`}
            value={draft.concurrency}
            min={1}
            max={10}
            placeholder={String(view.effective_limits.concurrency)}
            onChange={(v) => set('concurrency', v)}
          />
        </div>
      </Section>

      <Section title="Segmentación" hint="Fragmentos más frecuentes dan marcas de tiempo más precisas a cambio de más consultas.">
        <div className="grid gap-5 sm:grid-cols-2">
          <NumberField label="Duración del fragmento (s)" value={draft.window_s} min={4} max={30} onChange={(v) => set('window_s', v ?? 12)} />
          <NumberField label="Un fragmento cada (s)" value={draft.step_s} min={5} onChange={(v) => set('step_s', v ?? 30)} />
        </div>
      </Section>

      <Section title="Agrupación" hint="Cómo se convierten las detecciones sueltas en un tracklist.">
        <div className="grid gap-5 sm:grid-cols-2">
          <NumberField
            label="Confianza mínima (0–1)"
            hint="Una detección suelta por debajo de esto se descarta."
            value={draft.min_confidence}
            step={0.05}
            min={0}
            max={1}
            onChange={(v) => set('min_confidence', v ?? 0.5)}
          />
          <NumberField
            label="Huecos tolerados (fragmentos)"
            hint="Fallos seguidos que no parten un track en dos."
            value={draft.max_gap_segments}
            min={0}
            onChange={(v) => set('max_gap_segments', v ?? 2)}
          />
          <NumberField
            label="Mínimo para ID – ID (fragmentos)"
            value={draft.unknown_min_segments}
            min={1}
            onChange={(v) => set('unknown_min_segments', v ?? 3)}
          />
        </div>
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={draft.mark_unknown_edges}
            onChange={(e) => set('mark_unknown_edges', e.target.checked)}
            className="size-4 accent-[var(--color-signal)]"
          />
          Marcar también como ID – ID el principio y el final del set
        </label>
      </Section>

      <Section
        title="Comunidad"
        hint="Lee la descripción y los comentarios del vídeo para proponer nombres en los tramos ID – ID. Solo con enlaces; no gasta consultas."
      >
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={draft.community_enabled}
            onChange={(e) => set('community_enabled', e.target.checked)}
            className="size-4 accent-[var(--color-signal)]"
          />
          Buscar el tracklist en la descripción y los comentarios
        </label>
        <NumberField
          label="Comentarios a leer"
          hint="Los más votados, con sus respuestas. Más comentarios = más lento."
          value={draft.community_max_comments}
          min={10}
          max={2000}
          step={50}
          onChange={(v) => set('community_max_comments', v ?? 300)}
        />
      </Section>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-ink/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <p role="status" className={`text-sm ${status?.tone === 'error' ? 'text-bad' : 'text-ok'}`}>
            {status?.text ?? (dirty ? <span className="text-fog">Hay cambios sin guardar</span> : null)}
          </p>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost" disabled={!dirty} onClick={() => setDraft(view.values)}>
              Descartar
            </button>
            <button type="submit" className="btn-primary" disabled={!dirty}>
              Guardar
            </button>
          </div>
        </div>
      </div>
    </form>
  )
}

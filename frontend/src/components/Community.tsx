// Pistas de la comunidad: lo que la gente escribió en la descripción y los comentarios.
// Siempre se presentan como "sin verificar" y separadas del reconocimiento por huella.

import type { Community, Hint } from '../api/types'
import { formatTime } from '../lib/format'
import { ExternalLink } from './ui'

const KIND_TEXT = { tracklist: 'Tracklist', comment: 'Comentario', reply: 'Respuesta' }

function UnreleasedTag() {
  return (
    <span className="border border-warn/50 px-1.5 py-0.5 font-mono text-[0.58rem] tracking-[0.12em] text-warn uppercase">
      unreleased
    </span>
  )
}

function HintName({ hint }: { hint: Hint }) {
  if (hint.is_id) {
    return <span className="display text-base text-fog">ID – ID</span>
  }
  return (
    <span className="min-w-0">
      <span className="font-medium text-chalk">{hint.artist}</span>
      <span className="text-chalk/70"> – {hint.title}</span>
      {hint.note && (
        <span className="ml-2 text-xs text-fog" title="Mashup">
          + {hint.note}
        </span>
      )}
    </span>
  )
}

/** Sugerencia compacta dentro de una fila ID – ID del tracklist. */
export function Suggestions({ hints }: { hints: Hint[] }) {
  if (hints.length === 0) return null
  return (
    <div className="col-span-full mt-1 border-l border-signal bg-ink/60 px-4 py-3 sm:col-start-3">
      <p className="label flex items-center gap-2 !text-signal">
        <span className="size-1.5 rounded-full bg-signal" />
        La comunidad sugiere · sin verificar
      </p>
      <ul className="mt-2 space-y-1.5">
        {hints.map((h, i) => (
          <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <HintName hint={h} />
            {h.unreleased && !h.is_id && <UnreleasedTag />}
            <span className="text-xs text-fog" title={h.text}>
              {h.origin}
              {h.likes > 0 && ` · ${h.likes} ♥`}
            </span>
            {h.search && (
              <ExternalLink
                url={h.search.youtube}
                label={`Buscar ${h.artist} – ${h.title} en YouTube`}
                className="link text-xs text-fog hover:text-signal"
              >
                buscar ↗
              </ExternalLink>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function HintRow({ hint, withHours }: { hint: Hint; withHours: boolean }) {
  const time = hint.start_s === null ? null : formatTime(hint.start_s, withHours)
  const search = hint.search
  return (
    <li className="group grid grid-cols-[4.5rem_1fr] items-start gap-x-5 gap-y-2 border-b border-line px-2 py-3.5 transition-colors duration-300 hover:bg-booth sm:grid-cols-[5rem_1fr_auto]">
      {time && hint.timestamp_url ? (
        <ExternalLink
          url={hint.timestamp_url}
          label={`Abrir el set en ${time}`}
          className="timecode link w-fit text-sm text-chalk transition-colors hover:text-signal"
        >
          {time}
        </ExternalLink>
      ) : (
        <span className="timecode w-fit text-sm text-fog">{time ?? `#${hint.position}`}</span>
      )}
      <span className="min-w-0 space-y-1">
        <span className="flex flex-wrap items-center gap-2">
          <HintName hint={hint} />
          {hint.unreleased && !hint.is_id && <UnreleasedTag />}
        </span>
        {hint.kind !== 'tracklist' && (
          <span className="block truncate text-xs text-fog" title={hint.text}>
            {KIND_TEXT[hint.kind]} · {hint.origin}
            {hint.likes > 0 && ` · ${hint.likes} ♥`} — “{hint.text}”
          </span>
        )}
      </span>
      {search && (
        <span className="col-start-2 flex gap-px opacity-60 transition-opacity duration-300 group-hover:opacity-100 sm:col-start-auto">
          {(['beatport', 'spotify', 'youtube'] as const).map((site) => (
            <ExternalLink
              key={site}
              url={search[site]}
              label={`Buscar ${hint.artist} – ${hint.title} en ${site}`}
              className="timecode grid size-8 place-items-center border border-line-strong text-[0.62rem] tracking-[0.08em] uppercase text-fog transition-colors duration-200 hover:border-paper hover:bg-paper hover:text-ink"
            >
              {site.slice(0, 2)}
            </ExternalLink>
          ))}
        </span>
      )}
    </li>
  )
}

export function CommunityPanel({ community }: { community: Community }) {
  const withHours = [...community.tracklist, ...community.mentions].some(
    (h) => (h.start_s ?? 0) >= 3600,
  )
  return (
    <div className="space-y-10">
      <p className="max-w-3xl border-l-2 border-warn pl-4 text-sm leading-relaxed text-chalk/85">
        Esto lo ha escrito la gente en la descripción y los comentarios del vídeo.{' '}
        <strong className="font-medium text-warn">No está verificado</strong> y no se mezcla con lo
        que identifica la huella acústica.
      </p>

      {community.tracklist.length > 0 && (
        <section aria-labelledby="community-tracklist">
          <h3
            id="community-tracklist"
            className="flex items-baseline justify-between border-b border-line-strong pb-3"
          >
            <span className="display text-3xl">Tracklist publicado</span>
            <span className="label">{community.tracklist_origin}</span>
          </h3>
          <ol>
            {community.tracklist.map((h) => (
              <HintRow key={`t-${h.position}`} hint={h} withHours={withHours} />
            ))}
          </ol>
        </section>
      )}

      {community.mentions.length > 0 && (
        <section aria-labelledby="community-mentions">
          <h3
            id="community-mentions"
            className="flex items-baseline justify-between border-b border-line-strong pb-3"
          >
            <span className="display text-3xl">En los comentarios</span>
            <span className="label">{community.mentions.length} menciones</span>
          </h3>
          <ul>
            {community.mentions.map((h, i) => (
              <HintRow key={`m-${i}`} hint={h} withHours={withHours} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

// Pistas de la comunidad: lo que la gente escribió en la descripción y los comentarios.
// Siempre se presentan como "sin verificar" y separadas del reconocimiento por huella.

import type { Community, Hint } from '../api/types'
import { formatTime } from '../lib/format'
import { ExternalLink } from './ui'

const KIND_TEXT = { tracklist: 'Tracklist', comment: 'Comentario', reply: 'Respuesta' }

export function UnreleasedTag() {
  return (
    <span className="label border border-warn/50 px-1.5 py-0.5 text-[10px] text-warn">
      unreleased
    </span>
  )
}

function HintName({ hint }: { hint: Hint }) {
  if (hint.is_id) {
    return <span className="display text-sm tracking-wider text-fog">ID – ID</span>
  }
  return (
    <span className="min-w-0">
      <span className="font-semibold [font-stretch:110%]">{hint.artist}</span>
      <span className="text-chalk/80"> – {hint.title}</span>
      {hint.note && (
        <span className="label ml-2 normal-case tracking-normal" title="Mashup">
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
    <div className="col-span-full mt-1 border-l-2 border-warn/40 pl-3 sm:col-start-3">
      <p className="label text-warn">La comunidad sugiere · sin verificar</p>
      <ul className="mt-1.5 space-y-1.5">
        {hints.map((h, i) => (
          <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <HintName hint={h} />
            {h.unreleased && !h.is_id && <UnreleasedTag />}
            <span className="label normal-case tracking-normal" title={h.text}>
              {h.origin}
              {h.likes > 0 && ` · ${h.likes} ♥`}
            </span>
            {h.search && (
              <ExternalLink
                url={h.search.youtube}
                label={`Buscar ${h.artist} – ${h.title} en YouTube`}
                className="label hover:text-signal"
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
    <li className="grid grid-cols-[4.5rem_1fr] items-start gap-x-4 gap-y-1 border-b border-line px-1 py-3 sm:grid-cols-[5rem_1fr_auto]">
      {time && hint.timestamp_url ? (
        <ExternalLink
          url={hint.timestamp_url}
          label={`Abrir el set en ${time}`}
          className="timecode text-sm text-chalk underline decoration-line-strong underline-offset-4 hover:text-signal"
        >
          {time}
        </ExternalLink>
      ) : (
        <span className="timecode text-sm text-fog">{time ?? `#${hint.position}`}</span>
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
        <span className="col-start-2 flex gap-1 sm:col-start-auto">
          {(['beatport', 'spotify', 'youtube'] as const).map((site) => (
            <ExternalLink
              key={site}
              url={search[site]}
              label={`Buscar ${hint.artist} – ${hint.title} en ${site}`}
              className="timecode grid h-7 w-8 place-items-center border border-line-strong text-[10px] uppercase text-fog hover:border-signal hover:text-signal"
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
      <p className="border-l-2 border-warn/60 bg-booth px-4 py-3 text-sm text-chalk/90">
        Esto lo ha escrito la gente en la descripción y los comentarios del vídeo.{' '}
        <strong className="text-warn">No está verificado</strong> y no se mezcla con lo que
        identifica la huella acústica.
      </p>

      {community.tracklist.length > 0 && (
        <section aria-labelledby="community-tracklist">
          <h3
            id="community-tracklist"
            className="flex items-baseline justify-between border-b border-line-strong pb-2"
          >
            <span className="display text-lg">Tracklist publicado</span>
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
            className="flex items-baseline justify-between border-b border-line-strong pb-2"
          >
            <span className="display text-lg">En los comentarios</span>
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

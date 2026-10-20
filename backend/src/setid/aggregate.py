"""Agregación: de resultados por segmento a un tracklist limpio.

Algoritmo:

1. Cada detección (segmento con ``match``) se asigna a una identidad de track. Dos
   detecciones son el mismo track si comparten ISRC o si coinciden artista y título
   normalizados.
2. Para cada identidad, sus detecciones se agrupan en *ocurrencias*: detecciones separadas
   por como mucho ``max_gap_segments`` segmentos intermedios pertenecen a la misma
   ocurrencia, haya lo que haya en esos segmentos (nada, error o baja confianza de otro
   track). Un hueco mayor abre una ocurrencia nueva: así un track que vuelve más tarde en
   el set aparece dos veces.
3. Se descartan las ocurrencias formadas por una única detección de baja confianza.
4. Se descartan las ocurrencias contenidas por completo dentro de otra con más
   detecciones (p. ej. un falso positivo aislado en mitad de un track).
5. Se ordenan por el primer segmento en que aparecen; esa es su marca de tiempo.
6. Los tramos sin cubrir de al menos ``unknown_min_segments`` segmentos entre dos tracks
   se marcan como ``ID – ID``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from setid.models import EntrySource, Match, SegmentResult, TracklistEntry

UNKNOWN_ARTIST = "ID"
UNKNOWN_TITLE = "ID"


@dataclass(frozen=True)
class AggregationParams:
    window_s: float = 12.0
    min_confidence: float = 0.5
    max_gap_segments: int = 2
    unknown_min_segments: int = 3
    mark_unknown_edges: bool = False


# --- Normalización ------------------------------------------------------------------------

# Sufijos que no cambian la grabación. Los remixes y edits de otros artistas sí son tracks
# distintos y se conservan.
_NEUTRAL_SUFFIX = re.compile(
    r"[\(\[]\s*(original|extended|radio|club)(\s+(mix|version|edit))?\s*[\)\]]"
    r"|-\s*(original|extended)\s+mix\s*$",
    re.IGNORECASE,
)
_FEAT = re.compile(r"[\(\[]?\s*\b(feat|ft|featuring)\b\.?\s+[^\)\]]*[\)\]]?", re.IGNORECASE)
_ARTIST_SPLIT = re.compile(r"\s*(?:,|&|\+|\bx\b|\band\b|\bvs\b\.?|\by\b)\s*", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _clean(text: str) -> str:
    return _NON_ALNUM.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    text = _fold(title)
    text = _NEUTRAL_SUFFIX.sub(" ", text)
    text = _FEAT.sub(" ", text)
    return _clean(text)


def normalize_artist(artist: str) -> str:
    text = _FEAT.sub(" ", _fold(artist))
    names = {_clean(name) for name in _ARTIST_SPLIT.split(text)}
    return " & ".join(sorted(n for n in names if n))


def normalize_isrc(isrc: str | None) -> str | None:
    if not isrc:
        return None
    cleaned = re.sub(r"[^0-9A-Z]", "", isrc.upper())
    return cleaned if len(cleaned) == 12 else None


def text_key(match: Match) -> str:
    return f"{normalize_artist(match.artist)}|{normalize_title(match.title)}"


def same_track(a: Match, b: Match) -> bool:
    isrc_a, isrc_b = normalize_isrc(a.isrc), normalize_isrc(b.isrc)
    if isrc_a and isrc_b and isrc_a == isrc_b:
        return True
    # Una misma grabación puede tener varios ISRC (reediciones), así que si no coinciden
    # todavía puede ser el mismo track por artista + título.
    return text_key(a) == text_key(b)


# --- Agrupación ---------------------------------------------------------------------------


@dataclass
class _Occurrence:
    detections: list[SegmentResult] = field(default_factory=list)

    @property
    def first(self) -> int:
        return self.detections[0].index

    @property
    def last(self) -> int:
        return self.detections[-1].index

    @property
    def count(self) -> int:
        return len(self.detections)

    def matches(self) -> list[Match]:
        return [d.match for d in self.detections if d.match is not None]

    def best(self) -> Match:
        return max(self.matches(), key=lambda m: m.confidence)

    def contains(self, other: _Occurrence) -> bool:
        return self.first <= other.first and other.last <= self.last


def _group_by_identity(detections: list[SegmentResult]) -> list[list[SegmentResult]]:
    groups: list[tuple[Match, list[SegmentResult]]] = []
    for det in detections:
        if det.match is None:
            continue
        for ref, members in groups:
            if same_track(ref, det.match):
                members.append(det)
                break
        else:
            groups.append((det.match, [det]))
    return [members for _, members in groups]


def _split_occurrences(group: list[SegmentResult], max_gap: int) -> list[_Occurrence]:
    occurrences: list[_Occurrence] = []
    current = _Occurrence()
    for det in group:
        if current.detections and det.index - current.last - 1 > max_gap:
            occurrences.append(current)
            current = _Occurrence()
        current.detections.append(det)
    if current.detections:
        occurrences.append(current)
    return occurrences


def _drop_contained(occurrences: list[_Occurrence]) -> list[_Occurrence]:
    kept: list[_Occurrence] = []
    for occ in occurrences:
        dominated = any(
            other is not occ and other.contains(occ) and other.count > occ.count
            for other in occurrences
        )
        if not dominated:
            kept.append(occ)
    return kept


def _entry_from(occ: _Occurrence, window_s: float) -> TracklistEntry:
    matches = occ.matches()
    best = occ.best()
    label = best.label or next((m.label for m in matches if m.label), None)
    isrc = normalize_isrc(best.isrc) or next(
        (normalize_isrc(m.isrc) for m in matches if normalize_isrc(m.isrc)), None
    )
    return TracklistEntry(
        position=1,
        start_s=occ.detections[0].start_s,
        end_s=occ.detections[-1].start_s + window_s,
        artist=best.artist,
        title=best.title,
        label=label,
        isrc=isrc,
        confidence=best.confidence,
        detections=occ.count,
        source=EntrySource.FINGERPRINT,
    )


def _unknown_entry(start: SegmentResult, end_s: float) -> TracklistEntry:
    return TracklistEntry(
        position=1,
        start_s=start.start_s,
        end_s=end_s,
        artist=UNKNOWN_ARTIST,
        title=UNKNOWN_TITLE,
        source=EntrySource.UNKNOWN,
    )


def aggregate(
    results: Sequence[SegmentResult], params: AggregationParams | None = None
) -> list[TracklistEntry]:
    p = params or AggregationParams()
    segments = sorted(results, key=lambda r: r.index)
    if not segments:
        return []
    by_index = {s.index: s for s in segments}

    detections = [s for s in segments if s.match is not None]
    occurrences: list[_Occurrence] = []
    for group in _group_by_identity(detections):
        occurrences.extend(_split_occurrences(group, p.max_gap_segments))

    occurrences = [
        occ for occ in occurrences if occ.count > 1 or occ.best().confidence >= p.min_confidence
    ]
    occurrences = _drop_contained(occurrences)
    occurrences.sort(key=lambda o: (o.first, -o.count))

    first_index, last_index = segments[0].index, segments[-1].index
    entries: list[TracklistEntry] = []

    def add_unknown_if_long(gap_start: int, gap_end: int) -> None:
        """Añade ``ID – ID`` si el tramo [gap_start, gap_end] es suficientemente largo."""
        if gap_end - gap_start + 1 < p.unknown_min_segments:
            return
        start = next(by_index[i] for i in range(gap_start, gap_end + 1) if i in by_index)
        end = by_index[gap_end].start_s + p.window_s if gap_end in by_index else start.start_s
        entries.append(_unknown_entry(start, end))

    covered_until: int | None = None
    for occ in occurrences:
        if covered_until is None:
            if p.mark_unknown_edges:
                add_unknown_if_long(first_index, occ.first - 1)
        elif occ.first > covered_until + 1:
            add_unknown_if_long(covered_until + 1, occ.first - 1)
        entries.append(_entry_from(occ, p.window_s))
        covered_until = occ.last if covered_until is None else max(covered_until, occ.last)

    if covered_until is None:
        if p.mark_unknown_edges:
            add_unknown_if_long(first_index, last_index)
    elif p.mark_unknown_edges:
        add_unknown_if_long(covered_until + 1, last_index)

    return [e.model_copy(update={"position": i}) for i, e in enumerate(entries, start=1)]

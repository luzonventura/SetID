"""Vistas serializables que se envían a la interfaz."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel

from setid.community import Hint, HintKind, suggestions_for, track_key
from setid.db.tables import CommunityHint, Job, JobStatus, TrackEntry
from setid.links import search_links, timestamp_link
from setid.models import EntrySource, SourceType, TracklistEntry


class JobView(BaseModel):
    id: int
    source_type: SourceType
    source: str
    canonical_id: str | None
    title: str | None
    uploader: str | None
    duration_s: float | None
    provider: str
    status: JobStatus
    progress: float
    message: str | None
    error: str | None
    queries_used: int
    retries: int
    estimated_cost: float
    cached: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: Job) -> JobView:
        assert job.id is not None  # noqa: S101 - un Job leído de la base siempre tiene id
        return cls(
            id=job.id,
            source_type=job.source_type,
            source=job.source,
            canonical_id=job.canonical_id,
            title=job.title,
            uploader=job.uploader,
            duration_s=job.duration_s,
            provider=job.provider,
            status=job.status,
            progress=job.progress,
            message=job.message,
            error=job.error,
            queries_used=job.queries_used,
            retries=job.retries,
            estimated_cost=job.estimated_cost,
            cached=job.cached_from_id is not None,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class EntryView(BaseModel):
    position: int
    start_s: float
    end_s: float
    artist: str
    title: str
    label: str | None
    isrc: str | None
    confidence: float | None
    detections: int
    source: EntrySource
    timestamp_url: str | None
    search: dict[str, str] | None
    # Solo en los ID – ID: lo que dice la comunidad sobre ese tramo (sin verificar).
    suggestions: list[HintView] = []


class HintView(BaseModel):
    kind: HintKind
    start_s: float | None
    artist: str
    title: str
    unreleased: bool
    is_id: bool
    origin: str
    author: str | None
    likes: int
    text: str
    position: int
    note: str | None
    timestamp_url: str | None
    search: dict[str, str] | None


class CommunityView(BaseModel):
    tracklist_origin: str | None
    tracklist: list[HintView]
    mentions: list[HintView]


class JobDetail(JobView):
    tracklist: list[EntryView]
    live: bool  # True mientras el tracklist es provisional (trabajo en curso)
    community: CommunityView


def entry_from_row(row: TrackEntry) -> TracklistEntry:
    return TracklistEntry(
        position=row.position,
        start_s=row.start_s,
        end_s=row.end_s,
        artist=row.artist,
        title=row.title,
        label=row.label,
        isrc=row.isrc,
        confidence=row.confidence,
        detections=row.detections,
        source=row.source,
    )


def row_from_entry(job_id: int, entry: TracklistEntry) -> TrackEntry:
    return TrackEntry(job_id=job_id, **entry.model_dump())


def _timestamp(job: JobView, start_s: float | None) -> str | None:
    if job.source_type is SourceType.UPLOAD or start_s is None:
        return None
    return timestamp_link(job.source_type, job.source, start_s)


def hint_from_row(row: CommunityHint) -> Hint:
    return Hint(
        kind=row.kind,
        start_s=row.start_s,
        artist=row.artist,
        title=row.title,
        unreleased=row.unreleased,
        origin=row.origin,
        author=row.author,
        likes=row.likes,
        text=row.text,
        position=row.position,
        note=row.note,
    )


def row_from_hint(job_id: int, hint: Hint) -> CommunityHint:
    return CommunityHint(job_id=job_id, **dataclasses.asdict(hint))


def hint_view(job: JobView, hint: Hint) -> HintView:
    return HintView(
        kind=hint.kind,
        start_s=hint.start_s,
        artist=hint.artist,
        title=hint.title,
        unreleased=hint.unreleased,
        is_id=hint.is_id,
        origin=hint.origin,
        author=hint.author,
        likes=hint.likes,
        text=hint.text,
        position=hint.position,
        note=hint.note,
        timestamp_url=_timestamp(job, hint.start_s),
        search=None if hint.is_id else search_links(hint.artist, hint.title),
    )


def entry_view(
    job: JobView,
    entry: TracklistEntry,
    hints: Sequence[Hint] = (),
    known: frozenset[tuple[str, str]] = frozenset(),
) -> EntryView:
    suggestions = (
        [hint_view(job, h) for h in suggestions_for(entry.start_s, entry.end_s, hints, known=known)]
        if entry.is_unknown and hints
        else []
    )
    return EntryView(
        **entry.model_dump(),
        timestamp_url=_timestamp(job, entry.start_s),
        search=None if entry.is_unknown else search_links(entry.artist, entry.title),
        suggestions=suggestions,
    )


def tracklist_views(
    job: JobView, entries: Sequence[TracklistEntry], hints: Sequence[Hint]
) -> list[EntryView]:
    known = frozenset(track_key(e.artist, e.title) for e in entries if not e.is_unknown)
    return [entry_view(job, e, hints, known) for e in entries]


def community_view(job: JobView, hints: Sequence[Hint]) -> CommunityView:
    tracklist = sorted((h for h in hints if h.kind is HintKind.TRACKLIST), key=lambda h: h.position)
    return CommunityView(
        tracklist_origin=tracklist[0].origin if tracklist else None,
        tracklist=[hint_view(job, h) for h in tracklist],
        mentions=[hint_view(job, h) for h in hints if h.kind is not HintKind.TRACKLIST],
    )

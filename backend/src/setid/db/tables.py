"""Tablas de la base de datos local (SQLite).

Es una app de escritorio de un solo usuario, así que no hay tabla ``User``. Sin
``from __future__ import annotations``: SQLModel necesita las anotaciones evaluadas.
"""

from datetime import UTC, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from setid.community import HintKind
from setid.models import EntrySource, SourceType


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"
    AGGREGATING = "aggregating"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self in {JobStatus.DOWNLOADING, JobStatus.ANALYZING, JobStatus.AGGREGATING}

    @property
    def is_final(self) -> bool:
        return self in {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}


def _enum(enum: type[StrEnum]) -> sa.Enum:
    # Se guarda el valor ("done"), no el nombre ("DONE"), y sin CHECK de SQLite para que
    # añadir estados no obligue a recrear la tabla.
    return sa.Enum(
        enum, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20
    )


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_type: SourceType = Field(sa_type=_enum(SourceType))
    # Lo que introdujo el usuario: URL canónica o ruta del archivo.
    source: str
    canonical_id: str | None = Field(default=None, index=True)
    title: str | None = None
    uploader: str | None = None
    duration_s: float | None = None
    provider: str
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_type=_enum(JobStatus), index=True)
    progress: float = 0.0
    message: str | None = None
    error: str | None = None
    queries_used: int = 0
    retries: int = 0
    estimated_cost: float = 0.0
    force: bool = False
    cached_from_id: int | None = Field(default=None, foreign_key="job.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=utcnow, sa_type=sa.DateTime(timezone=True))
    started_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))


class TrackEntry(SQLModel, table=True):
    __tablename__ = "track_entry"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True, ondelete="CASCADE")
    position: int
    start_s: float
    end_s: float
    artist: str
    title: str
    label: str | None = None
    isrc: str | None = None
    confidence: float | None = None
    detections: int = 0
    source: EntrySource = Field(sa_type=_enum(EntrySource))


class QueryUsage(SQLModel, table=True):
    """Consultas consumidas por día (hora local) y proveedor, para el presupuesto diario."""

    __tablename__ = "query_usage"

    day: str = Field(primary_key=True)  # AAAA-MM-DD
    provider: str = Field(primary_key=True)
    queries: int = 0
    estimated_cost: float = 0.0


class CommunityHint(SQLModel, table=True):
    """Pista de la comunidad (descripción o comentarios). Nunca se mezcla con TrackEntry."""

    __tablename__ = "community_hint"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True, ondelete="CASCADE")
    kind: HintKind = Field(sa_type=_enum(HintKind))
    start_s: float | None = None
    artist: str
    title: str
    unreleased: bool = False
    origin: str
    author: str | None = None
    likes: int = 0
    text: str
    position: int = 0
    note: str | None = None

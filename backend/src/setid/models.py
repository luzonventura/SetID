"""Tipos de dominio compartidos por todo el pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    UPLOAD = "upload"


class EntrySource(StrEnum):
    FINGERPRINT = "fingerprint"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class Match(BaseModel):
    """Un track identificado por un proveedor en un segmento concreto."""

    model_config = ConfigDict(frozen=True)

    artist: str
    title: str
    label: str | None = None
    isrc: str | None = None
    album: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    provider: str


class SegmentResult(BaseModel):
    """Resultado del reconocimiento de un segmento (con o sin coincidencia)."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    start_s: float = Field(ge=0.0)
    match: Match | None = None
    error: str | None = None


class TracklistEntry(BaseModel):
    """Una línea del tracklist final."""

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=1)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    artist: str
    title: str
    label: str | None = None
    isrc: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    detections: int = 0
    source: EntrySource

    @property
    def is_unknown(self) -> bool:
        return self.source is EntrySource.UNKNOWN

"""Configuración leída de variables de entorno (prefijo ``SETID_``) o de ``.env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(StrEnum):
    FAKE = "fake"
    ACRCLOUD = "acrcloud"
    AUDD = "audd"
    SHAZAM = "shazam"


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "SetID"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SETID_", env_file=".env", extra="ignore")

    provider: ProviderName = ProviderName.FAKE
    data_dir: Path = Field(default_factory=_default_data_dir)

    # Segmentación
    window_s: float = Field(default=12.0, gt=0, le=30)
    step_s: float = Field(default=30.0, gt=0)

    # Reconocimiento. ``None`` = el valor recomendado para el proveedor (ver RATE_PROFILES).
    concurrency: int | None = Field(default=None, ge=1, le=10)
    min_interval_s: float | None = Field(default=None, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    backoff_base_s: float | None = Field(default=None, gt=0)
    backoff_max_s: float = Field(default=60.0, gt=0)
    request_timeout_s: float = Field(default=30.0, gt=0)
    daily_query_budget: int | None = Field(default=None, ge=0)

    # Agregación
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    max_gap_segments: int = Field(default=2, ge=0)
    unknown_min_segments: int = Field(default=3, ge=1)
    mark_unknown_edges: bool = False

    # Tracklist de la comunidad (descripción y comentarios; solo enlaces)
    community_enabled: bool = True
    community_max_comments: int = Field(default=300, ge=10, le=2000)
    community_timeout_s: float = Field(default=180.0, gt=0)

    # Límites de entrada
    max_duration_s: int = Field(default=4 * 3600, gt=0)
    max_file_bytes: int = Field(default=2 * 1024**3, gt=0)
    metadata_timeout_s: float = Field(default=60.0, gt=0)
    download_timeout_s: float = Field(default=20 * 60.0, gt=0)
    ffmpeg_timeout_s: float = Field(default=20 * 60.0, gt=0)

    # Credenciales. En la app de escritorio se guardan en el Administrador de credenciales
    # (ver settings_store); aquí solo llegan desde .env o variables de entorno.
    acrcloud_host: str = "identify-eu-west-1.acrcloud.com"
    acrcloud_access_key: SecretStr | None = None
    acrcloud_access_secret: SecretStr | None = None
    audd_api_token: SecretStr | None = None

    # Confianza fija para proveedores que no devuelven puntuación. Por defecto queda por
    # debajo de ``min_confidence``: una detección suelta se descarta y hacen falta al menos
    # dos segmentos que coincidan. Súbela por encima del umbral para conservar las sueltas.
    audd_confidence: float = Field(default=0.45, ge=0, le=1)
    shazam_confidence: float = Field(default=0.45, ge=0, le=1)

    # Coste estimado por consulta en USD; ajústalo a tu plan
    cost_per_query_acrcloud: float = Field(default=0.0, ge=0)
    cost_per_query_audd: float = Field(default=0.0, ge=0)

    @property
    def temp_root(self) -> Path:
        return self.data_dir / "tmp"

    def rate_limits(self) -> RateProfile:
        """Límites efectivos: los del proveedor, con lo que se haya fijado a mano encima."""
        base = RATE_PROFILES[self.provider]
        return RateProfile(
            concurrency=self.concurrency or base.concurrency,
            min_interval_s=base.min_interval_s
            if self.min_interval_s is None
            else self.min_interval_s,
            backoff_base_s=self.backoff_base_s or base.backoff_base_s,
        )


@dataclass(frozen=True)
class RateProfile:
    concurrency: int
    min_interval_s: float
    backoff_base_s: float


RATE_PROFILES: dict[ProviderName, RateProfile] = {
    ProviderName.FAKE: RateProfile(concurrency=3, min_interval_s=0.0, backoff_base_s=1.0),
    ProviderName.ACRCLOUD: RateProfile(concurrency=3, min_interval_s=0.0, backoff_base_s=1.0),
    ProviderName.AUDD: RateProfile(concurrency=2, min_interval_s=0.5, backoff_base_s=2.0),
    # La API no oficial de Shazam limita rápido: con 3 en paralelo y sin pausa, en un set de
    # 1 h hubo 189 reintentos y 40 segmentos perdidos.
    ProviderName.SHAZAM: RateProfile(concurrency=1, min_interval_s=1.5, backoff_base_s=4.0),
}

"""Orquestación del pipeline: entrada → audio → segmentos → tracklist.

Está partido en dos pasos para que la app pueda consultar la caché entre medias:

* :func:`prepare_input`: valida y lee metadatos (o el hash del archivo). No descarga nada.
* :func:`process_input`: descarga, normaliza, segmenta, reconoce y agrega.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import httpx

from setid.aggregate import AggregationParams, aggregate
from setid.audio import ffmpeg
from setid.audio.segment import iter_segments, segment_starts, wav_duration
from setid.config import Settings
from setid.models import SegmentResult, SourceType, TracklistEntry
from setid.providers.base import RecognitionProvider
from setid.recognize import (
    BudgetExhaustedError,
    FixedBudget,
    QueryBudget,
    RecognitionStats,
    RetryPolicy,
    recognize_segments,
)
from setid.sources import ytdlp
from setid.sources.url import CanonicalSource, RedirectResolver, resolve_source
from setid.workdir import job_workdir


class Phase(StrEnum):
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"
    AGGREGATING = "aggregating"
    DONE = "done"


@dataclass(frozen=True)
class Progress:
    phase: Phase
    percent: float
    message: str
    tracklist: list[TracklistEntry] | None = None


ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class PreparedInput:
    source_type: SourceType
    canonical_id: str
    # Lo que se guarda como origen: URL canónica o ruta absoluta del archivo.
    source: str
    title: str
    uploader: str | None
    duration_s: float
    origin: CanonicalSource | Path
    description: str | None = field(default=None, repr=False)

    @property
    def is_upload(self) -> bool:
        return isinstance(self.origin, Path)


@dataclass
class PipelineResult:
    source_type: SourceType
    canonical_id: str
    title: str
    uploader: str | None
    duration_s: float
    tracklist: list[TracklistEntry]
    segments: list[SegmentResult]
    stats: RecognitionStats
    provider: str
    description: str | None = field(default=None, repr=False)


def looks_like_url(value: str) -> bool:
    text = value.strip().lower()
    return "://" in text or text.startswith(("www.", "youtube.com", "youtu.be", "soundcloud.com"))


def http_redirect_resolver(timeout_s: float = 10.0) -> RedirectResolver:
    def resolve(url: str) -> str | None:
        with httpx.Client(follow_redirects=False, timeout=timeout_s) as client:
            response = client.get(url)
        return response.headers.get("location") if response.is_redirect else None

    return resolve


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"file:{digest.hexdigest()}"


def aggregation_params(settings: Settings) -> AggregationParams:
    return AggregationParams(
        window_s=settings.window_s,
        min_confidence=settings.min_confidence,
        max_gap_segments=settings.max_gap_segments,
        unknown_min_segments=settings.unknown_min_segments,
        mark_unknown_edges=settings.mark_unknown_edges,
    )


def estimate_queries(duration_s: float, settings: Settings) -> int:
    return len(segment_starts(duration_s, settings.window_s, settings.step_s))


def check_budget(budget: QueryBudget, duration_s: float, settings: Settings) -> int:
    needed = estimate_queries(duration_s, settings)
    remaining = budget.remaining()
    if remaining is not None and remaining < needed:
        raise BudgetExhaustedError(
            f"Este set necesita unas {needed} consultas y solo quedan {remaining} en el "
            "presupuesto."
        )
    return needed


def _reporter(on_progress: ProgressCallback | None) -> Callable[..., None]:
    def report(
        phase: Phase, percent: float, message: str, tracklist: list[TracklistEntry] | None = None
    ) -> None:
        if on_progress:
            on_progress(Progress(phase, round(min(100.0, percent), 1), message, tracklist))

    return report


async def prepare_input(
    value: str,
    settings: Settings,
    *,
    on_progress: ProgressCallback | None = None,
    resolver: RedirectResolver | None = None,
) -> PreparedInput:
    """Valida la entrada y lee sus metadatos (o el hash del archivo) sin descargar nada."""
    report = _reporter(on_progress)
    report(Phase.DOWNLOADING, 0, "Validando la entrada")
    if looks_like_url(value):
        source = await asyncio.to_thread(
            resolve_source, value, resolver or http_redirect_resolver()
        )
        report(Phase.DOWNLOADING, 2, "Leyendo metadatos")
        meta = await asyncio.to_thread(
            ytdlp.fetch_metadata,
            source,
            max_duration_s=settings.max_duration_s,
            timeout=settings.metadata_timeout_s,
        )
        return PreparedInput(
            source_type=source.type,
            canonical_id=source.canonical_id,
            source=source.url,
            title=meta.title,
            uploader=meta.uploader,
            duration_s=meta.duration_s,
            origin=source,
            description=meta.description,
        )

    local = await asyncio.to_thread(Path(value).resolve)
    info = await asyncio.to_thread(
        ffmpeg.validate_local_file,
        local,
        max_bytes=settings.max_file_bytes,
        max_duration_s=settings.max_duration_s,
    )
    report(Phase.DOWNLOADING, 2, "Calculando la huella del archivo")
    return PreparedInput(
        source_type=SourceType.UPLOAD,
        canonical_id=await asyncio.to_thread(file_fingerprint, local),
        source=str(local),
        title=local.stem,
        uploader=None,
        duration_s=info.duration_s,
        origin=local,
    )


async def process_input(
    prepared: PreparedInput,
    settings: Settings,
    provider: RecognitionProvider,
    *,
    on_progress: ProgressCallback | None = None,
    budget: QueryBudget | None = None,
) -> PipelineResult:
    """Descarga, normaliza, segmenta, reconoce y agrega.

    Todo el audio vive en un directorio temporal que se borra siempre.
    """
    report = _reporter(on_progress)
    budget = budget or FixedBudget(settings.daily_query_budget)
    params = aggregation_params(settings)

    with job_workdir(settings.temp_root) as workdir:
        # 3. Descarga
        if isinstance(prepared.origin, Path):
            audio = prepared.origin
        else:
            report(Phase.DOWNLOADING, 5, "Descargando el audio")
            audio = await asyncio.to_thread(
                ytdlp.download_audio,
                prepared.origin,
                workdir,
                max_bytes=settings.max_file_bytes,
                timeout=settings.download_timeout_s,
            )
            # El archivo descargado también se valida por contenido.
            await asyncio.to_thread(
                ffmpeg.validate_local_file,
                audio,
                max_bytes=settings.max_file_bytes,
                max_duration_s=settings.max_duration_s,
            )

        # 4. Normalización
        report(Phase.DOWNLOADING, 25, "Normalizando el audio")
        wav = await asyncio.to_thread(
            ffmpeg.normalize, audio, workdir / "normalized.wav", timeout=settings.ffmpeg_timeout_s
        )
        total = estimate_queries(wav_duration(wav), settings)

        # 5-6. Segmentación perezosa y reconocimiento
        report(Phase.ANALYZING, 30, f"Analizando {total} segmentos")
        partial: list[SegmentResult] = []

        def on_result(result: SegmentResult) -> None:
            partial.append(result)
            report(
                Phase.ANALYZING,
                30 + 65 * len(partial) / max(total, 1),
                f"Segmento {len(partial)} de {total}",
                aggregate(partial, params),
            )

        # closing(): si el trabajo aborta, el WAV se cierra ya y se puede borrar (en
        # Windows un archivo abierto no se puede eliminar).
        with closing(
            iter_segments(wav, window_s=settings.window_s, step_s=settings.step_s)
        ) as segments:
            limits = settings.rate_limits()
            results, stats = await recognize_segments(
                segments,
                provider,
                concurrency=limits.concurrency,
                retry=RetryPolicy(
                    max_attempts=settings.max_attempts,
                    base_s=limits.backoff_base_s,
                    max_s=settings.backoff_max_s,
                ),
                min_interval_s=limits.min_interval_s,
                budget=budget,
                on_result=on_result,
            )

    # 7. Agregación (el audio ya está borrado en este punto)
    report(Phase.AGGREGATING, 96, "Agrupando resultados")
    tracklist = aggregate(results, params)
    report(Phase.DONE, 100, "Listo", tracklist)
    return PipelineResult(
        source_type=prepared.source_type,
        canonical_id=prepared.canonical_id,
        title=prepared.title,
        uploader=prepared.uploader,
        duration_s=prepared.duration_s,
        tracklist=tracklist,
        segments=results,
        stats=stats,
        provider=provider.name,
        description=prepared.description,
    )


async def run_pipeline(
    value: str,
    settings: Settings,
    provider: RecognitionProvider,
    *,
    on_progress: ProgressCallback | None = None,
    resolver: RedirectResolver | None = None,
    budget: QueryBudget | None = None,
) -> PipelineResult:
    budget = budget or FixedBudget(settings.daily_query_budget)
    prepared = await prepare_input(value, settings, on_progress=on_progress, resolver=resolver)
    check_budget(budget, prepared.duration_s, settings)
    return await process_input(prepared, settings, provider, on_progress=on_progress, budget=budget)

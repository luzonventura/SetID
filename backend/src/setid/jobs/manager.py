"""Gestor de trabajos: cola persistente con un único worker.

Un solo hilo con su propio bucle asyncio procesa los trabajos de uno en uno (un trabajo
activo cada vez). La interfaz llama a los métodos públicos desde otros hilos; los cambios
de estado se notifican a los suscriptores como eventos (diccionarios serializables).

Flujo de un trabajo::

    queued → downloading → (caché) → [espera de presupuesto] → analyzing → aggregating → done
                                                                          ↘ failed / cancelled
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from setid import proc
from setid.audio.ffmpeg import InvalidAudioError
from setid.community import Hint, parse_community
from setid.config import Settings
from setid.db.budget import DailyBudget
from setid.db.tables import Job, JobStatus, utcnow
from setid.jobs.repository import JobRepository
from setid.jobs.views import JobDetail, JobView, community_view, tracklist_views
from setid.models import SourceType, TracklistEntry
from setid.pipeline import (
    Phase,
    PreparedInput,
    Progress,
    check_budget,
    prepare_input,
    process_input,
)
from setid.providers.base import PermanentProviderError, RecognitionProvider
from setid.providers.registry import build_provider
from setid.recognize import BudgetExhaustedError
from setid.settings_store import SettingsStore
from setid.sources import ytdlp
from setid.sources.url import CanonicalSource, InvalidUrlError, RedirectResolver, parse_source_url
from setid.sources.ytdlp import SourceRejected
from setid.workdir import purge_stale

log = logging.getLogger(__name__)

Listener = Callable[[dict[str, Any]], None]
ProviderFactory = Callable[[Settings], RecognitionProvider]

MAX_QUEUED = 20
_PROGRESS_EVERY_S = 0.5
_BUDGET_RECHECK_S = 60.0

# Errores con un mensaje pensado para el usuario: se muestran tal cual.
_USER_ERRORS = (
    InvalidUrlError,
    InvalidAudioError,
    SourceRejected,
    PermanentProviderError,
    BudgetExhaustedError,
    proc.ProcessError,
)

_PHASE_STATUS = {
    Phase.DOWNLOADING: JobStatus.DOWNLOADING,
    Phase.ANALYZING: JobStatus.ANALYZING,
    Phase.AGGREGATING: JobStatus.AGGREGATING,
    Phase.DONE: JobStatus.AGGREGATING,  # «done» lo fija el gestor al guardar el resultado
}


class JobError(ValueError):
    """Petición no válida desde la interfaz. Mensaje apto para el usuario."""


class _Running:
    def __init__(self, job_id: int, task: asyncio.Task[None]) -> None:
        self.job_id = job_id
        self.task = task
        self.cancel = threading.Event()
        self.finished = threading.Event()


class JobManager:
    def __init__(
        self,
        engine: Engine,
        store: SettingsStore,
        *,
        provider_factory: ProviderFactory = build_provider,
        resolver: RedirectResolver | None = None,
    ) -> None:
        self.repo = JobRepository(engine)
        self._engine = engine
        self._store = store
        self._provider_factory = provider_factory
        self._resolver = resolver
        self._listeners: list[Listener] = []
        self._listeners_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[int | None] | None = None
        self._settings_changed: asyncio.Event | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = False
        self._running: _Running | None = None
        self._live: dict[int, list[TracklistEntry]] = {}

    # --- Ciclo de vida -------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        interrupted = self.repo.mark_interrupted()
        if interrupted:
            log.info("trabajos interrumpidos marcados como fallidos", extra={"count": interrupted})
        purge_stale(self._store.load().temp_root)
        self._thread = threading.Thread(target=self._thread_main, name="setid-jobs", daemon=True)
        self._thread.start()
        self._ready.wait()
        for job_id in self.repo.queued_ids():
            self._enqueue(job_id)

    def stop(self, timeout: float = 15.0) -> None:
        if self._thread is None or self._loop is None:
            return
        # Los trabajos en cola siguen «queued» en la base y se retoman al volver a arrancar.
        self._stopping = True
        running = self._running
        if running is not None:
            self._cancel_running(running)
        self._loop.call_soon_threadsafe(self._put, None)
        self._thread.join(timeout)
        self._thread = None

    def _thread_main(self) -> None:
        asyncio.run(self._worker())

    async def _worker(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._settings_changed = asyncio.Event()
        self._ready.set()
        while True:
            job_id = await self._queue.get()
            if job_id is None or self._stopping:
                break
            task = asyncio.create_task(self._execute(job_id))
            self._running = _Running(job_id, task)
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._running.finished.set()
                self._running = None
                self._live.pop(job_id, None)

    def _put(self, job_id: int | None) -> None:
        assert self._queue is not None  # noqa: S101
        self._queue.put_nowait(job_id)

    def _enqueue(self, job_id: int) -> None:
        if self._loop is None:
            raise RuntimeError("El gestor de trabajos no está iniciado")
        self._loop.call_soon_threadsafe(self._put, job_id)

    # --- Eventos ---------------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._listeners_lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._listeners_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _emit(self, event: dict[str, Any]) -> None:
        with self._listeners_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                log.exception("un suscriptor de eventos falló")

    def _emit_job(self, job: Job | None) -> None:
        if job is not None:
            self._emit({"type": "job", "job": JobView.of(job).model_dump(mode="json")})

    def _emit_tracklist(self, job_id: int, entries: list[TracklistEntry], *, live: bool) -> None:
        job = self.repo.get(job_id)
        if job is None:
            return
        view = JobView.of(job)
        hints = self.repo.hints(job_id)
        self._emit(
            {
                "type": "tracklist",
                "job_id": job_id,
                "live": live,
                "tracklist": [
                    v.model_dump(mode="json") for v in tracklist_views(view, entries, hints)
                ],
            }
        )

    def _emit_community(self, job_id: int) -> None:
        job = self.repo.get(job_id)
        if job is None:
            return
        community = community_view(JobView.of(job), self.repo.hints(job_id))
        self._emit(
            {"type": "community", "job_id": job_id, "community": community.model_dump(mode="json")}
        )

    # --- API pública (cualquier hilo) ------------------------------------------------------

    def submit_url(self, url: str, *, force: bool = False) -> JobView:
        parsed = parse_source_url(url)  # falla rápido con un mensaje claro
        if isinstance(parsed, CanonicalSource):
            source_type, source, canonical = parsed.type, parsed.url, parsed.canonical_id
        else:  # enlace corto: se resuelve en el worker
            source_type, source, canonical = SourceType.SOUNDCLOUD, parsed.url, None
        return self._submit(source_type, source, canonical, force)

    def submit_file(self, path: str, *, force: bool = False) -> JobView:
        file = Path(path)
        if not file.is_file():
            raise JobError("El archivo no existe.")
        return self._submit(SourceType.UPLOAD, str(file.resolve()), None, force)

    def _submit(
        self, source_type: SourceType, source: str, canonical: str | None, force: bool
    ) -> JobView:
        if self.repo.count_queued() >= MAX_QUEUED:
            raise JobError(f"Ya hay {MAX_QUEUED} trabajos en cola. Espera a que avancen.")
        settings = self._store.load()
        job = self.repo.add(
            Job(
                source_type=source_type,
                source=source,
                canonical_id=canonical,
                provider=settings.provider.value,
                force=force,
                message="En cola",
            )
        )
        assert job.id is not None  # noqa: S101
        self._emit_job(job)
        self._enqueue(job.id)
        return JobView.of(job)

    def list_jobs(self, limit: int = 50) -> list[JobView]:
        return [JobView.of(j) for j in self.repo.list_recent(limit)]

    def get_job(self, job_id: int) -> JobDetail:
        job = self.repo.get(job_id)
        if job is None:
            raise JobError("El trabajo no existe.")
        view = JobView.of(job)
        live = job_id in self._live
        entries = self._live[job_id] if live else self.repo.entries(job_id)
        hints = self.repo.hints(job_id)
        return JobDetail(
            **view.model_dump(),
            tracklist=tracklist_views(view, entries, hints),
            live=live,
            community=community_view(view, hints),
        )

    def cancel(self, job_id: int) -> JobView:
        job = self.repo.get(job_id)
        if job is None:
            raise JobError("El trabajo no existe.")
        running = self._running
        if running is not None and running.job_id == job_id:
            self._cancel_running(running)
            running.finished.wait(10)
        elif job.status is JobStatus.QUEUED:
            self._finish(job_id, JobStatus.CANCELLED, message="Cancelado")
        updated = self.repo.get(job_id)
        assert updated is not None  # noqa: S101
        return JobView.of(updated)

    def delete(self, job_id: int) -> None:
        job = self.repo.get(job_id)
        if job is None:
            raise JobError("El trabajo no existe.")
        if not job.status.is_final:
            self.cancel(job_id)
        self.repo.delete(job_id)
        self._emit({"type": "job_deleted", "job_id": job_id})

    def notify_settings_changed(self) -> None:
        """Despierta a un trabajo que espera presupuesto, por si se ha ampliado."""
        if self._loop is not None and self._settings_changed is not None:
            self._loop.call_soon_threadsafe(self._settings_changed.set)

    def budget_status(self) -> dict[str, Any]:
        settings = self._store.load()
        budget = DailyBudget(
            self._engine, provider=settings.provider.value, limit=settings.daily_query_budget
        )
        return {
            "provider": settings.provider.value,
            "used_today": budget.used(),
            "limit": settings.daily_query_budget,
            "remaining": budget.remaining(),
        }

    def _cancel_running(self, running: _Running) -> None:
        # Primero se mata el proceso externo (si hay uno) y después se cancela la tarea, para
        # que el directorio temporal se pueda borrar enseguida.
        running.cancel.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(running.task.cancel)

    # --- Ejecución (hilo del worker) -------------------------------------------------------

    def _update(self, job_id: int, **fields: Any) -> Job | None:
        job = self.repo.update(job_id, **fields)
        self._emit_job(job)
        return job

    def _finish(self, job_id: int, status: JobStatus, **fields: Any) -> None:
        self._update(job_id, status=status, finished_at=utcnow(), **fields)

    async def _execute(self, job_id: int) -> None:
        job = self.repo.get(job_id)
        if job is None or job.status is not JobStatus.QUEUED:
            return
        running = self._running
        assert running is not None  # noqa: S101
        token = proc.cancel_event.set(running.cancel)
        provider: RecognitionProvider | None = None
        community: asyncio.Task[list[Hint]] | None = None
        settings = self._store.load()
        try:
            self._update(
                job_id,
                status=JobStatus.DOWNLOADING,
                started_at=utcnow(),
                progress=0.0,
                message="Preparando",
                error=None,
            )
            on_progress = self._progress_handler(job_id)
            prepared = await prepare_input(
                job.source, settings, on_progress=on_progress, resolver=self._resolver
            )
            self._update(
                job_id,
                canonical_id=prepared.canonical_id,
                source=prepared.source,
                title=prepared.title,
                uploader=prepared.uploader,
                duration_s=prepared.duration_s,
            )
            if not job.force and self._use_cache(job_id, prepared):
                return

            # Los comentarios se leen en paralelo con el análisis: no añaden espera.
            if settings.community_enabled and isinstance(prepared.origin, CanonicalSource):
                community = asyncio.create_task(
                    self._fetch_community(job_id, prepared.origin, settings)
                )
            provider = self._provider_factory(settings)
            budget = await self._wait_for_budget(job_id, prepared, settings, provider)
            result = await process_input(
                prepared, settings, provider, on_progress=on_progress, budget=budget
            )
            if community is not None:
                if not community.done():
                    self._update(job_id, message="Buscando el tracklist en los comentarios")
                self.repo.replace_hints(job_id, await community)
            self.repo.replace_entries(job_id, result.tracklist)
            self._live.pop(job_id, None)
            self._finish(
                job_id,
                JobStatus.DONE,
                progress=100.0,
                message="Listo",
                queries_used=result.stats.queries,
                retries=result.stats.retries,
                estimated_cost=result.stats.cost,
            )
            self._emit_tracklist(job_id, result.tracklist, live=False)
            self._emit_community(job_id)
        except asyncio.CancelledError:
            self._finish(job_id, JobStatus.CANCELLED, message="Cancelado")
        except _USER_ERRORS as exc:
            self._finish(job_id, JobStatus.FAILED, message="Error", error=str(exc))
        except Exception:
            log.exception("error inesperado procesando un trabajo", extra={"job_id": job_id})
            self._finish(
                job_id,
                JobStatus.FAILED,
                message="Error",
                error="Error inesperado. Revisa el registro de la app.",
            )
        finally:
            if community is not None and not community.done():
                community.cancel()
            proc.cancel_event.reset(token)
            if provider is not None:
                await provider.aclose()

    def _use_cache(self, job_id: int, prepared: PreparedInput) -> bool:
        cached = self.repo.find_cached(prepared.canonical_id, exclude_id=job_id)
        if cached is None or cached.id is None:
            return False
        entries = self.repo.entries(cached.id)
        self.repo.replace_entries(job_id, entries)
        self.repo.replace_hints(job_id, self.repo.hints(cached.id))
        self._finish(
            job_id,
            JobStatus.DONE,
            progress=100.0,
            message="Resultado guardado (sin nuevas consultas)",
            cached_from_id=cached.id,
            provider=cached.provider,
        )
        self._emit_tracklist(job_id, entries, live=False)
        self._emit_community(job_id)
        return True

    async def _fetch_community(
        self, job_id: int, source: CanonicalSource, settings: Settings
    ) -> list[Hint]:
        """Descripción y comentarios. Si falla, el trabajo sigue: es información extra."""
        try:
            data = await asyncio.to_thread(
                ytdlp.fetch_community,
                source,
                max_comments=settings.community_max_comments,
                timeout=settings.community_timeout_s,
            )
        except proc.ProcessCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "no se pudieron leer los comentarios",
                extra={"job_id": job_id, "error": type(exc).__name__},
            )
            return []
        return parse_community(data.description, data.comments).all

    async def _wait_for_budget(
        self,
        job_id: int,
        prepared: PreparedInput,
        settings: Settings,
        provider: RecognitionProvider,
    ) -> DailyBudget:
        assert self._settings_changed is not None  # noqa: S101
        while True:
            budget = DailyBudget(
                self._engine,
                provider=provider.name,
                limit=settings.daily_query_budget,
                cost_per_query=provider.cost_per_query,
            )
            try:
                check_budget(budget, prepared.duration_s, settings)
                return budget
            except BudgetExhaustedError as exc:
                self._update(
                    job_id,
                    status=JobStatus.QUEUED,
                    message=(
                        f"{exc} Seguirá en cola hasta que haya presupuesto (mañana, o antes "
                        "si lo amplías en Ajustes)."
                    ),
                )
            self._settings_changed.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._settings_changed.wait(), _BUDGET_RECHECK_S)
            # El límite puede haber cambiado; el proveedor no (se fijó al empezar).
            settings = self._store.load().model_copy(update={"provider": settings.provider})

    def _progress_handler(self, job_id: int) -> Callable[[Progress], None]:
        state: dict[str, Any] = {"phase": None, "written": 0.0, "tracks": None}

        def handle(progress: Progress) -> None:
            now = time.monotonic()
            status = _PHASE_STATUS[progress.phase]
            changed_phase = status != state["phase"]
            # Se escribe en la base y se notifica como mucho cada _PROGRESS_EVERY_S, salvo
            # cambios de fase, que van siempre.
            if changed_phase or now - state["written"] >= _PROGRESS_EVERY_S:
                state["written"] = now
                state["phase"] = status
                self._update(
                    job_id, status=status, progress=progress.percent, message=progress.message
                )
            if progress.tracklist is not None:
                self._live[job_id] = progress.tracklist
                signature = [(e.title, e.start_s, e.source) for e in progress.tracklist]
                if signature != state["tracks"]:
                    state["tracks"] = signature
                    self._emit_tracklist(job_id, progress.tracklist, live=True)

        return handle

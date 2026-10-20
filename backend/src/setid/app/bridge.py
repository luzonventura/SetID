"""API que la interfaz llama a través del puente de pywebview (``window.pywebview.api``).

Seguridad:

* pywebview expone a JavaScript todos los métodos públicos del objeto **y de sus
  atributos públicos**. Por eso todo el estado interno va en atributos con ``_``: si no, la
  página podría llamar, por ejemplo, a ``api.manager.repo.delete``.
* Toda entrada se valida aquí (tipos, rangos, enums). Nada llega a un shell.
* Las claves de API se pueden escribir pero nunca leer desde la interfaz.
* Solo se abren en el navegador del sistema URLs https de una lista blanca de hosts.

Cada método devuelve ``{"ok": true, "data": ...}`` o ``{"ok": false, "error": "..."}``.
"""

from __future__ import annotations

import functools
import logging
import webbrowser
from collections.abc import Callable
from typing import Any, ParamSpec, Protocol

from pydantic import BaseModel, ValidationError

from setid import __version__
from setid.exports import ExportFormat, ExportMeta, export
from setid.jobs.manager import JobError, JobManager
from setid.links import is_allowed_external
from setid.settings_store import SettingsStore, UnknownSettingError
from setid.sources.url import InvalidUrlError

log = logging.getLogger(__name__)

LEGAL_NOTICE = (
    "Herramienta de uso personal. Descargar contenido de YouTube puede contravenir sus "
    "términos de servicio; la opción recomendada es usar tu propio archivo. El audio nunca "
    "se almacena ni se redistribuye."
)

MAX_INPUT_LENGTH = 4096


class WindowPort(Protocol):
    """Lo que el puente necesita de la ventana nativa (lo implementa la capa de pywebview)."""

    def pick_audio_file(self) -> str | None: ...

    def save_file(self, suggested_name: str, content: str) -> str | None: ...


class BridgeInputError(ValueError):
    pass


P = ParamSpec("P")


def _endpoint[**P](func: Callable[P, Any]) -> Callable[P, dict[str, Any]]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            data = func(*args, **kwargs)
        except (JobError, InvalidUrlError, BridgeInputError, UnknownSettingError) as exc:
            return {"ok": False, "error": str(exc)}
        except ValidationError as exc:
            fields = ", ".join(str(e["loc"][0]) for e in exc.errors() if e.get("loc"))
            return {"ok": False, "error": f"Valor no válido en: {fields}"}
        except Exception:
            log.exception("error inesperado en el puente", extra={"endpoint": func.__name__})
            return {"ok": False, "error": "Error inesperado. Revisa el registro de la app."}
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        elif isinstance(data, list):
            data = [d.model_dump(mode="json") if isinstance(d, BaseModel) else d for d in data]
        return {"ok": True, "data": data}

    return wrapper


def _job_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BridgeInputError("Identificador de trabajo no válido.")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeInputError(f"Falta {name}.")
    if len(value) > MAX_INPUT_LENGTH:
        raise BridgeInputError(f"{name.capitalize()} es demasiado largo.")
    return value.strip()


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise BridgeInputError("Valor booleano no válido.")
    return value


class Api:
    def __init__(
        self,
        manager: JobManager,
        store: SettingsStore,
        window: WindowPort | None = None,
        open_url: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self._manager = manager
        self._store = store
        self._window = window
        self._open_url = open_url

    def _bind_window(self, window: WindowPort) -> None:
        self._window = window

    # --- Trabajos --------------------------------------------------------------------------

    @_endpoint
    def create_job(self, url: object, force: object = False) -> Any:
        return self._manager.submit_url(_text(url, "el enlace"), force=_flag(force))

    @_endpoint
    def create_job_from_file(self, path: object = None, force: object = False) -> Any:
        if path is None:
            if self._window is None:
                raise BridgeInputError("No hay ventana para elegir archivo.")
            chosen = self._window.pick_audio_file()
            if chosen is None:
                return None  # el usuario canceló el diálogo
            path = chosen
        return self._manager.submit_file(_text(path, "el archivo"), force=_flag(force))

    @_endpoint
    def list_jobs(self, limit: object = 50) -> Any:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise BridgeInputError("Límite no válido.")
        return self._manager.list_jobs(max(1, min(limit, 200)))

    @_endpoint
    def get_job(self, job_id: object) -> Any:
        return self._manager.get_job(_job_id(job_id))

    @_endpoint
    def cancel_job(self, job_id: object) -> Any:
        return self._manager.cancel(_job_id(job_id))

    @_endpoint
    def delete_job(self, job_id: object) -> Any:
        self._manager.delete(_job_id(job_id))
        return None

    # --- Exportación -----------------------------------------------------------------------

    def _export(self, job_id: object, fmt: object) -> Any:
        try:
            export_format = ExportFormat(str(fmt))
        except ValueError as exc:
            raise BridgeInputError("Formato de exportación no válido.") from exc
        job = self._manager.get_job(_job_id(job_id))
        if job.live:
            raise BridgeInputError("El trabajo todavía no ha terminado.")
        meta = ExportMeta(
            title=job.title or "tracklist",
            uploader=job.uploader,
            duration_s=job.duration_s,
            source=None if job.source_type.value == "upload" else job.source,
            provider=job.provider,
        )
        entries = self._manager.repo.entries(job.id)
        return export(export_format, meta, entries)

    @_endpoint
    def export_job(self, job_id: object, fmt: object) -> Any:
        """Devuelve el contenido (p. ej. para «copiar como texto»)."""
        file = self._export(job_id, fmt)
        return {"filename": file.filename, "media_type": file.media_type, "content": file.content}

    @_endpoint
    def save_export(self, job_id: object, fmt: object) -> Any:
        """Abre el diálogo nativo de «Guardar como» y escribe el archivo."""
        if self._window is None:
            raise BridgeInputError("No hay ventana para guardar el archivo.")
        file = self._export(job_id, fmt)
        path = self._window.save_file(file.filename, file.content)
        return {"path": path}

    # --- Ajustes ---------------------------------------------------------------------------

    @_endpoint
    def get_settings(self) -> Any:
        return self._store.public_view()

    @_endpoint
    def update_settings(self, changes: object) -> Any:
        if not isinstance(changes, dict) or not all(isinstance(k, str) for k in changes):
            raise BridgeInputError("Ajustes no válidos.")
        settings = self._store.update(changes)
        self._manager.notify_settings_changed()
        return self._store.public_view(settings)

    @_endpoint
    def reset_settings(self, names: object) -> Any:
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise BridgeInputError("Ajustes no válidos.")
        settings = self._store.reset(names)
        self._manager.notify_settings_changed()
        return self._store.public_view(settings)

    @_endpoint
    def set_secret(self, name: object, value: object) -> Any:
        if not isinstance(name, str) or not (value is None or isinstance(value, str)):
            raise BridgeInputError("Credencial no válida.")
        if isinstance(value, str) and len(value) > MAX_INPUT_LENGTH:
            raise BridgeInputError("Credencial demasiado larga.")
        self._store.set_secret(name, value)
        return self._store.public_view()["secrets"]

    @_endpoint
    def get_budget(self) -> Any:
        return self._manager.budget_status()

    # --- Varios ----------------------------------------------------------------------------

    @_endpoint
    def open_external(self, url: object) -> Any:
        target = _text(url, "el enlace")
        if not is_allowed_external(target):
            raise BridgeInputError("Ese enlace no se puede abrir desde la app.")
        self._open_url(target)
        return None

    @_endpoint
    def app_info(self) -> Any:
        return {
            "version": __version__,
            "data_dir": str(self._store.data_dir),
            "legal_notice": LEGAL_NOTICE,
        }

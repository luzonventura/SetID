"""Ventana de escritorio (pywebview + WebView2) que sirve la interfaz compilada.

Uso::

    uv run setid-app                      # interfaz compilada (frontend/dist)
    SETID_DEV_URL=http://localhost:5173 uv run setid-app   # contra el servidor de Vite

Seguridad de la ventana:

* Solo carga los archivos locales de la interfaz (o, en desarrollo, un servidor en
  localhost). Nunca una web remota: la página tiene acceso al puente con Python.
* Sin URLs ``file://``, sin descargas y sin abrir enlaces por su cuenta: los enlaces
  externos pasan por ``Api.open_external``, que aplica una lista blanca.
* La ruta real de un archivo soltado solo la conoce Python; la página recibe el trabajo
  ya creado.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from setid.app.context import AppContext, create_app
from setid.jobs.manager import JobError, JobManager
from setid.jobs.views import JobView

log = logging.getLogger(__name__)

AUDIO_FILE_TYPES = (
    "Audio (*.wav;*.mp3;*.flac;*.aiff;*.aif;*.m4a;*.aac;*.ogg;*.opus;*.wma)",
    "Todos los archivos (*.*)",
)
EVENT_NAME = "setid:event"
_DEV_HOSTS = {"localhost", "127.0.0.1"}


class NativeWindow(Protocol):
    """Subconjunto de ``webview.Window`` que se usa aquí (permite testear sin GUI)."""

    def create_file_dialog(self, *args: Any, **kwargs: Any) -> Any: ...

    def run_js(self, script: str) -> Any: ...


APP_USER_MODEL_ID = "SetID.Desktop"


def icon_path() -> Path | None:
    """Icono de la ventana (setid.ico), tanto en desarrollo como en el ejecutable."""
    candidates = [Path(__file__).with_name("assets") / "setid.ico"]
    if bundle := getattr(sys, "_MEIPASS", None):
        candidates.insert(0, Path(bundle) / "setid" / "app" / "assets" / "setid.ico")
    return next((p for p in candidates if p.is_file()), None)


def set_taskbar_identity() -> None:
    """Identidad propia en la barra de tareas de Windows.

    Sin esto, al lanzar con ``python.exe`` Windows agrupa la ventana con Python y muestra su
    icono. Con un AppUserModelID propio usa el icono de la ventana y no la mezcla con otras.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        log.debug("no se pudo fijar el AppUserModelID")


def frontend_entry() -> Path:
    """Localiza ``index.html`` de la interfaz compilada."""
    candidates = []
    if override := os.environ.get("SETID_FRONTEND_DIR"):
        candidates.append(Path(override))
    if bundle := getattr(sys, "_MEIPASS", None):  # ejecutable de PyInstaller (fase 4)
        candidates.append(Path(bundle) / "frontend")
    candidates.append(Path(__file__).resolve().parents[4] / "frontend" / "dist")
    for directory in candidates:
        if (directory / "index.html").is_file():
            return directory / "index.html"
    raise FileNotFoundError(
        "No se encuentra la interfaz compilada. Ejecuta `npm run build` en frontend/."
    )


def dev_url() -> str | None:
    url = os.environ.get("SETID_DEV_URL")
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in _DEV_HOSTS:
        raise ValueError("SETID_DEV_URL solo puede apuntar a http://localhost")
    return url


def event_script(event: dict[str, Any]) -> str:
    # JSON es un literal válido de JavaScript: los datos (títulos, artistas…) no pueden
    # romper la cadena ni inyectar código.
    payload = json.dumps(event, ensure_ascii=True)
    return f"window.dispatchEvent(new CustomEvent({json.dumps(EVENT_NAME)}, {{detail: {payload}}}))"


class DesktopWindow:
    """Implementa ``WindowPort`` del puente y reenvía eventos a la página."""

    def __init__(self, window: NativeWindow, open_dialog: int, save_dialog: int) -> None:
        self._window = window
        self._open = open_dialog
        self._save = save_dialog

    def pick_audio_file(self) -> str | None:
        result = self._window.create_file_dialog(
            self._open, allow_multiple=False, file_types=AUDIO_FILE_TYPES
        )
        return str(result[0]) if result else None

    def save_file(self, suggested_name: str, content: str) -> str | None:
        result = self._window.create_file_dialog(self._save, save_filename=suggested_name)
        if not result:
            return None
        target = Path(result if isinstance(result, str) else result[0])
        target.write_text(content, encoding="utf-8", newline="")
        return str(target)

    def emit(self, event: dict[str, Any]) -> None:
        try:
            self._window.run_js(event_script(event))
        except Exception:  # noqa: BLE001
            # La ventana puede estar cerrándose; no debe tumbar al worker.
            log.debug("no se pudo enviar un evento a la ventana")


def handle_drop(
    event: dict[str, Any], manager: JobManager, emit: Callable[[dict[str, Any]], None]
) -> None:
    files = (event.get("dataTransfer") or {}).get("files") or []
    raw = [f.get("pywebviewFullPath") for f in files if isinstance(f, dict)]
    paths = [p for p in raw if isinstance(p, str) and p]
    if not paths:
        emit({"type": "error", "error": "No se pudo leer el archivo soltado."})
        return
    if len(paths) > 1:
        emit({"type": "error", "error": "Suelta un único archivo cada vez."})
        return
    try:
        job: JobView = manager.submit_file(paths[0])
    except JobError as exc:
        emit({"type": "error", "error": str(exc)})
        return
    emit({"type": "file_dropped", "job": job.model_dump(mode="json")})


def run(context: AppContext | None = None) -> None:
    import webview
    from webview.dom import DOMEventHandler

    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = True

    set_taskbar_identity()
    ctx = context or create_app()
    url = dev_url() or str(frontend_entry())
    window = webview.create_window(
        "SetID",
        url,
        js_api=ctx.api,
        width=1240,
        height=860,
        min_size=(420, 560),
        background_color="#0A0A0B",
        text_select=True,
    )
    if window is None:
        return
    desktop = DesktopWindow(window, webview.FileDialog.OPEN, webview.FileDialog.SAVE)
    ctx.api._bind_window(desktop)
    unsubscribe = ctx.manager.subscribe(desktop.emit)

    def on_loaded() -> None:
        # Los manejadores DOM se pierden al recargar la página: se registran en cada carga.
        # (Los tipos de pywebview no declaran DOMEventHandler en Event.__iadd__, aunque es
        # el uso documentado.)
        doc = window.dom.document
        doc.events.dragover += DOMEventHandler(lambda _e: None, True, True, debounce=500)  # type: ignore[arg-type]
        doc.events.drop += DOMEventHandler(  # type: ignore[arg-type]
            lambda e: handle_drop(e, ctx.manager, desktop.emit), True, True
        )

    def on_closed() -> None:
        unsubscribe()
        ctx.close()

    window.events.loaded += on_loaded
    window.events.closed += on_closed
    icon = icon_path()
    webview.start(
        debug=bool(os.environ.get("SETID_DEBUG")),
        private_mode=True,
        icon=str(icon) if icon else None,
    )


def main() -> None:
    run()

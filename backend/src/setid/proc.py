"""Ejecución segura de procesos externos: siempre lista de argumentos, nunca shell.

Los procesos se pueden cancelar: si el contexto actual tiene un evento de cancelación
(:data:`cancel_event`) y se activa, el proceso se mata. ``asyncio.to_thread`` copia el
contexto, así que basta con fijarlo en la tarea del trabajo.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

_STDERR_TAIL = 2000
_POLL_S = 0.25

cancel_event: ContextVar[threading.Event | None] = ContextVar("cancel_event", default=None)


class ProcessError(RuntimeError):
    def __init__(self, program: str, message: str, stderr: str = "") -> None:
        super().__init__(f"{program}: {message}")
        self.program = program
        self.stderr = stderr[-_STDERR_TAIL:]


class ProcessTimeout(ProcessError):
    pass


class ProcessCancelled(ProcessError):
    pass


class ProgramNotFound(ProcessError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    stdout: str
    stderr: str


def _creation_flags() -> int:
    # Evita que se abra una consola por cada proceso cuando corre dentro de la app.
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _kill(process: subprocess.Popen[str]) -> None:
    process.kill()
    process.communicate()


def run(args: Sequence[str], *, timeout: float, program: str | None = None) -> ProcessResult:
    if isinstance(args, str) or not all(isinstance(a, str) for a in args):
        raise TypeError("args debe ser una lista de str")
    name = program or args[0]
    cancel = cancel_event.get()
    if cancel is not None and cancel.is_set():
        raise ProcessCancelled(name, "cancelado")
    try:
        process = subprocess.Popen(
            list(args),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        )
    except FileNotFoundError as exc:
        raise ProgramNotFound(name, "no está instalado o no está en el PATH") from exc

    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = process.communicate(timeout=_POLL_S)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                _kill(process)
                raise ProcessCancelled(name, "cancelado") from None
            if time.monotonic() > deadline:
                _kill(process)
                raise ProcessTimeout(name, f"tiempo agotado tras {timeout:.0f} s") from None

    if process.returncode != 0:
        raise ProcessError(name, f"terminó con código {process.returncode}", stderr)
    return ProcessResult(stdout, stderr)


CLI_EXE = "setid-cli.exe"
YT_DLP_FLAG = "--yt-dlp"


def yt_dlp_command() -> list[str]:
    """yt-dlp se ejecuta desde el propio entorno, con la versión fijada en uv.lock.

    En el ejecutable empaquetado no hay ``python -m``: lo ejecuta ``setid-cli.exe``, que va
    junto a ``SetID.exe`` y lleva yt-dlp dentro.
    """
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).with_name(CLI_EXE)), YT_DLP_FLAG]
    return [sys.executable, "-m", "yt_dlp"]

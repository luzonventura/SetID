"""Directorios temporales por trabajo que se borran siempre, incluso si el trabajo falla."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

_PREFIX = "job-"


def _remove(path: Path, attempts: int = 5) -> None:
    # En Windows un archivo recién cerrado por otro proceso puede seguir bloqueado un
    # instante (antivirus, indexador), así que se reintenta.
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


@contextmanager
def job_workdir(root: Path) -> Iterator[Path]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_PREFIX}{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        _remove(path)


# Más que la suma de todos los timeouts de un trabajo: un directorio así de antiguo no
# puede pertenecer a un trabajo vivo (de esta app o de una CLI lanzada en paralelo).
STALE_AFTER_S = 6 * 3600


def purge_stale(root: Path, *, older_than_s: float = STALE_AFTER_S) -> int:
    """Borra restos de trabajos anteriores (p. ej. si el proceso murió). Devuelve cuántos."""
    if not root.is_dir():
        return 0
    removed = 0
    cutoff = time.time() - older_than_s
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith(_PREFIX) and child.stat().st_mtime <= cutoff:
            try:
                _remove(child)
                removed += 1
            except OSError:
                log.warning("no se pudo borrar un directorio temporal antiguo")
    return removed

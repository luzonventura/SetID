"""Carátulas de los tracks.

Solo se aceptan imágenes servidas por https desde la CDN de Apple (``*.mzstatic.com``): es
de donde las sirven Shazam, AudD (Apple Music) y la búsqueda pública de iTunes, y la CSP de
la interfaz solo permite ese origen para imágenes.

Para los tracks sin carátula se consulta la API pública de búsqueda de iTunes (sin clave) y
el resultado solo se acepta si título y artista coinciden con el track identificado.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from setid.aggregate import normalize_artist, normalize_title

log = logging.getLogger(__name__)

ARTWORK_HOST_SUFFIX = ".mzstatic.com"
ITUNES_SEARCH = "https://itunes.apple.com/search"
COVER_SIZE = 600
# iTunes permite ~20 peticiones por minuto: una cada 3,2 s va sobrada.
LOOKUP_INTERVAL_S = 3.2

_SIZE_IN_URL = re.compile(r"/\d+x\d+(bb|cc|-\d+)?\.(jpg|jpeg|png|webp)$", re.IGNORECASE)


def safe_artwork_url(url: object, size: int = COVER_SIZE) -> str | None:
    """Devuelve la URL de la carátula normalizada a ``size`` px, o ``None`` si no es fiable."""
    if not isinstance(url, str) or len(url) > 1000:
        return None
    url = url.replace("{w}", str(size)).replace("{h}", str(size))
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.port is not None:
        return None
    if not host.endswith(ARTWORK_HOST_SUFFIX):
        return None
    # Pide la resolución que usa la interfaz en lugar de la miniatura de 100 px.
    path = _SIZE_IN_URL.sub(rf"/{size}x{size}bb.jpg", parts.path)
    return f"https://{host}{path}"


def _same_track(artist: str, title: str, cand_artist: str, cand_title: str) -> bool:
    if normalize_title(title) != normalize_title(cand_title):
        return False
    wanted = set(normalize_artist(artist).split(" & "))
    found = set(normalize_artist(cand_artist).split(" & "))
    return bool(wanted & found)


def pick_itunes_result(artist: str, title: str, payload: Any) -> str | None:
    """Elige, de una respuesta de la búsqueda de iTunes, la carátula del mismo track."""
    if not isinstance(payload, dict):
        return None
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        cand_artist = str(item.get("artistName") or "")
        cand_title = str(item.get("trackName") or "")
        if _same_track(artist, title, cand_artist, cand_title):
            return safe_artwork_url(item.get("artworkUrl100"))
    return None


class ArtworkCache(Protocol):
    def get(self, key: str) -> tuple[bool, str | None]:
        """(encontrado, url). Una búsqueda sin resultado también se guarda (url None)."""
        ...

    def put(self, key: str, url: str | None) -> None: ...


def cache_key(artist: str, title: str) -> str:
    return f"{normalize_artist(artist)}|{normalize_title(title)}"


class ArtworkFinder:
    """Busca carátulas en iTunes respetando su límite de peticiones y con caché."""

    def __init__(
        self,
        cache: ArtworkCache,
        *,
        client: httpx.AsyncClient | None = None,
        interval_s: float = LOOKUP_INTERVAL_S,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache = cache
        self._client = client or httpx.AsyncClient(timeout=8.0)
        self._interval = interval_s
        self._sleep = sleep
        self._clock = clock
        self._next = 0.0

    async def find(self, artist: str, title: str) -> str | None:
        key = cache_key(artist, title)
        hit, url = self._cache.get(key)
        if hit:
            return url
        wait = self._next - self._clock()
        if wait > 0:
            await self._sleep(wait)
        self._next = self._clock() + self._interval
        try:
            response = await self._client.get(
                ITUNES_SEARCH,
                params={
                    "term": f"{artist} {title}"[:200],
                    "media": "music",
                    "entity": "song",
                    "limit": "10",
                },
            )
        except httpx.HTTPError:
            log.info("búsqueda de carátula sin respuesta")
            return None
        if response.status_code != 200:
            # 403/429 = límite de iTunes: no se cachea, se reintentará otro día.
            return None
        try:
            url = pick_itunes_result(artist, title, response.json())
        except ValueError:
            return None
        self._cache.put(key, url)
        return url

    async def aclose(self) -> None:
        await self._client.aclose()

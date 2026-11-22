"""Carátulas y preescuchas de los tracks.

Las dos vienen de Apple, que es de donde las sirven Shazam, AudD (Apple Music) y la búsqueda
pública de iTunes:

* Carátulas: imágenes por https desde su CDN (``*.mzstatic.com``).
* Preescuchas: fragmentos de unos 30 s en AAC (``.m4a``) desde ``*.itunes.apple.com``.

La CSP de la interfaz solo permite esos orígenes para imágenes y audio, y aquí se rechaza
cualquier otra URL antes de guardarla.

Para los tracks a los que les falta alguna de las dos se consulta la API pública de búsqueda
de iTunes (sin clave) y el resultado solo se acepta si título y artista coinciden con el track
identificado.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, Protocol
from urllib.parse import urlsplit

import httpx

from setid.aggregate import normalize_artist, normalize_title

log = logging.getLogger(__name__)

ARTWORK_HOST_SUFFIX = ".mzstatic.com"
PREVIEW_HOST_SUFFIX = ".itunes.apple.com"
ITUNES_SEARCH = "https://itunes.apple.com/search"
COVER_SIZE = 600
# iTunes permite ~20 peticiones por minuto: una cada 3,2 s va sobrada.
LOOKUP_INTERVAL_S = 3.2

_SIZE_IN_URL = re.compile(r"/\d+x\d+(bb|cc|-\d+)?\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
_AUDIO_EXTENSIONS = (".m4a", ".aac", ".mp3")


class TrackMedia(NamedTuple):
    cover_url: str | None = None
    preview_url: str | None = None


NO_MEDIA = TrackMedia()


def _https_parts(url: object, host_suffix: str) -> tuple[str, str] | None:
    """(host, ruta) si es https al dominio indicado, sin credenciales ni puerto."""
    if not isinstance(url, str) or len(url) > 1000:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.port is not None:
        return None
    if not host.endswith(host_suffix):
        return None
    return host, parts.path


def safe_artwork_url(url: object, size: int = COVER_SIZE) -> str | None:
    """Devuelve la URL de la carátula normalizada a ``size`` px, o ``None`` si no es fiable."""
    if isinstance(url, str):
        url = url.replace("{w}", str(size)).replace("{h}", str(size))
    checked = _https_parts(url, ARTWORK_HOST_SUFFIX)
    if checked is None:
        return None
    host, path = checked
    # Pide la resolución que usa la interfaz en lugar de la miniatura de 100 px.
    path = _SIZE_IN_URL.sub(rf"/{size}x{size}bb.jpg", path)
    return f"https://{host}{path}"


def safe_preview_url(url: object) -> str | None:
    """Devuelve la URL de la preescucha de Apple, o ``None`` si no es fiable."""
    checked = _https_parts(url, PREVIEW_HOST_SUFFIX)
    if checked is None:
        return None
    host, path = checked
    if not path.lower().endswith(_AUDIO_EXTENSIONS):
        return None
    return f"https://{host}{path}"


def _same_track(artist: str, title: str, cand_artist: str, cand_title: str) -> bool:
    if normalize_title(title) != normalize_title(cand_title):
        return False
    wanted = set(normalize_artist(artist).split(" & "))
    found = set(normalize_artist(cand_artist).split(" & "))
    return bool(wanted & found)


def pick_itunes_result(artist: str, title: str, payload: Any) -> TrackMedia:
    """Elige, de una respuesta de la búsqueda de iTunes, la carátula y la preescucha del
    mismo track. Si varias versiones coinciden, completa con la siguiente lo que le falte a
    la primera."""
    cover = preview = None
    if not isinstance(payload, dict):
        return NO_MEDIA
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        cand_artist = str(item.get("artistName") or "")
        cand_title = str(item.get("trackName") or "")
        if not _same_track(artist, title, cand_artist, cand_title):
            continue
        cover = cover or safe_artwork_url(item.get("artworkUrl100"))
        preview = preview or safe_preview_url(item.get("previewUrl"))
        if cover and preview:
            break
    return TrackMedia(cover, preview)


class ArtworkCache(Protocol):
    def get(self, key: str) -> TrackMedia | None:
        """Lo guardado para ese track, o ``None`` si nunca se buscó. Una búsqueda sin
        resultado también se guarda (``NO_MEDIA``)."""
        ...

    def put(self, key: str, media: TrackMedia) -> None: ...


def cache_key(artist: str, title: str) -> str:
    """Identidad de un track (artista y título normalizados), la misma en cualquier set."""
    return f"{normalize_artist(artist)}|{normalize_title(title)}"


class ArtworkFinder:
    """Busca carátulas y preescuchas en iTunes respetando su límite de peticiones y con
    caché."""

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

    async def find(self, artist: str, title: str) -> TrackMedia:
        key = cache_key(artist, title)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
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
            log.info("búsqueda en iTunes sin respuesta")
            return NO_MEDIA
        if response.status_code != 200:
            # 403/429 = límite de iTunes: no se cachea, se reintentará otro día.
            return NO_MEDIA
        try:
            media = pick_itunes_result(artist, title, response.json())
        except ValueError:
            return NO_MEDIA
        self._cache.put(key, media)
        return media

    async def aclose(self) -> None:
        await self._client.aclose()

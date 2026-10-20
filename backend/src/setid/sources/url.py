"""Validación estricta de URLs de entrada.

Solo se aceptan hosts de una lista blanca exacta. La URL que se pasa a ``yt-dlp`` nunca es
la que escribió el usuario: se reconstruye a partir del ID extraído, así que cualquier resto
(query, fragmento, credenciales...) se descarta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from setid.models import SourceType

YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
YOUTU_BE_HOST = "youtu.be"
SOUNDCLOUD_HOST = "soundcloud.com"
SOUNDCLOUD_SHORT_HOST = "on.soundcloud.com"

MAX_URL_LENGTH = 2048

_YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_SC_SLUG = re.compile(r"[A-Za-z0-9_-]{1,255}")
_SC_SECRET = re.compile(r"s-[A-Za-z0-9]{1,64}")
_SC_SHORT_CODE = re.compile(r"[A-Za-z0-9]{1,64}")

# Rutas de SoundCloud que son listas de tracks o páginas del usuario, no un track.
_SC_NON_TRACK = frozenset(
    {
        "sets", "likes", "tracks", "reposts", "albums", "popular-tracks", "followers",
        "following", "comments", "spotlight", "toptracks", "playlists",
    }
)  # fmt: skip
_SC_RESERVED_USERS = frozenset(
    {
        "discover", "search", "stream", "you", "upload", "charts", "stations", "settings",
        "messages", "notifications", "pages", "terms-of-use", "pro", "mobile", "people",
    }
)  # fmt: skip


class InvalidUrlError(ValueError):
    """La URL no es aceptable. El mensaje es apto para mostrarse al usuario."""


@dataclass(frozen=True)
class CanonicalSource:
    type: SourceType
    id: str
    url: str

    @property
    def canonical_id(self) -> str:
        prefix = {SourceType.YOUTUBE: "yt", SourceType.SOUNDCLOUD: "sc"}[self.type]
        return f"{prefix}:{self.id}"


@dataclass(frozen=True)
class ShortLink:
    """Enlace corto (on.soundcloud.com) que hay que resolver antes de usarlo."""

    url: str


def parse_source_url(raw: str) -> CanonicalSource | ShortLink:
    """Valida ``raw`` contra la lista blanca y lo normaliza. No hace ninguna petición de red."""
    text = raw.strip()
    if not text:
        raise InvalidUrlError("La URL está vacía.")
    if len(text) > MAX_URL_LENGTH:
        raise InvalidUrlError("La URL es demasiado larga.")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text) or "\\" in text:
        raise InvalidUrlError("La URL contiene caracteres no válidos.")

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise InvalidUrlError("La URL no está bien formada.") from exc

    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidUrlError("Solo se aceptan enlaces http(s).")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise InvalidUrlError("La URL no puede contener credenciales.")
    if port is not None:
        raise InvalidUrlError("La URL no puede indicar un puerto.")

    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    query = parse_qs(parts.query, keep_blank_values=True)

    if host in YOUTUBE_HOSTS:
        return _parse_youtube(segments, query)
    if host == YOUTU_BE_HOST:
        return _parse_youtu_be(segments, query)
    if host == SOUNDCLOUD_HOST:
        return _parse_soundcloud(segments, query)
    if host == SOUNDCLOUD_SHORT_HOST:
        if len(segments) != 1 or not _SC_SHORT_CODE.fullmatch(segments[0]):
            raise InvalidUrlError("Enlace corto de SoundCloud no válido.")
        return ShortLink(f"https://{SOUNDCLOUD_SHORT_HOST}/{segments[0]}")
    raise InvalidUrlError("Solo se aceptan enlaces de YouTube o SoundCloud.")


def _youtube(video_id: str) -> CanonicalSource:
    return CanonicalSource(
        SourceType.YOUTUBE, video_id, f"https://www.youtube.com/watch?v={video_id}"
    )


def _parse_youtube(segments: list[str], query: dict[str, list[str]]) -> CanonicalSource:
    if segments == ["watch"]:
        ids = query.get("v", [])
        if len(ids) != 1 or not _YT_ID.fullmatch(ids[0]):
            raise InvalidUrlError("No se encuentra un ID de vídeo de YouTube válido.")
        # Un vídeo abierto dentro de una lista sigue siendo un vídeo: la URL canónica
        # descarta ``list`` y yt-dlp se invoca además con --no-playlist.
        return _youtube(ids[0])
    if len(segments) == 2 and segments[0] in {"live", "shorts"}:
        if not _YT_ID.fullmatch(segments[1]):
            raise InvalidUrlError("No se encuentra un ID de vídeo de YouTube válido.")
        return _youtube(segments[1])
    if segments and segments[0] == "playlist":
        raise InvalidUrlError("Las playlists no están soportadas; pega el enlace de un vídeo.")
    raise InvalidUrlError("El enlace de YouTube no apunta a un vídeo.")


def _parse_youtu_be(segments: list[str], query: dict[str, list[str]]) -> CanonicalSource:
    if len(segments) != 1 or not _YT_ID.fullmatch(segments[0]):
        raise InvalidUrlError("No se encuentra un ID de vídeo de YouTube válido.")
    return _youtube(segments[0])


def _parse_soundcloud(segments: list[str], query: dict[str, list[str]]) -> CanonicalSource:
    if len(segments) not in {2, 3}:
        raise InvalidUrlError("El enlace de SoundCloud no apunta a un track.")
    user, track = segments[0].lower(), segments[1].lower()
    if track in _SC_NON_TRACK:
        raise InvalidUrlError("Las playlists y listas de SoundCloud no están soportadas.")
    if user in _SC_RESERVED_USERS:
        raise InvalidUrlError("El enlace de SoundCloud no apunta a un track.")
    if not (_SC_SLUG.fullmatch(user) and _SC_SLUG.fullmatch(track)):
        raise InvalidUrlError("El enlace de SoundCloud no es válido.")
    path = f"{user}/{track}"
    if len(segments) == 3:
        # Track privado: /usuario/track/s-TOKEN
        if not _SC_SECRET.fullmatch(segments[2]):
            raise InvalidUrlError("El enlace de SoundCloud no apunta a un track.")
        path = f"{path}/{segments[2]}"
    return CanonicalSource(SourceType.SOUNDCLOUD, path, f"https://{SOUNDCLOUD_HOST}/{path}")


class RedirectResolver(Protocol):
    def __call__(self, url: str) -> str | None:
        """Devuelve la cabecera ``Location`` de ``url`` sin seguir la redirección."""
        ...


def resolve_source(raw: str, resolver: RedirectResolver) -> CanonicalSource:
    """Como :func:`parse_source_url`, pero resuelve enlaces cortos (un único salto).

    El destino de la redirección pasa por la misma lista blanca, y no se permite que sea
    otro enlace corto.
    """
    parsed = parse_source_url(raw)
    if isinstance(parsed, CanonicalSource):
        return parsed
    location = resolver(parsed.url)
    if not location:
        raise InvalidUrlError("No se pudo resolver el enlace corto de SoundCloud.")
    target = parse_source_url(location)
    if not isinstance(target, CanonicalSource) or target.type is not SourceType.SOUNDCLOUD:
        raise InvalidUrlError("El enlace corto no redirige a un track de SoundCloud.")
    return target

"""Shazam mediante ``shazamio`` (API NO oficial, obtenida por ingeniería inversa).

Gratis, pero puede dejar de funcionar sin aviso y su uso está en zona gris respecto a los
términos de Shazam. Desactivado por defecto; se instala con el extra ``shazam``.

La huella se calcula en local (``shazamio_core``, en Rust) y solo se envía la firma. Las
peticiones HTTP las hace un cliente propio con httpx para controlar timeouts y reintentos,
en lugar de los 20 reintentos que shazamio hace por defecto.
"""

from __future__ import annotations

import warnings
from typing import Any

import httpx

from setid.models import Match
from setid.providers.base import (
    PermanentProviderError,
    SegmentProviderError,
    post_or_retryable,
)


def parse_response(payload: Any, confidence: float, provider: str = "shazam") -> Match | None:
    if not isinstance(payload, dict):
        raise SegmentProviderError(f"{provider}: respuesta inesperada")
    track = payload.get("track")
    if not payload.get("matches") or not isinstance(track, dict):
        return None
    title, artist = track.get("title"), track.get("subtitle")
    if not title or not artist:
        return None
    label = album = None
    for section in track.get("sections") or []:
        for item in section.get("metadata") or []:
            if item.get("title") == "Label":
                label = item.get("text") or None
            elif item.get("title") == "Album":
                album = item.get("text") or None
    return Match(
        artist=artist,
        title=title,
        label=label,
        isrc=track.get("isrc") or None,
        album=album,
        confidence=confidence,
        provider=provider,
    )


class _HttpxClient:
    """Implementa la interfaz HTTP de shazamio con httpx."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        if method.upper() != "POST":
            raise SegmentProviderError("shazam: método no soportado")
        response = await post_or_retryable(
            self._client, "shazam", url, headers=kwargs.get("headers"), json=kwargs.get("json")
        )
        try:
            return response.json()
        except ValueError as exc:
            raise SegmentProviderError("shazam: respuesta no es JSON") from exc


class ShazamProvider:
    name = "shazam"
    cost_per_query = 0.0

    def __init__(
        self,
        *,
        confidence: float = 0.8,
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        try:
            with warnings.catch_warnings():
                # pydub (dependencia de shazamio) tiene regex sin escapar que avisan al compilar.
                warnings.filterwarnings("ignore", category=SyntaxWarning)
                from shazamio import Shazam
        except ImportError as exc:
            raise PermanentProviderError(
                "shazam: falta la dependencia opcional; instala con `uv sync --extra shazam`"
            ) from exc
        self._confidence = confidence
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._shazam = Shazam(http_client=_HttpxClient(self._client))

    async def identify(self, segment: bytes) -> Match | None:
        from shazamio_core.shazamio_core import SignatureError

        try:
            signature = await self._shazam.core_recognizer.recognize_bytes(value=segment)
        except SignatureError as exc:
            raise SegmentProviderError("shazam: no se pudo generar la huella") from exc
        # Los errores HTTP ya llegan convertidos por _HttpxClient.
        payload = await self._shazam.send_recognize_request_v2(sig=signature)
        return parse_response(payload, self._confidence, self.name)

    async def aclose(self) -> None:
        await self._client.aclose()

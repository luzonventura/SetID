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

from setid.artwork import safe_artwork_url, safe_preview_url
from setid.models import Match
from setid.providers.base import (
    PermanentProviderError,
    SegmentProviderError,
    post_or_retryable,
)


def _preview(track: dict[str, Any]) -> str | None:
    """La preescucha de Apple que Shazam incluye entre las acciones del track."""
    for action in (track.get("hub") or {}).get("actions") or []:
        if (
            isinstance(action, dict)
            and action.get("type") == "uri"
            and (url := safe_preview_url(action.get("uri")))
        ):
            return url
    return None


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
        cover_url=safe_artwork_url(
            (track.get("images") or {}).get("coverarthq")
            or (track.get("images") or {}).get("coverart")
        ),
        preview_url=_preview(track),
    )


def _httpx_client(client: httpx.AsyncClient) -> Any:
    """Cliente HTTP para shazamio hecho con httpx.

    La clase se define aquí dentro porque hereda de la interfaz de shazamio, que es una
    dependencia opcional y solo se importa cuando se elige este proveedor.
    """
    from shazamio.interfaces.client import HTTPClientInterface

    class HttpxClient(HTTPClientInterface):
        async def request(self, method: str, url: str, **kwargs: Any) -> Any:
            if method.upper() != "POST":
                raise SegmentProviderError("shazam: método no soportado")
            response = await post_or_retryable(
                client, "shazam", url, headers=kwargs.get("headers"), json=kwargs.get("json")
            )
            try:
                return response.json()
            except ValueError as exc:
                raise SegmentProviderError("shazam: respuesta no es JSON") from exc

        async def request_text(self, url: str, *, content_type: str, **kwargs: Any) -> str:
            # Solo se usa el reconocimiento; el resto de la API de shazamio no se expone.
            raise SegmentProviderError("shazam: operación no soportada")

    return HttpxClient()


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
        self._shazam = Shazam(http_client=_httpx_client(self._client))

    async def identify(self, segment: bytes) -> Match | None:
        from shazamio_core.shazamio_core import SignatureError

        try:
            signature = await self._shazam.core_recognizer.recognize_bytes(value=segment)
        except SignatureError as exc:
            raise SegmentProviderError("shazam: no se pudo generar la huella") from exc
        # Los errores HTTP ya llegan convertidos por el cliente de _httpx_client.
        payload = await self._shazam.send_recognize_request_v2(sig=signature)
        return parse_response(payload, self._confidence, self.name)

    async def aclose(self) -> None:
        await self._client.aclose()

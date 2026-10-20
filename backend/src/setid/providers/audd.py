"""AudD (https://audd.io). Su API estándar no devuelve puntuación, así que la confianza es
un valor fijo configurable."""

from __future__ import annotations

from typing import Any

import httpx

from setid.models import Match
from setid.providers.base import (
    PermanentProviderError,
    QuotaExceededError,
    SegmentProviderError,
    post_or_retryable,
)

_URL = "https://api.audd.io/"
_BAD_TOKEN = {900}
_QUOTA = {901, 902}
_NO_RESULT = {300}  # no se pudo generar la huella


def parse_response(payload: Any, confidence: float, provider: str = "audd") -> Match | None:
    if not isinstance(payload, dict):
        raise SegmentProviderError(f"{provider}: respuesta inesperada")
    if payload.get("status") == "error":
        code = (payload.get("error") or {}).get("error_code")
        if code in _BAD_TOKEN:
            raise PermanentProviderError(f"{provider}: token no válido")
        if code in _QUOTA:
            raise QuotaExceededError(f"{provider}: se ha agotado el límite de consultas")
        if code in _NO_RESULT:
            return None
        raise SegmentProviderError(f"{provider}: error {code}")

    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("artist") or not result.get("title"):
        return None
    isrc = (result.get("apple_music") or {}).get("isrc") or (
        (result.get("spotify") or {}).get("external_ids") or {}
    ).get("isrc")
    return Match(
        artist=result["artist"],
        title=result["title"],
        label=result.get("label") or None,
        isrc=isrc or None,
        album=result.get("album") or None,
        confidence=confidence,
        provider=provider,
    )


class AudDProvider:
    name = "audd"

    def __init__(
        self,
        *,
        api_token: str | None,
        confidence: float = 0.8,
        timeout_s: float = 30.0,
        cost_per_query: float = 0.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = api_token
        self._confidence = confidence
        self.cost_per_query = cost_per_query
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def identify(self, segment: bytes) -> Match | None:
        data = {"return": "apple_music,spotify"}
        if self._token:
            data["api_token"] = self._token
        files = {"file": ("segment.wav", segment, "audio/wav")}
        response = await post_or_retryable(self._client, self.name, _URL, data=data, files=files)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SegmentProviderError("audd: respuesta no es JSON") from exc
        return parse_response(payload, self._confidence, self.name)

    async def aclose(self) -> None:
        await self._client.aclose()

"""ACRCloud Identification API (``POST /v1/identify`` con firma HMAC-SHA1)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from setid.models import Match
from setid.providers.base import (
    PermanentProviderError,
    QuotaExceededError,
    RetryableProviderError,
    SegmentProviderError,
    clamp_confidence,
    post_or_retryable,
)

_ENDPOINT = "/v1/identify"
_HOST = re.compile(r"identify-[a-z0-9-]+\.acrcloud\.(com|cn)")

_NO_RESULT = {1001, 2004}  # sin coincidencia / no se pudo generar la huella
_RETRYABLE = {3015}  # QPS superado
_QUOTA = {3003}  # límite de la cuenta
_PERMANENT = {3000, 3001, 3002, 3014}  # credenciales o firma


def sign(access_key: str, access_secret: str, timestamp: str) -> str:
    string_to_sign = "\n".join(["POST", _ENDPOINT, access_key, "audio", "1", timestamp])
    digest = hmac.new(access_secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def parse_response(payload: Any, provider: str = "acrcloud") -> Match | None:
    if not isinstance(payload, dict):
        raise SegmentProviderError(f"{provider}: respuesta inesperada")
    status = payload.get("status") or {}
    code = status.get("code")
    if code in _NO_RESULT:
        return None
    if code in _RETRYABLE:
        raise RetryableProviderError(f"{provider}: límite de consultas por segundo")
    if code in _QUOTA:
        raise QuotaExceededError(f"{provider}: se ha agotado la cuota de la cuenta")
    if code in _PERMANENT:
        raise PermanentProviderError(f"{provider}: credenciales o configuración incorrectas")
    if code != 0:
        raise SegmentProviderError(f"{provider}: error {code}")

    music = (payload.get("metadata") or {}).get("music") or []
    if not music:
        return None
    best = max(music, key=lambda m: m.get("score") or 0)
    artists = [a.get("name") for a in best.get("artists") or [] if a.get("name")]
    title = best.get("title")
    if not artists or not title:
        return None
    return Match(
        artist=", ".join(artists),
        title=title,
        label=best.get("label") or None,
        isrc=(best.get("external_ids") or {}).get("isrc") or None,
        album=(best.get("album") or {}).get("name") or None,
        confidence=clamp_confidence(float(best.get("score") or 0) / 100),
        provider=provider,
    )


class ACRCloudProvider:
    name = "acrcloud"

    def __init__(
        self,
        *,
        host: str,
        access_key: str,
        access_secret: str,
        timeout_s: float = 30.0,
        cost_per_query: float = 0.0,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not _HOST.fullmatch(host):
            raise PermanentProviderError("acrcloud: host no válido")
        if not access_key or not access_secret:
            raise PermanentProviderError("acrcloud: faltan las credenciales")
        self._url = f"https://{host}{_ENDPOINT}"
        self._key = access_key
        self._secret = access_secret
        self._clock = clock
        self.cost_per_query = cost_per_query
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def identify(self, segment: bytes) -> Match | None:
        timestamp = str(int(self._clock()))
        data = {
            "access_key": self._key,
            "sample_bytes": str(len(segment)),
            "timestamp": timestamp,
            "signature": sign(self._key, self._secret, timestamp),
            "data_type": "audio",
            "signature_version": "1",
        }
        files = {"sample": ("segment.wav", segment, "audio/wav")}
        response = await post_or_retryable(
            self._client, self.name, self._url, data=data, files=files
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SegmentProviderError("acrcloud: respuesta no es JSON") from exc
        return parse_response(payload, self.name)

    async def aclose(self) -> None:
        await self._client.aclose()

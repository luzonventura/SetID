"""Interfaz común de los proveedores de reconocimiento y su jerarquía de errores.

* :class:`RetryableProviderError`: 429, 5xx, timeouts. Se reintenta con backoff.
* :class:`SegmentProviderError`: el proveedor no pudo con este segmento. Se anota y se sigue.
* :class:`PermanentProviderError`: credenciales o configuración incorrectas, o cuota
  agotada. Se aborta el trabajo, porque todas las consultas siguientes fallarían igual.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from setid.models import Match


class ProviderError(Exception):
    pass


class RetryableProviderError(ProviderError):
    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class SegmentProviderError(ProviderError):
    pass


class PermanentProviderError(ProviderError):
    pass


class QuotaExceededError(PermanentProviderError):
    pass


class RecognitionProvider(Protocol):
    name: str
    cost_per_query: float

    async def identify(self, segment: bytes) -> Match | None:
        """Identifica un segmento WAV. ``None`` significa que no hay coincidencia."""
        ...

    async def aclose(self) -> None: ...


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def check_http_status(response: httpx.Response, provider: str) -> None:
    status = response.status_code
    if status == 429:
        raise RetryableProviderError(
            f"{provider}: límite de peticiones (429)", retry_after_s=_retry_after(response)
        )
    if status >= 500:
        raise RetryableProviderError(f"{provider}: error del servidor ({status})")
    if status in {401, 403}:
        raise PermanentProviderError(f"{provider}: credenciales rechazadas ({status})")
    if status >= 400:
        raise SegmentProviderError(f"{provider}: petición rechazada ({status})")


async def post_or_retryable(
    client: httpx.AsyncClient, provider: str, url: str, **kwargs: object
) -> httpx.Response:
    """POST que convierte los fallos de red en errores reintentables."""
    try:
        response = await client.post(url, **kwargs)  # type: ignore[arg-type]
    except httpx.TimeoutException as exc:
        raise RetryableProviderError(f"{provider}: tiempo de espera agotado") from exc
    except httpx.TransportError as exc:
        raise RetryableProviderError(f"{provider}: error de red") from exc
    check_http_status(response, provider)
    return response


def clamp_confidence(value: float) -> float:
    return min(1.0, max(0.0, value))

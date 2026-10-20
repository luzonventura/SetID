"""Envío de segmentos al proveedor con concurrencia limitada, reintentos y presupuesto.

Los segmentos se consumen del iterador solo cuando hay hueco en el semáforo, así que en
memoria nunca hay más de ``concurrency`` segmentos a la vez.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from setid.audio.segment import Segment
from setid.models import SegmentResult
from setid.providers.base import (
    PermanentProviderError,
    RecognitionProvider,
    RetryableProviderError,
    SegmentProviderError,
)

log = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """No quedan consultas en el presupuesto. Mensaje apto para el usuario."""


class QueryBudget(Protocol):
    def remaining(self) -> int | None:
        """Consultas restantes, o ``None`` si no hay límite."""
        ...

    def try_consume(self) -> bool: ...

    def refund(self) -> None:
        """Devuelve una consulta que el proveedor rechazó sin procesarla (429/5xx)."""
        ...


class FixedBudget:
    """Presupuesto en memoria (CLI). La app usa uno diario persistente en base de datos."""

    def __init__(self, limit: int | None) -> None:
        self._remaining = limit

    def remaining(self) -> int | None:
        return self._remaining

    def try_consume(self) -> bool:
        if self._remaining is None:
            return True
        if self._remaining <= 0:
            return False
        self._remaining -= 1
        return True

    def refund(self) -> None:
        if self._remaining is not None:
            self._remaining += 1


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_s: float = 1.0
    max_s: float = 60.0
    jitter: float = 0.25

    def delay(self, attempt: int, retry_after_s: float | None, rng: random.Random) -> float:
        if retry_after_s is not None:
            return min(self.max_s, retry_after_s)
        backoff = min(self.max_s, self.base_s * 2.0 ** (attempt - 1))
        return backoff * (1 + self.jitter * rng.random())


@dataclass
class RecognitionStats:
    queries: int = 0
    retries: int = 0
    errors: int = 0
    cost: float = 0.0


class _Pacer:
    """Ritmo compartido por todas las consultas.

    Mantiene una separación mínima entre consultas y, cuando el proveedor limita (429/5xx),
    pausa a *todos* los workers, no solo al que recibió el error. Si no, los demás siguen
    martilleando la API y agravan el bloqueo.
    """

    def __init__(
        self,
        interval_s: float,
        sleep: Callable[[float], Awaitable[None]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval_s
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            if now < self._next:
                await self._sleep(self._next - now)
                now = max(now, self._next)
            self._next = now + self._interval

    def pause(self, seconds: float) -> None:
        self._next = max(self._next, self._clock() + seconds)


async def recognize_segments(
    segments: Iterable[Segment],
    provider: RecognitionProvider,
    *,
    concurrency: int = 3,
    retry: RetryPolicy | None = None,
    min_interval_s: float = 0.0,
    budget: QueryBudget | None = None,
    on_result: Callable[[SegmentResult], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] | None = None,
    rng: random.Random | None = None,
) -> tuple[list[SegmentResult], RecognitionStats]:
    policy = retry or RetryPolicy()
    budget = budget or FixedBudget(None)
    rng = rng or random.Random()  # noqa: S311 - solo para el jitter del backoff
    pacer = _Pacer(min_interval_s, sleep, clock or time.monotonic)
    stats = RecognitionStats()
    results: list[SegmentResult] = []
    slots = asyncio.Semaphore(concurrency)

    def charge() -> None:
        stats.queries += 1
        stats.cost += provider.cost_per_query

    async def identify(seg: Segment) -> SegmentResult:
        for attempt in range(1, policy.max_attempts + 1):
            if not budget.try_consume():
                raise BudgetExhaustedError("Se ha agotado el presupuesto de consultas.")
            await pacer.wait()
            try:
                match = await provider.identify(seg.wav)
                charge()
                return SegmentResult(index=seg.index, start_s=seg.start_s, match=match)
            except PermanentProviderError:
                budget.refund()
                raise
            except RetryableProviderError as exc:
                # Un 429/5xx no se factura: ni cuenta como consulta ni gasta presupuesto.
                budget.refund()
                if attempt == policy.max_attempts:
                    return _failed(seg, str(exc))
                stats.retries += 1
                pacer.pause(policy.delay(attempt, exc.retry_after_s, rng))
                continue
            except SegmentProviderError as exc:
                charge()
                return _failed(seg, str(exc))
            except Exception as exc:  # noqa: BLE001 - un fallo raro no debe tirar un set entero
                charge()
                log.warning("error inesperado del proveedor: %s", type(exc).__name__)
                return _failed(seg, f"{provider.name}: error inesperado")
        raise AssertionError("inalcanzable")

    def _failed(seg: Segment, error: str) -> SegmentResult:
        stats.errors += 1
        return SegmentResult(index=seg.index, start_s=seg.start_s, error=error)

    async def worker(seg: Segment) -> None:
        try:
            result = await identify(seg)
            results.append(result)
            if on_result:
                on_result(result)
        finally:
            slots.release()

    iterator = iter(segments)
    try:
        async with asyncio.TaskGroup() as group:
            while True:
                # Primero el hueco y después el segmento: nunca se lee uno de más.
                await slots.acquire()
                seg = next(iterator, None)
                if seg is None:
                    slots.release()
                    break
                group.create_task(worker(seg))
    except ExceptionGroup as eg:
        # Un error permanente o de presupuesto cancela el resto; se propaga el primero.
        raise eg.exceptions[0] from None

    results.sort(key=lambda r: r.index)
    return results, stats

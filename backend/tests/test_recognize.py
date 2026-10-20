from __future__ import annotations

import asyncio
import itertools
import random
from collections.abc import Iterator

import pytest

from setid.audio.segment import Segment
from setid.models import Match
from setid.providers.base import (
    PermanentProviderError,
    RetryableProviderError,
    SegmentProviderError,
)
from setid.recognize import (
    BudgetExhaustedError,
    FixedBudget,
    RetryPolicy,
    recognize_segments,
)


def make_segments(n: int, pulled: list[int] | None = None) -> Iterator[Segment]:
    for i in range(n):
        if pulled is not None:
            pulled.append(i)
        yield Segment(index=i, start_s=i * 30.0, duration_s=12.0, wav=str(i).encode())


def match_for(segment: bytes) -> Match:
    return Match(artist="A", title=segment.decode(), confidence=0.9, provider="script")


class ScriptedProvider:
    """Proveedor de test: ``script[index]`` es una lista de respuestas por intento."""

    name = "script"
    cost_per_query = 0.01

    def __init__(self, script: dict[int, list[object]] | None = None, delay: float = 0) -> None:
        self.script = script or {}
        self.delay = delay
        self.calls: list[int] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def identify(self, segment: bytes) -> Match | None:
        index = int(segment.decode())
        self.calls.append(index)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            steps = self.script.get(index)
            outcome = steps.pop(0) if steps else "match"
            if isinstance(outcome, Exception):
                raise outcome
            return None if outcome is None else match_for(segment)
        finally:
            self.in_flight -= 1

    async def aclose(self) -> None:
        return None


async def no_sleep(_: float) -> None:
    await asyncio.sleep(0)


async def test_results_are_complete_and_ordered() -> None:
    provider = ScriptedProvider({3: [None]}, delay=0.001)
    results, stats = await recognize_segments(make_segments(6), provider, concurrency=3)
    assert [r.index for r in results] == list(range(6))
    assert results[3].match is None and results[3].error is None
    assert results[0].match is not None
    assert stats.queries == 6
    assert stats.cost == pytest.approx(0.06)


async def test_concurrency_is_bounded_and_segments_are_pulled_lazily() -> None:
    pulled: list[int] = []
    provider = ScriptedProvider(delay=0.01)
    seen_ahead: list[int] = []

    def on_result(_: object) -> None:
        # Nunca se han sacado del iterador más de `concurrency` segmentos sin terminar.
        seen_ahead.append(len(pulled) - len(seen_ahead))

    await recognize_segments(
        make_segments(20, pulled), provider, concurrency=3, on_result=on_result
    )
    assert provider.max_in_flight <= 3
    assert max(seen_ahead) <= 3


class FakeClock:
    """Reloj virtual: ``sleep`` avanza el tiempo en lugar de esperar."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds
        await asyncio.sleep(0)


async def test_retryable_errors_are_retried_with_backoff() -> None:
    clock = FakeClock()
    provider = ScriptedProvider(
        {0: [RetryableProviderError("429"), RetryableProviderError("503"), "match"]}
    )
    results, stats = await recognize_segments(
        make_segments(1),
        provider,
        retry=RetryPolicy(max_attempts=5, base_s=1, jitter=0),
        sleep=clock.sleep,
        clock=clock,
    )
    assert results[0].match is not None
    assert clock.sleeps == [1, 2]
    assert stats.retries == 2
    assert stats.queries == 1  # los 429/5xx no se facturan


async def test_retry_after_header_is_respected() -> None:
    clock = FakeClock()
    provider = ScriptedProvider({0: [RetryableProviderError("429", retry_after_s=7), "match"]})
    await recognize_segments(make_segments(1), provider, sleep=clock.sleep, clock=clock)
    assert clock.sleeps == [7]


async def test_throttling_pauses_all_workers() -> None:
    clock = FakeClock()
    starts: list[tuple[int, float]] = []

    class Recording(ScriptedProvider):
        async def identify(self, segment: bytes) -> Match | None:
            starts.append((int(segment.decode()), clock.now))
            return await super().identify(segment)

    provider = Recording({0: [RetryableProviderError("429", retry_after_s=10), "match"]})
    await recognize_segments(
        make_segments(4), provider, concurrency=3, sleep=clock.sleep, clock=clock
    )
    # Tras el 429 del segmento 0, ninguna consulta nueva sale antes de t=10.
    first_429 = starts.index((0, 0.0))
    assert all(t >= 10 for _, t in starts[first_429 + 3 :])


async def test_backoff_is_capped() -> None:
    policy = RetryPolicy(base_s=1, max_s=10, jitter=0)
    rng = random.Random(0)
    assert [policy.delay(a, None, rng) for a in range(1, 7)] == [1, 2, 4, 8, 10, 10]


async def test_gives_up_after_max_attempts_and_records_error() -> None:
    provider = ScriptedProvider({1: [RetryableProviderError("503")] * 3})
    results, stats = await recognize_segments(
        make_segments(3), provider, retry=RetryPolicy(max_attempts=3), sleep=no_sleep
    )
    assert results[1].match is None
    assert results[1].error == "503"
    assert results[0].match is not None and results[2].match is not None
    assert stats.errors == 1


async def test_segment_errors_are_not_retried() -> None:
    provider = ScriptedProvider({0: [SegmentProviderError("bad audio")]})
    results, _stats = await recognize_segments(make_segments(1), provider, sleep=no_sleep)
    assert results[0].error == "bad audio"
    assert provider.calls == [0]


async def test_unexpected_exceptions_do_not_abort_the_set() -> None:
    provider = ScriptedProvider({0: [KeyError("x")]})
    results, _ = await recognize_segments(make_segments(2), provider)
    assert results[0].error is not None
    assert results[1].match is not None


async def test_permanent_error_aborts_everything() -> None:
    provider = ScriptedProvider({2: [PermanentProviderError("bad key")]}, delay=0.001)
    with pytest.raises(PermanentProviderError, match="bad key"):
        await recognize_segments(make_segments(50), provider, concurrency=2)
    assert len(provider.calls) < 50


async def test_budget_is_enforced_per_query() -> None:
    provider = ScriptedProvider()
    with pytest.raises(BudgetExhaustedError):
        await recognize_segments(make_segments(5), provider, budget=FixedBudget(3))
    assert len(provider.calls) == 3


async def test_throttled_attempts_do_not_consume_budget() -> None:
    budget = FixedBudget(10)
    clock = FakeClock()
    provider = ScriptedProvider({0: [RetryableProviderError("429"), "match"]})
    await recognize_segments(
        make_segments(2), provider, budget=budget, sleep=clock.sleep, clock=clock
    )
    assert budget.remaining() == 8


async def test_segment_errors_do_consume_budget() -> None:
    budget = FixedBudget(10)
    provider = ScriptedProvider({0: [SegmentProviderError("bad")]})
    _, stats = await recognize_segments(make_segments(1), provider, budget=budget)
    assert budget.remaining() == 9
    assert stats.queries == 1


async def test_min_interval_spaces_out_queries() -> None:
    clock = FakeClock()
    starts: list[float] = []

    class Timed(ScriptedProvider):
        async def identify(self, segment: bytes) -> Match | None:
            starts.append(clock.now)
            return await super().identify(segment)

    await recognize_segments(
        make_segments(4),
        Timed(),
        concurrency=4,
        min_interval_s=1.5,
        sleep=clock.sleep,
        clock=clock,
    )
    assert [b - a for a, b in itertools.pairwise(starts)] == [1.5, 1.5, 1.5]

"""Presupuesto diario de consultas, persistido en SQLite por día (hora local) y proveedor."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import Engine, text
from sqlmodel import Session

from setid.db.tables import QueryUsage


def today_local() -> str:
    return date.today().isoformat()


class DailyBudget:
    def __init__(
        self,
        engine: Engine,
        *,
        provider: str,
        limit: int | None,
        cost_per_query: float = 0.0,
        today: Callable[[], str] = today_local,
    ) -> None:
        self._engine = engine
        self._provider = provider
        self._limit = limit
        self._cost = cost_per_query
        self._today = today

    def used(self) -> int:
        with Session(self._engine) as session:
            row = session.get(QueryUsage, (self._today(), self._provider))
            return row.queries if row else 0

    def remaining(self) -> int | None:
        if self._limit is None:
            return None
        return max(0, self._limit - self.used())

    def try_consume(self) -> bool:
        day = self._today()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO query_usage (day, provider, queries, estimated_cost) "
                    "VALUES (:day, :provider, 0, 0)"
                ),
                {"day": day, "provider": self._provider},
            )
            # Comprobar y sumar en una sola sentencia: atómico aunque haya varios hilos.
            result = conn.execute(
                text(
                    "UPDATE query_usage SET queries = queries + 1, "
                    "estimated_cost = estimated_cost + :cost "
                    "WHERE day = :day AND provider = :provider "
                    "AND (:limit IS NULL OR queries < :limit)"
                ),
                {"day": day, "provider": self._provider, "limit": self._limit, "cost": self._cost},
            )
            return result.rowcount == 1

    def refund(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE query_usage SET queries = MAX(0, queries - 1), "
                    "estimated_cost = MAX(0, estimated_cost - :cost) "
                    "WHERE day = :day AND provider = :provider"
                ),
                {"day": self._today(), "provider": self._provider, "cost": self._cost},
            )

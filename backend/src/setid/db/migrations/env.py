"""Entorno de Alembic. Usa el motor que le pasa :func:`setid.db.engine.migrate`."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel

import setid.db.tables  # noqa: F401 - registra las tablas en los metadatos

config = context.config
target_metadata = SQLModel.metadata


def run_migrations() -> None:
    engine = config.attributes.get("engine")
    if not isinstance(engine, Engine):
        engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite no soporta la mayoría de ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


run_migrations()

"""Motor SQLite con WAL y migraciones con Alembic al arrancar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlmodel import create_engine

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def _on_connect(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def database_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def make_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url(path),
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _on_connect)
    return engine


def alembic_config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # env.py usa este motor directamente (con los PRAGMA ya configurados).
    config.attributes["engine"] = engine
    return config


def migrate(engine: Engine) -> None:
    command.upgrade(alembic_config(engine), "head")


def open_database(path: Path) -> Engine:
    engine = make_engine(path)
    migrate(engine)
    return engine

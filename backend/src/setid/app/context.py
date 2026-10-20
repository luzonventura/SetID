"""Montaje de la app: ajustes, base de datos, gestor de trabajos y API del puente."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from setid.app.bridge import Api
from setid.db.engine import open_database
from setid.jobs.manager import JobManager, ProviderFactory
from setid.logging_setup import setup_logging
from setid.providers.registry import build_provider
from setid.settings_store import SecretBackend, SettingsStore
from setid.sources.url import RedirectResolver

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    store: SettingsStore
    engine: Engine
    manager: JobManager
    api: Api
    log_path: Path | None

    def close(self) -> None:
        self.manager.stop()
        self.engine.dispose()


def create_app(
    data_dir: Path | None = None,
    *,
    secrets: SecretBackend | None = None,
    provider_factory: ProviderFactory = build_provider,
    resolver: RedirectResolver | None = None,
    log_to_file: bool = True,
) -> AppContext:
    store = SettingsStore(data_dir, secrets)
    log_path = setup_logging(store.data_dir / "logs") if log_to_file else None
    engine = open_database(store.data_dir / "setid.db")
    manager = JobManager(engine, store, provider_factory=provider_factory, resolver=resolver)
    manager.start()
    log.info("app iniciada")
    return AppContext(store, engine, manager, Api(manager, store), log_path)

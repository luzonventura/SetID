"""Tests de base de datos, presupuesto diario, ajustes, exportaciones y logs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from setid.db.budget import DailyBudget
from setid.db.engine import alembic_config, open_database
from setid.exports import ExportMeta, to_csv, to_m3u, to_text
from setid.logging_setup import JsonFormatter, redact
from setid.models import EntrySource, TracklistEntry
from setid.settings_store import MemorySecrets, SettingsStore


def test_database_uses_wal_and_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "setid.db"
    engine = open_database(path)
    engine.dispose()
    engine = open_database(path)  # segunda vez: no debe fallar
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == ScriptDirectory.from_config(alembic_config(engine)).get_current_head()
    engine.dispose()


def test_daily_budget(tmp_path: Path) -> None:
    engine = open_database(tmp_path / "setid.db")
    day = ["2026-10-18"]
    budget = DailyBudget(
        engine, provider="audd", limit=3, cost_per_query=0.01, today=lambda: day[0]
    )
    assert budget.remaining() == 3
    assert [budget.try_consume() for _ in range(4)] == [True, True, True, False]
    assert budget.remaining() == 0
    budget.refund()
    assert budget.remaining() == 1

    other = DailyBudget(engine, provider="acrcloud", limit=3, today=lambda: day[0])
    assert other.remaining() == 3  # cada proveedor lleva su cuenta

    day[0] = "2026-10-19"
    assert budget.remaining() == 3  # día nuevo, presupuesto nuevo

    unlimited = DailyBudget(engine, provider="shazam", limit=None)
    assert unlimited.remaining() is None
    assert unlimited.try_consume()
    assert unlimited.used() == 1
    engine.dispose()


def test_settings_store_roundtrip_and_env_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = MemorySecrets()
    store = SettingsStore(tmp_path, secrets)
    assert store.load().step_s == 30
    store.update({"step_s": 45, "min_confidence": 0.6})
    assert json.loads(store.path.read_text())["step_s"] == 45

    fresh = SettingsStore(tmp_path, secrets).load()
    assert (fresh.step_s, fresh.min_confidence) == (45, 0.6)

    store.set_secret("acrcloud_access_key", "from-keyring")
    monkeypatch.setenv("SETID_ACRCLOUD_ACCESS_KEY", "from-env")
    key = store.load().acrcloud_access_key
    assert key is not None and key.get_secret_value() == "from-env"
    monkeypatch.delenv("SETID_ACRCLOUD_ACCESS_KEY")
    key = store.load().acrcloud_access_key
    assert key is not None and key.get_secret_value() == "from-keyring"

    store.reset(["step_s"])
    assert store.load().step_s == 30


def test_secrets_never_written_to_settings_file(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, MemorySecrets())
    store.set_secret("audd_api_token", "tok-secreto")
    store.update({"step_s": 40})
    assert "tok-secreto" not in store.path.read_text()


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / "settings.json").write_text("{no es json")
    assert SettingsStore(tmp_path, MemorySecrets()).load().step_s == 30


def entry(
    position: int, artist: str, title: str, start: float, unknown: bool = False
) -> TracklistEntry:
    return TracklistEntry(
        position=position,
        start_s=start,
        end_s=start + 60,
        artist=artist,
        title=title,
        confidence=None if unknown else 0.9,
        source=EntrySource.UNKNOWN if unknown else EntrySource.FINGERPRINT,
    )


META = ExportMeta(title="Set", uploader=None, duration_s=4000, source=None, provider="fake")


def test_csv_neutralizes_formula_injection() -> None:
    rows = to_csv([entry(1, '=HYPERLINK("http://evil")', "+cmd|' /C calc'!A0", 0)])
    line = rows.splitlines()[1]
    assert "'=HYPERLINK" in line
    assert "'+cmd" in line


def test_text_export_aligns_hours() -> None:
    lines = to_text(META, [entry(1, "A", "T", 0), entry(2, "B", "U", 3700)]).splitlines()
    assert lines[2:] == ["0:00:00 A – T", "1:01:40 B – U"]


def test_m3u_strips_newlines_from_metadata() -> None:
    content = to_m3u(META, [entry(1, "A\n#EXTINF:evil", "T", 0)])
    assert "\n#EXTINF:evil" not in content


def test_redact_hides_secrets() -> None:
    assert redact("POST api_token=abc123&x=1") == "POST api_token=***&x=1"
    assert redact('{"access_key": "KEY"}') == '{"access_key": "***"}'
    assert redact("sin secretos") == "sin secretos"


def test_json_log_format() -> None:
    record = logging.makeLogRecord(
        {"name": "setid", "levelname": "INFO", "msg": "hola token=xyz", "job_id": 3}
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "hola token=***"
    assert payload["job_id"] == 3
    assert payload["level"] == "info"

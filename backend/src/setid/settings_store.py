"""Ajustes de la app de escritorio.

* Los valores normales se guardan en ``<data_dir>/settings.json``.
* Las claves de API van al almacén de credenciales del sistema (en Windows, el
  Administrador de credenciales) mediante ``keyring``. Nunca se escriben en disco en claro
  ni se devuelven a la interfaz: solo se informa de si están configuradas.

Prioridad: variables de entorno < ``settings.json`` para los ajustes normales (lo que
cambias en la app manda); para las claves manda la variable de entorno, útil en desarrollo.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from pydantic import SecretStr

from setid.config import Settings

KEYRING_SERVICE = "SetID"

EDITABLE_FIELDS = frozenset(
    {
        "provider",
        "window_s",
        "step_s",
        "concurrency",
        "min_interval_s",
        "daily_query_budget",
        "min_confidence",
        "max_gap_segments",
        "unknown_min_segments",
        "mark_unknown_edges",
        "community_enabled",
        "community_max_comments",
        "acrcloud_host",
        "audd_confidence",
        "shazam_confidence",
        "cost_per_query_acrcloud",
        "cost_per_query_audd",
    }
)
SECRET_FIELDS = frozenset({"acrcloud_access_key", "acrcloud_access_secret", "audd_api_token"})


class SecretBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class KeyringSecrets:
    """Almacén de credenciales del sistema operativo."""

    def get_password(self, service: str, username: str) -> str | None:
        import keyring

        return keyring.get_password(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        import keyring

        keyring.set_password(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        with contextlib.suppress(PasswordDeleteError):
            keyring.delete_password(service, username)


class MemorySecrets:
    """Almacén en memoria para tests."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class UnknownSettingError(ValueError):
    pass


class SettingsStore:
    def __init__(self, data_dir: Path | None = None, secrets: SecretBackend | None = None) -> None:
        self._overrides: dict[str, Any] = {"data_dir": data_dir} if data_dir else {}
        self._secrets = secrets or KeyringSecrets()
        self.data_dir = Settings(**self._overrides).data_dir

    @property
    def path(self) -> Path:
        return self.data_dir / "settings.json"

    def _stored(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # Un settings.json roto no debe impedir arrancar: se ignora y se usan defaults.
            return {}
        return (
            {k: v for k, v in raw.items() if k in EDITABLE_FIELDS} if isinstance(raw, dict) else {}
        )

    def _secret_values(self, base: Settings) -> dict[str, SecretStr]:
        values = {}
        for name in SECRET_FIELDS:
            if getattr(base, name) is None:
                stored = self._secrets.get_password(KEYRING_SERVICE, name)
                if stored:
                    values[name] = SecretStr(stored)
        return values

    def load(self) -> Settings:
        base = Settings(**self._overrides)
        return Settings(**{**self._overrides, **self._stored(), **self._secret_values(base)})

    def update(self, changes: dict[str, Any]) -> Settings:
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise UnknownSettingError(f"Ajustes desconocidos: {', '.join(sorted(unknown))}")
        merged = {**self._stored(), **changes}
        # Valida antes de escribir: si algo no es válido, salta ValidationError y no se toca.
        validated = Settings(**{**self._overrides, **merged})
        to_store = {k: validated.model_dump(mode="json")[k] for k in merged}
        self._write(to_store)
        return self.load()

    def reset(self, names: list[str]) -> Settings:
        stored = {k: v for k, v in self._stored().items() if k not in names}
        self._write(stored)
        return self.load()

    def _write(self, data: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix="settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            Path(tmp).replace(self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def set_secret(self, name: str, value: str | None) -> None:
        if name not in SECRET_FIELDS:
            raise UnknownSettingError(f"Credencial desconocida: {name}")
        if value:
            self._secrets.set_password(KEYRING_SERVICE, name, value.strip())
        else:
            self._secrets.delete_password(KEYRING_SERVICE, name)

    def public_view(self, settings: Settings | None = None) -> dict[str, Any]:
        """Lo que puede ver la interfaz: valores editables y si cada clave está puesta."""
        current = settings or self.load()
        dumped = current.model_dump(mode="json")
        return {
            "values": {k: dumped[k] for k in sorted(EDITABLE_FIELDS)},
            "secrets": {k: getattr(current, k) is not None for k in sorted(SECRET_FIELDS)},
            "effective_limits": {
                "concurrency": current.rate_limits().concurrency,
                "min_interval_s": current.rate_limits().min_interval_s,
            },
        }

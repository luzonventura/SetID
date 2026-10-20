"""Construcción del proveedor elegido en la configuración."""

from __future__ import annotations

from setid.config import ProviderName, Settings
from setid.providers.base import PermanentProviderError, RecognitionProvider


def _secret(value: object) -> str:
    from pydantic import SecretStr

    return value.get_secret_value() if isinstance(value, SecretStr) else ""


def build_provider(settings: Settings, name: ProviderName | None = None) -> RecognitionProvider:
    choice = name or settings.provider
    if choice is ProviderName.FAKE:
        from setid.providers.fake import FakeProvider

        return FakeProvider()
    if choice is ProviderName.ACRCLOUD:
        from setid.providers.acrcloud import ACRCloudProvider

        key, secret = (
            _secret(settings.acrcloud_access_key),
            _secret(settings.acrcloud_access_secret),
        )
        if not key or not secret:
            raise PermanentProviderError(
                "acrcloud: define SETID_ACRCLOUD_ACCESS_KEY y SETID_ACRCLOUD_ACCESS_SECRET"
            )
        return ACRCloudProvider(
            host=settings.acrcloud_host,
            access_key=key,
            access_secret=secret,
            timeout_s=settings.request_timeout_s,
            cost_per_query=settings.cost_per_query_acrcloud,
        )
    if choice is ProviderName.AUDD:
        from setid.providers.audd import AudDProvider

        return AudDProvider(
            api_token=_secret(settings.audd_api_token) or None,
            confidence=settings.audd_confidence,
            timeout_s=settings.request_timeout_s,
            cost_per_query=settings.cost_per_query_audd,
        )
    if choice is ProviderName.SHAZAM:
        from setid.providers.shazam import ShazamProvider

        return ShazamProvider(
            confidence=settings.shazam_confidence, timeout_s=settings.request_timeout_s
        )
    raise PermanentProviderError(f"proveedor desconocido: {choice}")

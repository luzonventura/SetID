from __future__ import annotations

import base64
import hashlib
import hmac
import math
import random
from array import array

import httpx
import pytest
import respx

from setid.artwork import LOOKUP_INTERVAL_S, ArtworkFinder, pick_itunes_result, safe_artwork_url
from setid.audio.demo import DEMO_CATALOG
from setid.providers import acrcloud, audd, shazam
from setid.providers.acrcloud import ACRCloudProvider
from setid.providers.audd import AudDProvider
from setid.providers.base import (
    PermanentProviderError,
    QuotaExceededError,
    RetryableProviderError,
    SegmentProviderError,
)
from setid.providers.fake import FakeProvider, analyze_tone
from tests.helpers import tone_frames, wav_bytes

# --- Fake ---------------------------------------------------------------------------------


async def test_fake_recognizes_catalog_tones() -> None:
    provider = FakeProvider()
    for track in DEMO_CATALOG:
        match = await provider.identify(wav_bytes(tone_frames(track.frequency_hz, 2, 0.5)))
        assert match is not None
        assert (match.artist, match.title) == (track.artist, track.title)
        assert match.confidence == pytest.approx(0.95, abs=0.01)


async def test_fake_tolerates_pitch_and_maps_volume_to_confidence() -> None:
    match = await FakeProvider().identify(wav_bytes(tone_frames(440 * 1.04, 2, 0.15)))
    assert match is not None
    assert match.title == "Groove Theory"
    assert match.confidence < 0.5


async def test_fake_returns_none_for_noise_and_silence() -> None:
    rng = random.Random(1)
    noise = bytes(rng.getrandbits(8) for _ in range(44_100 * 2))
    provider = FakeProvider()
    assert await provider.identify(wav_bytes(noise)) is None
    assert await provider.identify(wav_bytes(b"\x00\x00" * 44_100)) is None


def test_analyze_tone_estimates_frequency() -> None:
    freq, peak, irregularity = analyze_tone(wav_bytes(tone_frames(550, 1, 0.3)))
    assert freq == pytest.approx(550, rel=0.01)
    assert peak == pytest.approx(0.3, rel=0.01)
    assert irregularity < 0.05


def music_like(seconds: float = 2, rate: int = 44_100) -> bytes:
    """Un 770 Hz (el tono de un track de demo) mezclado con otras notas y un bombo."""
    rng = random.Random(7)
    out = array("h")
    for i in range(int(seconds * rate)):
        t = i / rate
        kick = 0.5 * math.sin(2 * math.pi * 55 * t) * math.exp(-((t * 2) % 1) * 8)
        value = (
            0.35 * math.sin(2 * math.pi * 770 * t)
            + 0.25 * math.sin(2 * math.pi * 1130 * t)
            + kick
            + rng.uniform(-0.05, 0.05)
        )
        out.append(int(max(-1.0, min(1.0, value)) * 32767))
    return wav_bytes(out.tobytes())


async def test_fake_ignores_real_music_that_contains_a_catalog_frequency() -> None:
    # Falso positivo real: un set de Franky Rizardo salió como «Oscillator Twins» (770 Hz).
    analysis = analyze_tone(music_like())
    assert analysis.irregularity > 0.15
    assert await FakeProvider().identify(music_like()) is None


# --- ACRCloud -----------------------------------------------------------------------------

ACR_URL = "https://identify-eu-west-1.acrcloud.com/v1/identify"


def acr_ok(score: int = 87) -> dict[str, object]:
    return {
        "status": {"code": 0, "msg": "Success"},
        "metadata": {
            "music": [
                {
                    "title": "Space",
                    "artists": [{"name": "Marco Carola"}, {"name": "Guest"}],
                    "label": "Music On",
                    "album": {"name": "Space EP"},
                    "external_ids": {"isrc": "ITXXX2400001"},
                    "score": score,
                },
                {"title": "Other", "artists": [{"name": "X"}], "score": 40},
            ]
        },
    }


def test_acrcloud_signature_matches_documented_algorithm() -> None:
    expected = base64.b64encode(
        hmac.new(b"secret", b"POST\n/v1/identify\nkey\naudio\n1\n1700000000", hashlib.sha1).digest()
    ).decode()
    assert acrcloud.sign("key", "secret", "1700000000") == expected


def test_acrcloud_parse_success_picks_best_score() -> None:
    match = acrcloud.parse_response(acr_ok())
    assert match is not None
    assert match.artist == "Marco Carola, Guest"
    assert match.title == "Space"
    assert match.label == "Music On"
    assert match.isrc == "ITXXX2400001"
    assert match.confidence == pytest.approx(0.87)


@pytest.mark.parametrize("code", [1001, 2004])
def test_acrcloud_no_result(code: int) -> None:
    assert acrcloud.parse_response({"status": {"code": code}}) is None


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (3015, RetryableProviderError),
        (3003, QuotaExceededError),
        (3001, PermanentProviderError),
        (3014, PermanentProviderError),
        (9999, SegmentProviderError),
    ],
)
def test_acrcloud_error_codes(code: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        acrcloud.parse_response({"status": {"code": code}})


def test_acrcloud_rejects_unexpected_host() -> None:
    with pytest.raises(PermanentProviderError):
        ACRCloudProvider(host="evil.com", access_key="k", access_secret="s")


@respx.mock
async def test_acrcloud_sends_signed_multipart_request() -> None:
    route = respx.post(ACR_URL).mock(return_value=httpx.Response(200, json=acr_ok()))
    provider = ACRCloudProvider(
        host="identify-eu-west-1.acrcloud.com",
        access_key="key",
        access_secret="secret",
        clock=lambda: 1700000000,
    )
    match = await provider.identify(b"RIFFfake")
    await provider.aclose()
    assert match is not None and match.title == "Space"
    body = route.calls.last.request.content
    assert acrcloud.sign("key", "secret", "1700000000").encode() in body
    assert b'name="sample"; filename="segment.wav"' in body
    assert b"secret\r\n" not in body  # el secreto nunca viaja


@respx.mock
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429, headers={"Retry-After": "7"}), RetryableProviderError),
        (httpx.Response(503), RetryableProviderError),
        (httpx.Response(401), PermanentProviderError),
        (httpx.Response(400), SegmentProviderError),
        (httpx.Response(200, text="<html>"), SegmentProviderError),
    ],
)
async def test_acrcloud_http_errors(response: httpx.Response, error: type[Exception]) -> None:
    respx.post(ACR_URL).mock(return_value=response)
    provider = ACRCloudProvider(
        host="identify-eu-west-1.acrcloud.com", access_key="k", access_secret="s"
    )
    with pytest.raises(error) as info:
        await provider.identify(b"x")
    if response.status_code == 429:
        assert isinstance(info.value, RetryableProviderError)
        assert info.value.retry_after_s == 7
    await provider.aclose()


@respx.mock
async def test_network_timeout_is_retryable() -> None:
    respx.post(ACR_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
    provider = ACRCloudProvider(
        host="identify-eu-west-1.acrcloud.com", access_key="k", access_secret="s"
    )
    with pytest.raises(RetryableProviderError):
        await provider.identify(b"x")
    await provider.aclose()


# --- AudD ---------------------------------------------------------------------------------


def test_audd_parse_success_with_isrc_from_apple_music() -> None:
    payload = {
        "status": "success",
        "result": {
            "artist": "Ilario Alicante",
            "title": "Vibes",
            "label": "Cocoon",
            "apple_music": {"isrc": "DEXXX2400001"},
        },
    }
    match = audd.parse_response(payload, confidence=0.8)
    assert match is not None
    assert (match.artist, match.title, match.label) == ("Ilario Alicante", "Vibes", "Cocoon")
    assert match.isrc == "DEXXX2400001"
    assert match.confidence == 0.8


def test_audd_parse_isrc_from_spotify() -> None:
    payload = {
        "status": "success",
        "result": {"artist": "A", "title": "T", "spotify": {"external_ids": {"isrc": "X1"}}},
    }
    match = audd.parse_response(payload, confidence=0.8)
    assert match is not None and match.isrc == "X1"


def test_audd_no_result() -> None:
    assert audd.parse_response({"status": "success", "result": None}, confidence=0.8) is None


@pytest.mark.parametrize(
    ("code", "error"),
    [(900, PermanentProviderError), (901, QuotaExceededError), (902, QuotaExceededError)],
)
def test_audd_error_codes(code: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        audd.parse_response({"status": "error", "error": {"error_code": code}}, confidence=0.8)


@respx.mock
async def test_audd_request_includes_token_only_when_set() -> None:
    route = respx.post("https://api.audd.io/").mock(
        return_value=httpx.Response(200, json={"status": "success", "result": None})
    )
    with_token = AudDProvider(api_token="tok123")
    without = AudDProvider(api_token=None)
    await with_token.identify(b"x")
    assert b"tok123" in route.calls.last.request.content
    await without.identify(b"x")
    assert b"api_token" not in route.calls.last.request.content
    await with_token.aclose()
    await without.aclose()


# --- Shazam -------------------------------------------------------------------------------


def test_shazam_parse_success() -> None:
    payload = {
        "matches": [{"id": "1"}],
        "track": {
            "title": "Tons Of Groove",
            "subtitle": "Miguelle & Tons",
            "isrc": "ITXXX2400009",
            "sections": [
                {
                    "type": "SONG",
                    "metadata": [
                        {"title": "Album", "text": "EP"},
                        {"title": "Label", "text": "Listen To Flow"},
                    ],
                }
            ],
        },
    }
    match = shazam.parse_response(payload, confidence=0.8)
    assert match is not None
    assert (match.artist, match.title) == ("Miguelle & Tons", "Tons Of Groove")
    assert match.label == "Listen To Flow"
    assert match.album == "EP"


def test_shazam_no_match() -> None:
    assert shazam.parse_response({"matches": [], "retryms": 1000}, confidence=0.8) is None


# --- Carátulas ----------------------------------------------------------------------------


def test_shazam_parse_cover_prefers_hq() -> None:
    payload = {
        "matches": [{"id": "1"}],
        "track": {
            "title": "T",
            "subtitle": "A",
            "images": {
                "coverart": "https://is1-ssl.mzstatic.com/image/thumb/a/400x400cc.jpg",
                "coverarthq": "https://is2-ssl.mzstatic.com/image/thumb/a/400x400cc.jpg",
            },
        },
    }
    match = shazam.parse_response(payload, confidence=0.8)
    assert match is not None
    assert match.cover_url == "https://is2-ssl.mzstatic.com/image/thumb/a/600x600bb.jpg"


def test_audd_parse_cover_from_apple_music_template() -> None:
    payload = {
        "status": "success",
        "result": {
            "artist": "A",
            "title": "T",
            "apple_music": {
                "artwork": {"url": "https://is3-ssl.mzstatic.com/image/thumb/b/{w}x{h}bb.jpg"}
            },
        },
    }
    match = audd.parse_response(payload, confidence=0.8)
    assert match is not None
    assert match.cover_url == "https://is3-ssl.mzstatic.com/image/thumb/b/600x600bb.jpg"


@pytest.mark.parametrize(
    "url",
    [
        None,
        42,
        "http://is1-ssl.mzstatic.com/a/100x100bb.jpg",  # sin TLS
        "https://evil.example.com/a.jpg",
        "https://mzstatic.com.evil.example/a.jpg",
        "https://user@is1-ssl.mzstatic.com/a.jpg",
        "https://is1-ssl.mzstatic.com:8443/a.jpg",
        "javascript:alert(1)",
        "https://is1-ssl.mzstatic.com/" + "a" * 1000,
    ],
)
def test_safe_artwork_url_rejects_untrusted(url: object) -> None:
    assert safe_artwork_url(url) is None


def test_safe_artwork_url_drops_query_and_resizes() -> None:
    url = "https://IS1-ssl.mzstatic.com/image/thumb/x/100x100bb.jpg?track=1#frag"
    assert safe_artwork_url(url) == "https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.jpg"


def test_pick_itunes_result_needs_same_title_and_shared_artist() -> None:
    cover = "https://is1-ssl.mzstatic.com/image/thumb/c/100x100bb.jpg"
    payload = {
        "results": [
            {"artistName": "Someone Else", "trackName": "Vibes", "artworkUrl100": "x"},
            {"artistName": "Ilario Alicante", "trackName": "Vibes (Remix)", "artworkUrl100": "x"},
            {
                "artistName": "Ilario Alicante & Friend",
                "trackName": "Vibes (Original Mix)",
                "artworkUrl100": cover,
            },
        ]
    }
    assert pick_itunes_result("Ilario Alicante", "Vibes", payload) == cover.replace(
        "100x100", "600x600"
    )
    assert pick_itunes_result("Nobody", "Vibes", payload) is None
    assert pick_itunes_result("A", "T", "no es un dict") is None


class _MemoryCache:
    def __init__(self) -> None:
        self.data: dict[str, str | None] = {}

    def get(self, key: str) -> tuple[bool, str | None]:
        return (key in self.data, self.data.get(key))

    def put(self, key: str, url: str | None) -> None:
        self.data[key] = url


async def test_artwork_finder_caches_hits_and_misses_but_not_rate_limits() -> None:
    calls: list[str] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["term"])
        assert request.url.host == "itunes.apple.com"
        return httpx.Response(status["code"], json={"results": []})

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    cache = _MemoryCache()
    finder = ArtworkFinder(
        cache,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=fake_sleep,
        clock=lambda: 0.0,
    )
    status["code"] = 429
    assert await finder.find("A", "T") is None
    assert cache.data == {}  # el límite de iTunes no se guarda como «sin carátula»
    status["code"] = 200
    assert await finder.find("A", "T") is None
    assert await finder.find("A", "T") is None  # segunda vez: desde la caché
    assert len(calls) == 2
    assert slept == [LOOKUP_INTERVAL_S]  # respeta el intervalo entre peticiones
    await finder.aclose()

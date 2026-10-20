import pytest

from setid.models import SourceType
from setid.sources.url import (
    CanonicalSource,
    InvalidUrlError,
    ShortLink,
    parse_source_url,
    resolve_source,
)

VID = "dQw4w9WgXcQ"
YT_CANONICAL = f"https://www.youtube.com/watch?v={VID}"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"http://www.youtube.com/watch?v={VID}",
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={VID}",
        f"  https://www.youtube.com/watch?v={VID}&t=3600s  ",
        f"https://www.youtube.com/watch?v={VID}&list=PL123&index=2",
        f"https://www.youtube.com/watch?v={VID}#t=60",
        f"https://www.youtube.com/live/{VID}?si=abc",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=xyz&t=42",
    ],
)
def test_youtube_variants_normalize_to_same_canonical_id(url: str) -> None:
    src = parse_source_url(url)
    assert isinstance(src, CanonicalSource)
    assert src.type is SourceType.YOUTUBE
    assert src.canonical_id == f"yt:{VID}"
    assert src.url == YT_CANONICAL


@pytest.mark.parametrize(
    ("url", "expected_id"),
    [
        ("https://soundcloud.com/marcocarola/music-on-ibiza", "marcocarola/music-on-ibiza"),
        ("https://soundcloud.com/MarcoCarola/Set-2024?utm_source=x", "marcocarola/set-2024"),
        ("https://soundcloud.com/user_1/track/s-AbC123", "user_1/track/s-AbC123"),
    ],
)
def test_soundcloud_tracks(url: str, expected_id: str) -> None:
    src = parse_source_url(url)
    assert isinstance(src, CanonicalSource)
    assert src.type is SourceType.SOUNDCLOUD
    assert src.canonical_id == f"sc:{expected_id}"
    assert src.url == f"https://soundcloud.com/{expected_id}"


def test_soundcloud_short_link_requires_resolution() -> None:
    assert parse_source_url("https://on.soundcloud.com/AbC123") == ShortLink(
        "https://on.soundcloud.com/AbC123"
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "youtube.com/watch?v=dQw4w9WgXcQ",  # sin esquema
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "javascript:alert(1)",
        "file:///etc/passwd",
        f"https://evil.com/watch?v={VID}",
        f"https://youtube.com.evil.com/watch?v={VID}",
        f"https://evilyoutube.com/watch?v={VID}",
        f"https://www.youtube.com.evil.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",  # fuera de la lista blanca
        f"https://youtube.com./watch?v={VID}",  # punto final
        f"https://youtube.com@evil.com/watch?v={VID}",
        f"https://user:pass@youtube.com/watch?v={VID}",
        f"https://evil.com\\@youtube.com/watch?v={VID}",
        f"https://evil.com#@youtube.com/watch?v={VID}",
        f"https://youtube.com:443/watch?v={VID}",
        f"https://youtube.com:8080/watch?v={VID}",
        f"https://youtube.com:99999/watch?v={VID}",
        f"https://127.0.0.1/watch?v={VID}",
        f"https://[::1]/watch?v={VID}",
        f"https://xn--yutube-wqf.com/watch?v={VID}",  # IDN homógrafo
        f"https://yоutube.com/watch?v={VID}",  # 'о' cirílica
        f"https://www.youtube.com/watch?v={VID}\nHost: evil",
        f"https://www.youtube.com/watch?v={VID}%0a",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQX",  # 12 caracteres
        f"https://www.youtube.com/watch?v={VID}&v=aaaaaaaaaaa",
        "https://www.youtube.com/playlist?list=PL1234567890",
        "https://www.youtube.com/@marcocarola",
        "https://www.youtube.com/channel/UC123",
        "https://youtu.be/",
        f"https://youtu.be/{VID}/extra",
        "https://soundcloud.com/marcocarola",
        "https://soundcloud.com/marcocarola/sets/ibiza-2024",
        "https://soundcloud.com/marcocarola/likes",
        "https://soundcloud.com/discover/sets",
        "https://soundcloud.com/search/sounds",
        "https://soundcloud.com/a/b/c/d",
        "https://soundcloud.com/a/b/not-a-secret",
        "https://soundcloud.com/a%2F..%2F/b",
        "https://m.soundcloud.com/a/b",
        "https://on.soundcloud.com/",
        "https://on.soundcloud.com/a/b",
        "https://" + "a" * 3000,
    ],
)
def test_rejects_invalid_or_non_whitelisted(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        parse_source_url(url)


def test_id_starting_with_dashes_never_becomes_an_option() -> None:
    # Es un ID válido para YouTube. No es peligroso porque nunca se pasa suelto a yt-dlp:
    # va dentro de la URL canónica, y esta detrás de "--".
    src = parse_source_url("https://www.youtube.com/watch?v=--option-xx")
    assert isinstance(src, CanonicalSource)
    assert src.url == "https://www.youtube.com/watch?v=--option-xx"


def test_resolve_short_link_follows_one_whitelisted_hop() -> None:
    calls: list[str] = []

    def resolver(url: str) -> str | None:
        calls.append(url)
        return "https://soundcloud.com/artist/track?si=123&utm_medium=text"

    src = resolve_source("https://on.soundcloud.com/AbC", resolver)
    assert calls == ["https://on.soundcloud.com/AbC"]
    assert src.canonical_id == "sc:artist/track"


@pytest.mark.parametrize(
    "location",
    [
        None,
        "",
        "https://evil.com/artist/track",
        "https://on.soundcloud.com/Other",  # cadena de enlaces cortos
        f"https://www.youtube.com/watch?v={VID}",  # tipo distinto
        "https://soundcloud.com/artist/sets/x",
    ],
)
def test_resolve_short_link_rejects_bad_targets(location: str | None) -> None:
    with pytest.raises(InvalidUrlError):
        resolve_source("https://on.soundcloud.com/AbC", lambda _url: location)


def test_resolve_does_not_call_resolver_for_canonical_urls() -> None:
    def resolver(url: str) -> str | None:
        raise AssertionError("no debería llamarse")

    assert resolve_source(f"https://youtu.be/{VID}", resolver).canonical_id == f"yt:{VID}"

"""Enlaces de búsqueda y de salto a un momento del set. Solo URLs de búsqueda, sin APIs."""

from __future__ import annotations

from urllib.parse import quote, quote_plus, urlsplit

from setid.models import SourceType

# Hosts que la interfaz puede abrir en el navegador del sistema. Cualquier otro se rechaza
# (la ventana de la app nunca navega fuera de sus propios archivos).
EXTERNAL_HOSTS = frozenset(
    {
        "www.youtube.com",
        "youtube.com",
        "soundcloud.com",
        "www.beatport.com",
        "open.spotify.com",
    }
)


def search_query(artist: str, title: str) -> str:
    return f"{artist} {title}".strip()


def search_links(artist: str, title: str) -> dict[str, str]:
    q = search_query(artist, title)
    return {
        "beatport": f"https://www.beatport.com/search?q={quote_plus(q)}",
        "spotify": f"https://open.spotify.com/search/{quote(q, safe='')}",
        "youtube": f"https://www.youtube.com/results?search_query={quote_plus(q)}",
    }


def timestamp_link(source_type: SourceType, source_url: str, start_s: float) -> str | None:
    """Abre el set en ese segundo. ``source_url`` es siempre la URL canónica."""
    seconds = int(start_s)
    if source_type is SourceType.YOUTUBE:
        return f"{source_url}&t={seconds}s"
    if source_type is SourceType.SOUNDCLOUD:
        minutes, secs = divmod(seconds, 60)
        return f"{source_url}#t={minutes}:{secs:02d}"
    return None


def is_allowed_external(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname in EXTERNAL_HOSTS
        and parts.username is None
        and parts.port is None
    )

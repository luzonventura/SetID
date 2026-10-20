"""Tracklist de la comunidad: lo que la gente escribe en la descripción y los comentarios.

Nunca se mezcla con el reconocimiento: son *pistas* sin verificar que se muestran aparte y
como sugerencias para los tramos ``ID – ID``.

Qué se busca:

* **Tracklists**: bloques de líneas con marca de tiempo (``12:30 Artista - Título``,
  ``[1:02:10] …``) o numeradas (``1. Artista - Título``), en la descripción o en un
  comentario (fijado, del propio canal o con muchos likes).
* **Menciones sueltas**: un comentario como ``45:10 Artista - Título 🔥``.
* **Preguntas y respuestas**: ``23:15 track id?`` / ``alguien sabe el tema del 1:02:00``. Las
  respuestas a esa pregunta (``It's Artista - Título``) se colocan en su marca de tiempo.
* **Unreleased**: «unreleased», «forthcoming», «dubplate», «ID», «sin publicar»… se marcan.

No se hace scraping de webs de terceros: solo se usa lo que devuelve yt-dlp del propio vídeo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

from setid.aggregate import normalize_artist, normalize_title

MAX_TEXT = 300
MIN_TRACKLIST_LINES = 3
SUGGESTION_MARGIN_S = 45.0
MAX_SUGGESTIONS = 3


class HintKind(StrEnum):
    TRACKLIST = "tracklist"  # línea de un tracklist (descripción o comentario)
    COMMENT = "comment"  # mención suelta con marca de tiempo
    REPLY = "reply"  # respuesta a una pregunta «track id?»


@dataclass(frozen=True)
class Hint:
    kind: HintKind
    start_s: float | None
    artist: str
    title: str
    unreleased: bool
    origin: str  # «descripción», «comentario fijado», «comentario de @x»…
    author: str | None
    likes: int
    text: str
    position: int = 0  # orden dentro de su tracklist
    note: str | None = None  # p. ej. el acapella de un mashup («/W Artista - Acapella»)

    @property
    def is_id(self) -> bool:
        return _is_id(self.artist) and _is_id(self.title)


class ParsedTrack(NamedTuple):
    artist: str
    title: str
    unreleased: bool
    note: str | None = None


@dataclass
class CommunityResult:
    tracklist: list[Hint] = field(default_factory=list)
    tracklist_origin: str | None = None
    hints: list[Hint] = field(default_factory=list)

    @property
    def all(self) -> list[Hint]:
        return [*self.tracklist, *self.hints]


# --- Expresiones ------------------------------------------------------------------------

_TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
_TIMESTAMP = re.compile(rf"(?<![\d:])({_TS})(?![\d:])")
_TS_LINE = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]\s*)?"  # numeración opcional
    rf"[\[(]?\s*(?P<ts>{_TS})\s*[\])]?"  # marca de tiempo, quizá entre corchetes
    rf"\s*(?:[-–—|:.>]+\s*)?"  # separador opcional
    rf"(?P<rest>.*)$"
)
_NUMBERED_LINE = re.compile(r"^\s*(?P<n>\d{1,3})\s*[.)\-]\s+(?P<rest>.+)$")
_SEPARATOR = re.compile(r"\s+[-–—~]\s+|\s+[-–—]\s*|\s*[-–—]\s+")
_UNRELEASED_WORDS = (
    r"unreleased|forthcoming|out\s+soon|coming\s+soon|not\s+out(?:\s+yet)?|dub\s*plate|"
    r"not\s+releas(?:ing|ed)|never\s+releas(?:ed|ing)|won'?t\s+be\s+released|no\s+release|"
    r"sin\s+(?:publicar|sacar|salir)|in[eé]dit[oa]|no\s+(?:est[aá]\s+)?(?:publicad[oa]|sacad[oa])|"
    r"no\s+(?:va\s+a\s+)?sal(?:e|ir|dr[aá])"
)
_UNRELEASED = re.compile(rf"\b(?:{_UNRELEASED_WORDS})\b", re.IGNORECASE)
# Mashups: «Track /W Artista - Acapella», «Track w/ Acapella», «Track / with …».
_MASHUP = re.compile(r"\s*/\s*w(?:ith)?\b\.?\s*|\s+w/\s*", re.IGNORECASE)
_QUESTION = re.compile(
    r"(track\s*-?\s*id|\bid\s*\?|\bid\s+(pls|please|plz|anyone)|"
    r"what'?s?\s+(is\s+)?(the\s+|this\s+)?(track|song|tune)|"
    r"name\s+of\s+(the\s+|this\s+)?(track|song|tune)|(track|song)\s+name|tune\s*\?|"
    r"anyone\s+know|who\s+knows|"
    r"alguien\s+sabe|qu[eé]\s+(tema|canci[oó]n)|nombre\s+del\s+(tema|track)|c[oó]mo\s+se\s+llama)",
    re.IGNORECASE,
)
_ANSWER_PREFIX = re.compile(
    r"^\s*(?:@[\w.\-]+\s*)?(?:it'?s|its|it\s+is|this\s+is|that'?s|track\s+is|song\s+is|"
    r"i\s+think\s+(?:it'?s)?|pretty\s+sure\s+(?:it'?s)?|es|creo\s+que\s+es|se\s+llama)?\s*[:\-]?\s*",
    re.IGNORECASE,
)
_UNRELEASED_SUFFIX = re.compile(
    rf"\s*[\(\[]\s*(?:{_UNRELEASED_WORDS})[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_ID_WORDS = {"id", "unknown", "?", "??", "???", "desconocido"}


def parse_timestamp(text: str) -> float:
    parts = [int(p) for p in text.split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return float(seconds)


def _strip_decoration(text: str) -> str:
    """Quita emojis, comillas y puntuación sobrante de los extremos."""
    keep_end = set(")]")
    chars = list(text.strip())

    def junk(ch: str, *, end: bool) -> bool:
        if ch.isalnum() or (end and ch in keep_end) or (not end and ch in "(["):
            return False
        return unicodedata.category(ch)[0] in {"S", "P", "Z", "C"} or ch in "️‍"

    while chars and junk(chars[-1], end=True):
        chars.pop()
    while chars and junk(chars[0], end=False):
        chars.pop(0)
    return "".join(chars).strip()


def _is_id(text: str) -> bool:
    return text.strip().lower() in _ID_WORDS


def _has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def split_track(text: str) -> ParsedTrack | None:
    """``"Artista - Título (Unreleased)"`` → ``ParsedTrack("Artista", "Título", True)``.

    En un mashup (``"A - Track /W B - Acapella"``) el track principal es lo de antes del
    ``/W`` y el resto va a ``note``: así las búsquedas usan solo el track principal.
    """
    clean = _strip_decoration(text)
    if not clean or len(clean) > MAX_TEXT:
        return None
    unreleased = bool(_UNRELEASED.search(clean))
    clean = _UNRELEASED_SUFFIX.sub("", clean).strip()
    main, *rest = _MASHUP.split(clean, maxsplit=1)
    note = _strip_decoration(rest[0]) if rest else None
    parts = _SEPARATOR.split(main, maxsplit=1)
    if len(parts) != 2:
        return None
    artist, title = (_strip_decoration(p) for p in parts)
    if not artist or not title:
        return None
    if _is_id(artist) and _is_id(title):
        return ParsedTrack("ID", "ID", True)
    if not (_has_letters(artist) and _has_letters(title)):
        return None
    if len(artist) > 120 or len(title) > 160:
        return None
    return ParsedTrack(artist, title, unreleased or _is_id(title) or _is_id(artist), note or None)


@dataclass(frozen=True)
class _Line:
    start_s: float | None
    track: ParsedTrack | None
    raw: str


def _parse_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for raw in text.splitlines():
        if m := _TS_LINE.match(raw):
            lines.append(_Line(parse_timestamp(m["ts"]), split_track(m["rest"]), raw.strip()))
        elif m := _NUMBERED_LINE.match(raw):
            lines.append(_Line(None, split_track(m["rest"]), raw.strip()))
    return lines


def tracklist_from_text(text: str) -> list[tuple[float | None, ParsedTrack, str]]:
    """Extrae un tracklist si el texto contiene al menos MIN_TRACKLIST_LINES pistas."""
    tracks = [(line.start_s, line.track, line.raw) for line in _parse_lines(text) if line.track]
    return tracks if len(tracks) >= MIN_TRACKLIST_LINES else []


# --- Comentarios --------------------------------------------------------------------------


@dataclass(frozen=True)
class Comment:
    id: str
    parent: str  # "root" o el id del comentario al que responde
    text: str
    author: str | None
    likes: int
    is_pinned: bool
    by_uploader: bool

    @classmethod
    def from_ytdlp(cls, raw: dict[str, Any]) -> Comment | None:
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        likes = raw.get("like_count")
        return cls(
            id=str(raw.get("id") or ""),
            parent=str(raw.get("parent") or "root"),
            text=text[:5000],
            author=raw.get("author") if isinstance(raw.get("author"), str) else None,
            likes=likes if isinstance(likes, int) and likes >= 0 else 0,
            is_pinned=bool(raw.get("is_pinned")),
            by_uploader=bool(raw.get("author_is_uploader")),
        )


def _origin(comment: Comment) -> str:
    if comment.is_pinned:
        return "comentario fijado"
    if comment.by_uploader:
        return "comentario del canal"
    return f"comentario de {comment.author}" if comment.author else "comentario"


def _hint(
    kind: HintKind,
    start_s: float | None,
    track: ParsedTrack,
    origin: str,
    comment: Comment | None,
    text: str,
    position: int = 0,
) -> Hint:
    return Hint(
        kind=kind,
        start_s=start_s,
        artist=track.artist,
        title=track.title,
        unreleased=track.unreleased,
        origin=origin,
        author=comment.author if comment else None,
        likes=comment.likes if comment else 0,
        text=text[:MAX_TEXT],
        position=position,
        note=track.note,
    )


def _to_tracklist(
    tracks: list[tuple[float | None, ParsedTrack, str]], origin: str, comment: Comment | None
) -> list[Hint]:
    return [
        _hint(HintKind.TRACKLIST, start, track, origin, comment, raw, i)
        for i, (start, track, raw) in enumerate(tracks, start=1)
    ]


def _answer_track(text: str) -> tuple[float | None, ParsedTrack] | None:
    """La primera pista que aparezca en una respuesta (con o sin marca de tiempo)."""
    for raw in text.splitlines():
        if m := _TS_LINE.match(raw):
            start: float | None = parse_timestamp(m["ts"])
            body = m["rest"]
        else:
            start, body = None, raw
        body = _ANSWER_PREFIX.sub("", body, count=1)
        if track := split_track(body):
            return start, track
    return None


def parse_community(description: str | None, comments: Iterable[dict[str, Any]]) -> CommunityResult:
    parsed = [c for raw in comments if isinstance(raw, dict) if (c := Comment.from_ytdlp(raw))]
    result = CommunityResult()

    # 1. El tracklist «oficial»: descripción > comentario fijado/del canal > más likes.
    candidates: list[tuple[int, list[Hint], str]] = []
    if description and (tracks := tracklist_from_text(description)):
        candidates.append((10**9, _to_tracklist(tracks, "descripción", None), "descripción"))
    tracklist_comment_ids: set[str] = set()
    for c in parsed:
        if c.parent != "root" and not c.by_uploader:
            continue
        if tracks := tracklist_from_text(c.text):
            tracklist_comment_ids.add(c.id)
            weight = c.likes + (10**8 if c.is_pinned or c.by_uploader else 0)
            candidates.append((weight, _to_tracklist(tracks, _origin(c), c), _origin(c)))
    if candidates:
        _, result.tracklist, result.tracklist_origin = max(candidates, key=lambda x: x[0])

    # 2. Menciones sueltas y preguntas en comentarios raíz.
    questions: dict[str, float | None] = {}
    for c in parsed:
        if c.parent != "root" or c.id in tracklist_comment_ids:
            continue
        stamps = [parse_timestamp(t) for t in _TIMESTAMP.findall(c.text)]
        # «23:15 Is this Artist - Title?» también es una pregunta: no es una afirmación.
        if _QUESTION.search(c.text) or c.text.rstrip().endswith("?"):
            questions[c.id] = stamps[0] if stamps else None
            continue
        for line in _parse_lines(c.text):
            if line.track and line.start_s is not None:
                result.hints.append(
                    _hint(HintKind.COMMENT, line.start_s, line.track, _origin(c), c, line.raw)
                )

    # 3. Respuestas a preguntas: se colocan en la marca de tiempo de la pregunta.
    for c in parsed:
        if c.parent == "root" or c.parent not in questions:
            continue
        if found := _answer_track(c.text):
            start, track = found
            when = start if start is not None else questions[c.parent]
            if when is None:
                continue
            origin = f"respuesta de {c.author}" if c.author else "respuesta"
            result.hints.append(_hint(HintKind.REPLY, when, track, origin, c, c.text))

    result.hints = _dedupe(result.hints)
    return result


def _key(hint: Hint) -> tuple[str, str, int]:
    bucket = -1 if hint.start_s is None else int(hint.start_s // 60)
    return normalize_artist(hint.artist), normalize_title(hint.title), bucket


def _dedupe(hints: Sequence[Hint]) -> list[Hint]:
    best: dict[tuple[str, str, int], Hint] = {}
    for h in hints:
        k = _key(h)
        if k not in best or h.likes > best[k].likes:
            best[k] = h
    return sorted(best.values(), key=lambda h: (h.start_s is None, h.start_s or 0, -h.likes))


# --- Sugerencias para los ID – ID -----------------------------------------------------------

_KIND_RANK = {HintKind.TRACKLIST: 0, HintKind.REPLY: 1, HintKind.COMMENT: 2}


def track_key(artist: str, title: str) -> tuple[str, str]:
    return normalize_artist(artist), normalize_title(title)


def _is_known(hint: Hint, known: frozenset[tuple[str, str]]) -> bool:
    """Mismo título y al menos un artista en común con un track ya identificado.

    La gente suele escribir solo uno de los artistas («Sofia Varela» por «Sofia Varela &
    K-Loop»), así que exigir todos dejaría pasar el track anterior o el siguiente.
    """
    artists, title = track_key(hint.artist, hint.title)
    names = set(artists.split(" & "))
    return any(
        title == known_title and names & set(known_artists.split(" & "))
        for known_artists, known_title in known
    )


def suggestions_for(
    start_s: float,
    end_s: float,
    hints: Sequence[Hint],
    *,
    known: frozenset[tuple[str, str]] = frozenset(),
    margin_s: float = SUGGESTION_MARGIN_S,
    limit: int = MAX_SUGGESTIONS,
) -> list[Hint]:
    """Pistas de la comunidad que caen dentro de un tramo (con margen).

    ``known`` son los tracks ya identificados por huella en el set: no se sugieren, porque
    junto a un ID – ID casi siempre son el track anterior o el siguiente.
    """
    inside = [
        h
        for h in hints
        if h.start_s is not None
        and start_s - margin_s <= h.start_s <= end_s + margin_s
        and not _is_known(h, known)
    ]
    # Primero las que dan nombre (no «ID – ID»), luego tracklist > respuesta > comentario.
    inside.sort(key=lambda h: (h.is_id, _KIND_RANK[h.kind], -h.likes, h.start_s or 0))
    seen: set[tuple[str, str]] = set()
    out: list[Hint] = []
    for h in inside:
        k = track_key(h.artist, h.title)
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
        if len(out) == limit:
            break
    return out

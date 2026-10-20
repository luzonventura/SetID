"""Exportación del tracklist a texto, CSV, JSON y M3U."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from setid.links import search_links
from setid.models import TracklistEntry


class ExportFormat(StrEnum):
    TXT = "txt"
    CSV = "csv"
    JSON = "json"
    M3U = "m3u"


MEDIA_TYPES = {
    ExportFormat.TXT: "text/plain",
    ExportFormat.CSV: "text/csv",
    ExportFormat.JSON: "application/json",
    ExportFormat.M3U: "audio/x-mpegurl",
}


@dataclass(frozen=True)
class ExportMeta:
    title: str
    uploader: str | None
    duration_s: float | None
    source: str | None
    provider: str


@dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    content: str


def format_time(seconds: float, *, with_hours: bool = False) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h or with_hours else f"{m:02d}:{s:02d}"


def _line(entry: TracklistEntry) -> str:
    if entry.is_unknown:
        return "ID – ID"
    text = f"{entry.artist} – {entry.title}"
    return f"{text} [{entry.label}]" if entry.label else text


def to_text(meta: ExportMeta, entries: Sequence[TracklistEntry]) -> str:
    """El formato habitual para pegar en la descripción de un vídeo o un comentario."""
    # Si el set pasa de una hora, todas las marcas llevan horas para que queden alineadas.
    hours = any(e.start_s >= 3600 for e in entries)
    header = meta.title + (f" — {meta.uploader}" if meta.uploader else "")
    lines = [header, ""]
    lines += [f"{format_time(e.start_s, with_hours=hours)} {_line(e)}" for e in entries]
    return "\n".join(lines) + "\n"


_CSV_COLUMNS = (
    "position", "start", "start_s", "artist", "title", "label", "isrc", "confidence",
    "detections", "source", "beatport", "spotify", "youtube",
)  # fmt: skip
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    # Inyección de fórmulas: un artista "=HYPERLINK(...)" se ejecutaría al abrir en Excel.
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def to_csv(entries: Sequence[TracklistEntry]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for e in entries:
        links = {} if e.is_unknown else search_links(e.artist, e.title)
        row = [
            e.position, format_time(e.start_s), int(e.start_s), e.artist, e.title,
            e.label or "", e.isrc or "", "" if e.confidence is None else f"{e.confidence:.2f}",
            e.detections, e.source.value, links.get("beatport", ""), links.get("spotify", ""),
            links.get("youtube", ""),
        ]  # fmt: skip
        writer.writerow([_csv_safe(v) for v in row])
    return buffer.getvalue()


def to_json(meta: ExportMeta, entries: Sequence[TracklistEntry]) -> str:
    payload = {
        "title": meta.title,
        "uploader": meta.uploader,
        "duration_s": meta.duration_s,
        "source": meta.source,
        "provider": meta.provider,
        "tracklist": [
            {
                **e.model_dump(mode="json"),
                "start": format_time(e.start_s),
                "links": None if e.is_unknown else search_links(e.artist, e.title),
            }
            for e in entries
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def to_m3u(meta: ExportMeta, entries: Sequence[TracklistEntry]) -> str:
    """Lista M3U con un enlace de búsqueda por track (los ``ID – ID`` se omiten)."""
    lines = ["#EXTM3U", f"#PLAYLIST:{_one_line(meta.title)}"]
    for e in entries:
        if e.is_unknown:
            continue
        duration = max(1, int(e.end_s - e.start_s))
        lines.append(f"#EXTINF:{duration},{_one_line(e.artist)} - {_one_line(e.title)}")
        lines.append(search_links(e.artist, e.title)["youtube"])
    return "\n".join(lines) + "\n"


def _one_line(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text).strip()


def safe_filename(title: str, extension: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .")[:120] or "tracklist"
    return f"{stem}.{extension}"


def export(fmt: ExportFormat, meta: ExportMeta, entries: Sequence[TracklistEntry]) -> ExportFile:
    if fmt is ExportFormat.TXT:
        content = to_text(meta, entries)
    elif fmt is ExportFormat.CSV:
        content = to_csv(entries)
    elif fmt is ExportFormat.JSON:
        content = to_json(meta, entries)
    else:
        content = to_m3u(meta, entries)
    return ExportFile(safe_filename(meta.title, fmt.value), MEDIA_TYPES[fmt], content)

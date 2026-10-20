"""CLI: ``setid <url|archivo>`` imprime el tracklist en la terminal."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from setid.audio.demo import generate_demo_set
from setid.audio.ffmpeg import InvalidAudioError
from setid.community import Hint, HintKind, parse_community, suggestions_for, track_key
from setid.config import ProviderName, Settings
from setid.models import TracklistEntry
from setid.pipeline import (
    PipelineResult,
    Progress,
    http_redirect_resolver,
    looks_like_url,
    run_pipeline,
)
from setid.proc import YT_DLP_FLAG, ProcessError
from setid.providers.base import PermanentProviderError
from setid.providers.registry import build_provider
from setid.recognize import BudgetExhaustedError
from setid.sources import ytdlp
from setid.sources.url import InvalidUrlError, resolve_source
from setid.sources.ytdlp import SourceRejected
from setid.workdir import purge_stale

EXIT_OK, EXIT_ERROR, EXIT_INPUT = 0, 1, 2


def format_time(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def confidence_bar(value: float | None, width: int = 5) -> str:
    if value is None:
        return ""
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled) + f" {value:.2f}"


def format_entry(entry: TracklistEntry, time_width: int) -> str:
    time = format_time(entry.start_s).rjust(time_width)
    if entry.is_unknown:
        return f"{entry.position:>3}  {time}  ID – ID"
    line = f"{entry.position:>3}  {time}  {entry.artist} – {entry.title}"
    if entry.label:
        line += f"  [{entry.label}]"
    return f"{line}  {confidence_bar(entry.confidence)}"


def format_hint(hint: Hint, *, with_origin: bool = True) -> str:
    text = "ID – ID" if hint.is_id else f"{hint.artist} – {hint.title}"
    if hint.unreleased and not hint.is_id:
        text += " (unreleased)"
    if hint.note:
        text += f"  + {hint.note}"
    if not with_origin:
        return text
    likes = f", {hint.likes} likes" if hint.likes else ""
    return f"{text}  · {hint.origin}{likes}"


def format_result(result: PipelineResult, hints: Sequence[Hint] = ()) -> str:
    header = result.title
    if result.uploader:
        header += f" — {result.uploader}"
    width = len(format_time(result.duration_s))
    lines = [f"{header} ({format_time(result.duration_s)})", ""]
    known = frozenset(track_key(e.artist, e.title) for e in result.tracklist if not e.is_unknown)
    for entry in result.tracklist:
        lines.append(format_entry(entry, width))
        if entry.is_unknown:
            for hint in suggestions_for(entry.start_s, entry.end_s, hints, known=known):
                lines.append(f"{'':>{width + 7}}↳ comunidad: {format_hint(hint)}")
    if not result.tracklist:
        lines.append("  No se ha identificado ningún track.")
    community = [h for h in hints if h.kind is HintKind.TRACKLIST]
    if community:
        lines += ["", f"Tracklist de la comunidad (sin verificar, de: {community[0].origin})"]
        for h in community:
            when = format_time(h.start_s) if h.start_s is not None else ""
            lines.append(
                f"{h.position:>3}  {when.rjust(width)}  {format_hint(h, with_origin=False)}"
            )
    s = result.stats
    lines += [
        "",
        f"Proveedor: {result.provider} · consultas: {s.queries} (reintentos: {s.retries}, "
        f"errores: {s.errors}) · coste estimado: ${s.cost:.4f}",
    ]
    return "\n".join(lines)


def result_to_json(result: PipelineResult, hints: Sequence[Hint] = ()) -> str:
    return json.dumps(
        {
            "source_type": result.source_type.value,
            "canonical_id": result.canonical_id,
            "title": result.title,
            "uploader": result.uploader,
            "duration_s": result.duration_s,
            "provider": result.provider,
            "queries_used": result.stats.queries,
            "estimated_cost": result.stats.cost,
            "tracklist": [e.model_dump(mode="json") for e in result.tracklist],
            "community": [
                {**dataclasses.asdict(h), "kind": h.kind.value, "is_id": h.is_id} for h in hints
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setid", description="Extrae el tracklist de un set de DJ."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("source", nargs="?", help="URL de YouTube/SoundCloud o archivo de audio")
    target.add_argument(
        "--make-demo",
        metavar="WAV",
        type=Path,
        help="genera un set sintético para probar con --provider fake",
    )
    parser.add_argument("--provider", choices=[p.value for p in ProviderName])
    parser.add_argument("--window", type=float, help="duración de cada segmento (s)")
    parser.add_argument("--step", type=float, help="separación entre segmentos (s)")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--max-queries", type=int, help="presupuesto máximo de consultas")
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    parser.add_argument(
        "--no-community", action="store_true", help="no leer la descripción ni los comentarios"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="sin barra de progreso")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    overrides = {
        "provider": args.provider,
        "window_s": args.window,
        "step_s": args.step,
        "concurrency": args.concurrency,
        "min_confidence": args.min_confidence,
        "daily_query_budget": args.max_queries,
        "community_enabled": False if args.no_community else None,
    }
    return Settings(**{k: v for k, v in overrides.items() if v is not None})


class ProgressPrinter:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled and sys.stderr.isatty()

    def __call__(self, progress: Progress) -> None:
        if not self.enabled:
            return
        found = sum(1 for e in progress.tracklist or [] if not e.is_unknown)
        tracks = f" · {found} tracks" if progress.tracklist is not None else ""
        line = f"\r[{progress.percent:5.1f}%] {progress.message}{tracks}"
        sys.stderr.write(line.ljust(70))
        sys.stderr.flush()

    def done(self) -> None:
        if self.enabled:
            sys.stderr.write("\r" + " " * 70 + "\r")
            sys.stderr.flush()


async def _community(source: str, settings: Settings) -> list[Hint]:
    """Descripción y comentarios, en paralelo con el análisis. Si falla, no pasa nada."""
    try:
        canonical = await asyncio.to_thread(resolve_source, source, http_redirect_resolver())
        data = await asyncio.to_thread(
            ytdlp.fetch_community,
            canonical,
            max_comments=settings.community_max_comments,
            timeout=settings.community_timeout_s,
        )
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).info("no se pudieron leer los comentarios")
        return []
    return parse_community(data.description, data.comments).all


async def _identify(
    source: str, settings: Settings, printer: ProgressPrinter
) -> tuple[PipelineResult, list[Hint]]:
    purge_stale(settings.temp_root)
    provider = build_provider(settings)
    community = (
        asyncio.create_task(_community(source, settings))
        if settings.community_enabled and looks_like_url(source)
        else None
    )
    try:
        result = await run_pipeline(source, settings, provider, on_progress=printer)
        return result, (await community if community else [])
    finally:
        if community and not community.done():
            community.cancel()
        await provider.aclose()


def run_yt_dlp(argv: list[str]) -> int:
    """Modo interno del ejecutable: ``setid-cli.exe --yt-dlp <args>`` es yt-dlp tal cual.

    Lo usa la app empaquetada (ver ``proc.yt_dlp_command``); los argumentos siempre vienen de
    código propio, nunca de un shell.
    """
    import yt_dlp

    try:
        yt_dlp.main(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    raw = sys.argv[1:] if argv is None else argv
    if raw[:1] == [YT_DLP_FLAG]:
        return run_yt_dlp(raw[1:])
    args = build_parser().parse_args(raw)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.make_demo:
        generate_demo_set(args.make_demo)
        print(f"Set de demo generado en {args.make_demo}")
        print(f"Pruébalo con: setid --provider fake {args.make_demo}")
        return EXIT_OK

    try:
        settings = settings_from_args(args)
    except ValidationError as exc:
        print(f"Configuración no válida: {exc}", file=sys.stderr)
        return EXIT_INPUT

    printer = ProgressPrinter(enabled=not args.quiet)
    try:
        result, hints = asyncio.run(_identify(args.source, settings, printer))
    except (InvalidUrlError, InvalidAudioError, SourceRejected) as exc:
        printer.done()
        print(f"Entrada no válida: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except (PermanentProviderError, BudgetExhaustedError) as exc:
        printer.done()
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except ProcessError as exc:
        printer.done()
        print(f"Error: {exc}", file=sys.stderr)
        if args.verbose and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        printer.done()
        print("Cancelado.", file=sys.stderr)
        return 130
    printer.done()
    print(result_to_json(result, hints) if args.json else format_result(result, hints))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

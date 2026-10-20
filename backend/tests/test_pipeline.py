"""Tests de extremo a extremo con ffmpeg real y FakeProvider."""

from __future__ import annotations

from pathlib import Path

import pytest

from setid.audio.demo import DemoPart, generate_demo_set
from setid.audio.ffmpeg import InvalidAudioError
from setid.cli import format_result, main
from setid.config import Settings
from setid.models import EntrySource, Match
from setid.pipeline import Phase, Progress, run_pipeline
from setid.providers.base import PermanentProviderError
from setid.providers.fake import FakeProvider
from setid.recognize import BudgetExhaustedError, FixedBudget

pytestmark = pytest.mark.ffmpeg

SHORT_SET = (
    DemoPart(90, 330.0),
    DemoPart(120, None),
    DemoPart(90, 440.0),
    DemoPart(60, 330.0),
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", provider="fake")


@pytest.fixture(scope="module")
def demo_mp3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Se genera WAV y se le da otra extensión: el tipo real se detecta por contenido.
    path = tmp_path_factory.mktemp("demo") / "short-set.flac"
    generate_demo_set(path, SHORT_SET)
    return path


def leftover_files(settings: Settings) -> list[Path]:
    root = settings.temp_root
    return [p for p in root.rglob("*")] if root.exists() else []


async def test_pipeline_end_to_end(demo_mp3: Path, settings: Settings) -> None:
    events: list[Progress] = []
    result = await run_pipeline(str(demo_mp3), settings, FakeProvider(), on_progress=events.append)

    summary = [(e.title if not e.is_unknown else "ID", e.start_s) for e in result.tracklist]
    assert summary == [
        ("Night Shift", 0),
        ("ID", 90),
        ("Groove Theory", 210),
        ("Night Shift", 300),
    ]
    assert result.tracklist[1].source is EntrySource.UNKNOWN
    assert result.stats.queries == 12
    assert result.canonical_id.startswith("file:")
    assert result.duration_s == pytest.approx(360)

    phases = [e.phase for e in events]
    assert phases[0] is Phase.DOWNLOADING
    assert Phase.ANALYZING in phases
    assert phases[-1] is Phase.DONE
    assert [e.percent for e in events] == sorted(e.percent for e in events)
    assert any(e.tracklist for e in events if e.phase is Phase.ANALYZING)

    assert leftover_files(settings) == []
    assert demo_mp3.exists()  # el archivo del usuario no se toca


async def test_workdir_is_removed_when_job_fails(demo_mp3: Path, settings: Settings) -> None:
    class Broken(FakeProvider):
        async def identify(self, segment: bytes) -> Match | None:
            raise PermanentProviderError("credenciales")

    with pytest.raises(PermanentProviderError):
        await run_pipeline(str(demo_mp3), settings, Broken())
    assert leftover_files(settings) == []


async def test_budget_is_checked_before_processing(demo_mp3: Path, settings: Settings) -> None:
    with pytest.raises(BudgetExhaustedError, match="12 consultas"):
        await run_pipeline(str(demo_mp3), settings, FakeProvider(), budget=FixedBudget(5))
    assert leftover_files(settings) == []


async def test_rejects_non_audio_file(tmp_path: Path, settings: Settings) -> None:
    fake = tmp_path / "set.wav"
    fake.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with pytest.raises(InvalidAudioError):
        await run_pipeline(str(fake), settings, FakeProvider())


def test_cli_prints_tracklist(
    demo_mp3: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SETID_DATA_DIR", str(tmp_path / "cli-data"))
    assert main(["--provider", "fake", "-q", str(demo_mp3)]) == 0
    out = capsys.readouterr().out
    assert "Lumen Grid – Night Shift" in out
    assert "ID – ID" in out
    assert "consultas: 12" in out


def test_cli_rejects_bad_url(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-q", "https://evil.com/watch?v=dQw4w9WgXcQ"]) == 2
    assert "Entrada no válida" in capsys.readouterr().err


def test_format_result_handles_empty_tracklist(demo_mp3: Path) -> None:
    from setid.models import SourceType
    from setid.pipeline import PipelineResult
    from setid.recognize import RecognitionStats

    text = format_result(
        PipelineResult(
            source_type=SourceType.UPLOAD,
            canonical_id="file:x",
            title="Set",
            uploader=None,
            duration_s=3700,
            tracklist=[],
            segments=[],
            stats=RecognitionStats(),
            provider="fake",
        )
    )
    assert "1:01:40" in text
    assert "ningún track" in text

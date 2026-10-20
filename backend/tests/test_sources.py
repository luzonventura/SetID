from __future__ import annotations

import json
from pathlib import Path

import pytest

from setid import proc
from setid.audio import ffmpeg
from setid.proc import ProcessResult
from setid.sources import ytdlp
from setid.sources.url import parse_source_url

VID = "dQw4w9WgXcQ"


def info(**overrides: object) -> str:
    base: dict[str, object] = {
        "_type": "video",
        "id": VID,
        "title": "Marco Carola @ Music On",
        "uploader": "Music On",
        "duration": 3600,
        "extractor_key": "Youtube",
        "description": "00:00 Intro",
    }
    base.update(overrides)
    return json.dumps(base)


def test_parse_metadata_ok() -> None:
    meta = ytdlp.parse_metadata(info(), max_duration_s=4 * 3600)
    assert meta.title == "Marco Carola @ Music On"
    assert meta.duration_s == 3600


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration": 4 * 3600 + 1},
        {"duration": None},
        {"duration": 0},
        {"is_live": True},
        {"_type": "playlist"},
        {"extractor_key": "Generic"},
    ],
)
def test_parse_metadata_rejects(overrides: dict[str, object]) -> None:
    with pytest.raises(ytdlp.SourceRejected):
        ytdlp.parse_metadata(info(**overrides), max_duration_s=4 * 3600)


def test_parse_metadata_rejects_garbage() -> None:
    with pytest.raises(ytdlp.SourceRejected):
        ytdlp.parse_metadata("not json", max_duration_s=100)


def test_yt_dlp_receives_canonical_url_after_double_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_run(args: list[str], *, timeout: float, program: str | None = None) -> ProcessResult:
        captured.append(list(args))
        return ProcessResult(info(), "")

    monkeypatch.setattr(proc, "run", fake_run)
    source = parse_source_url(f"https://youtu.be/{VID}?si=abc&list=PL1")
    assert not isinstance(source, type(None))
    ytdlp.fetch_metadata(source, max_duration_s=14400, timeout=5)  # type: ignore[arg-type]
    args = captured[0]
    assert args[-2:] == ["--", f"https://www.youtube.com/watch?v={VID}"]
    assert "--ignore-config" in args
    assert "--no-playlist" in args


def test_proc_run_rejects_string_commands() -> None:
    with pytest.raises(TypeError):
        proc.run("echo hi", timeout=1)  # type: ignore[arg-type]


def test_ffmpeg_input_is_absolute_file_url(tmp_path: Path) -> None:
    path = tmp_path / "-i evil.mp3"
    value = ffmpeg.ffmpeg_input(path)
    assert value.startswith("file:")
    assert not value.removeprefix("file:").startswith("-")


def test_parse_probe_accepts_audio() -> None:
    raw = json.dumps(
        {
            "format": {"format_name": "mp3", "duration": "123.4"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
        }
    )
    assert ffmpeg.parse_probe(raw).duration_s == pytest.approx(123.4)


@pytest.mark.parametrize(
    "payload",
    [
        {"format": {"format_name": "png_pipe", "duration": "1"}, "streams": []},
        {"format": {"format_name": "mp4", "duration": "10"}, "streams": [{"codec_type": "video"}]},
        {"format": {"format_name": "mp3"}, "streams": [{"codec_type": "audio"}]},
    ],
)
def test_parse_probe_rejects(payload: dict[str, object]) -> None:
    with pytest.raises(ffmpeg.InvalidAudioError):
        ffmpeg.parse_probe(json.dumps(payload))


@pytest.mark.ffmpeg
def test_validate_rejects_fake_audio_by_content(tmp_path: Path) -> None:
    fake = tmp_path / "set.mp3"
    fake.write_text("esto no es audio")
    with pytest.raises(ffmpeg.InvalidAudioError):
        ffmpeg.validate_local_file(fake, max_bytes=10**9, max_duration_s=3600)


@pytest.mark.ffmpeg
def test_validate_enforces_size_limit(tmp_path: Path) -> None:
    big = tmp_path / "a.wav"
    big.write_bytes(b"\x00" * 2048)
    with pytest.raises(ffmpeg.InvalidAudioError, match="límite"):
        ffmpeg.validate_local_file(big, max_bytes=1024, max_duration_s=3600)

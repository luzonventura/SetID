import io
import wave
from array import array
from pathlib import Path

import pytest

from setid.audio.segment import iter_segments, segment_starts
from tests.helpers import counter_wav, write_wav


def test_segment_starts_one_hour() -> None:
    starts = segment_starts(3600, 12, 30)
    assert len(starts) == 120
    assert starts[:3] == [0, 30, 60]
    assert starts[-1] == 3570


def test_segment_starts_skips_too_short_tail() -> None:
    assert segment_starts(62, 12, 30) == [0, 30]  # el resto (2 s) no merece una consulta
    assert segment_starts(65, 12, 30) == [0, 30, 60]


def test_segment_starts_short_input() -> None:
    assert segment_starts(0, 12, 30) == []
    assert segment_starts(3, 12, 30) == []
    assert segment_starts(10, 12, 30) == [0]


def test_segment_starts_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        segment_starts(100, 0, 30)


def _samples(wav_data: bytes) -> array[int]:
    with wave.open(io.BytesIO(wav_data), "rb") as wav:
        out = array("h")
        out.frombytes(wav.readframes(wav.getnframes()))
        return out


def test_iter_segments_reads_the_right_audio(tmp_path: Path) -> None:
    path = counter_wav(tmp_path / "counter.wav", seconds=100)
    segments = list(iter_segments(path, window_s=12, step_s=30))
    assert [s.start_s for s in segments] == [0, 30, 60, 90]
    for seg in segments:
        samples = _samples(seg.wav)
        assert samples[0] == seg.start_s
        assert samples[-1] == min(seg.start_s + 11, 99)
    assert segments[-1].duration_s == pytest.approx(10)


def test_iter_segments_is_lazy(tmp_path: Path) -> None:
    path = counter_wav(tmp_path / "counter.wav", seconds=100)
    gen = iter_segments(path, window_s=12, step_s=30)
    first = next(gen)
    assert first.index == 0
    gen.close()


def test_iter_segments_requires_normalized_wav(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "x.wav", b"\x00\x00" * 22_050, rate=22_050)
    with pytest.raises(ValueError, match="normalizado"):
        list(iter_segments(path, window_s=12, step_s=30))

from setid.cli import format_result
from setid.community import parse_community
from setid.models import EntrySource, SourceType, TracklistEntry
from setid.pipeline import PipelineResult
from setid.recognize import RecognitionStats


def entry(
    position: int, start: float, end: float, artist: str = "ID", title: str = "ID"
) -> TracklistEntry:
    unknown = artist == "ID"
    return TracklistEntry(
        position=position,
        start_s=start,
        end_s=end,
        artist=artist,
        title=title,
        confidence=None if unknown else 0.9,
        detections=0 if unknown else 4,
        source=EntrySource.UNKNOWN if unknown else EntrySource.FINGERPRINT,
    )


def test_cli_shows_community_suggestions_under_unknown_stretches() -> None:
    result = PipelineResult(
        source_type=SourceType.YOUTUBE,
        canonical_id="yt:x",
        title="Set",
        uploader=None,
        duration_s=600,
        tracklist=[entry(1, 0, 90, "A", "One"), entry(2, 90, 210), entry(3, 210, 400, "B", "Two")],
        segments=[],
        stats=RecognitionStats(),
        provider="shazam",
    )
    hints = parse_community(
        "0:00 A - One\n1:30 Toman - Bounce (unreleased)\n3:30 B - Two",
        [
            {"id": "q", "parent": "root", "text": "2:00 track id?"},
            {
                "id": "r",
                "parent": "q",
                "text": "its Kolter - Wild",
                "like_count": 5,
                "author": "@d",
            },
        ],
    ).all
    text = format_result(result, hints)
    assert "↳ comunidad: Toman – Bounce (unreleased)  · descripción" in text
    assert "↳ comunidad: Kolter – Wild  · respuesta de @d, 5 likes" in text
    assert "B – Two  · " not in text  # el track siguiente ya identificado no se sugiere
    assert "Tracklist de la comunidad (sin verificar, de: descripción)" in text

"""Tests de la agregación.

Los escenarios se describen con una cadena, un símbolo por segmento (paso de 30 s):

* ``A``..``Z``: detección del track con esa letra y confianza alta (0.9)
* ``a``..``z``: detección del mismo track con confianza baja (0.3)
* ``_``: segmento sin resultado
* ``!``: segmento con error del proveedor
"""

from __future__ import annotations

import pytest

from setid.aggregate import (
    AggregationParams,
    aggregate,
    normalize_artist,
    normalize_isrc,
    normalize_title,
    same_track,
)
from setid.models import EntrySource, Match, SegmentResult, TracklistEntry

STEP = 30.0


def track(letter: str, confidence: float = 0.9, **overrides: str | None) -> Match:
    fields: dict[str, str | None] = {
        "artist": f"Artist {letter.upper()}",
        "title": f"Title {letter.upper()}",
        "label": f"Label {letter.upper()}",
        "isrc": None,
    }
    fields.update(overrides)
    return Match(
        artist=fields["artist"] or "",
        title=fields["title"] or "",
        label=fields["label"],
        isrc=fields["isrc"],
        confidence=confidence,
        provider="test",
    )


def scenario(spec: str) -> list[SegmentResult]:
    results = []
    for i, ch in enumerate(spec.replace(" ", "")):
        match = None
        error = None
        if ch.isalpha():
            match = track(ch, 0.9 if ch.isupper() else 0.3)
        elif ch == "!":
            error = "timeout"
        elif ch != "_":
            raise ValueError(ch)
        results.append(SegmentResult(index=i, start_s=i * STEP, match=match, error=error))
    return results


def summary(entries: list[TracklistEntry]) -> list[tuple[str, float]]:
    """(letra o 'ID', inicio en s) por entrada, para comparar de un vistazo."""
    out = []
    for e in entries:
        label = "ID" if e.source is EntrySource.UNKNOWN else e.title.removeprefix("Title ")
        out.append((label, e.start_s))
    return out


def run(spec: str, **params: float | int | bool) -> list[tuple[str, float]]:
    return summary(aggregate(scenario(spec), AggregationParams(**params)))  # type: ignore[arg-type]


# --- Casos básicos ------------------------------------------------------------------------


def test_empty_input() -> None:
    assert aggregate([]) == []


def test_nothing_recognized_gives_empty_tracklist() -> None:
    assert run("_ _ _ _ _") == []


def test_consecutive_segments_group_into_tracks() -> None:
    assert run("A A A B B B C C") == [("A", 0), ("B", 90), ("C", 180)]


def test_positions_are_sequential_and_end_is_last_detection_plus_window() -> None:
    entries = aggregate(scenario("A A A B B"))
    assert [e.position for e in entries] == [1, 2]
    assert entries[0].end_s == 2 * STEP + 12.0
    assert entries[0].detections == 3
    assert entries[0].label == "Label A"


def test_input_order_does_not_matter() -> None:
    results = scenario("A A _ B B")
    assert aggregate(list(reversed(results))) == aggregate(results)


# --- Huecos -------------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ["A _ A", "A _ _ A", "A ! A", "A ! _ A", "A A _ _ A A"])
def test_small_gaps_without_result_keep_the_same_track(spec: str) -> None:
    assert run(spec) == [("A", 0)]


@pytest.mark.parametrize("spec", ["A b A", "A b c A", "A b _ A", "A a A"])
def test_low_confidence_results_inside_a_gap_keep_the_same_track(spec: str) -> None:
    assert run(spec) == [("A", 0)]


def test_gap_larger_than_tolerance_splits_and_marks_unknown() -> None:
    assert run("A A _ _ _ A A") == [("A", 0), ("ID", 60), ("A", 150)]


def test_gap_tolerance_is_configurable() -> None:
    assert run("A _ _ _ A", max_gap_segments=3) == [("A", 0)]
    assert run("A _ A", max_gap_segments=0, unknown_min_segments=5) == [("A", 0), ("A", 60)]


# --- Baja confianza -----------------------------------------------------------------------


def test_isolated_low_confidence_detection_is_discarded() -> None:
    assert run("A A A _ x B B B") == [("A", 0), ("B", 150)]
    # Al descartarla, su segmento cuenta como no reconocido para el umbral de ID – ID.
    assert run("A A A _ x _ B B B") == [("A", 0), ("ID", 90), ("B", 180)]


def test_isolated_high_confidence_detection_is_kept() -> None:
    assert run("A A A _ X _ B B B", unknown_min_segments=5) == [
        ("A", 0),
        ("X", 120),
        ("B", 180),
    ]


def test_repeated_low_confidence_detections_are_kept() -> None:
    # Varias detecciones débiles que coinciden entre sí son evidencia suficiente.
    assert run("a a a") == [("A", 0)]


def test_min_confidence_threshold_is_configurable() -> None:
    assert run("_ x _", min_confidence=0.2) == [("X", 30)]
    assert run("_ X _", min_confidence=0.95) == []


def test_track_starts_at_first_detection_even_if_weak() -> None:
    assert run("_ a A A") == [("A", 30)]


# --- Repeticiones, transiciones y falsos positivos ----------------------------------------


def test_same_track_played_again_later_appears_twice() -> None:
    assert run("A A A B B B B A A") == [("A", 0), ("B", 90), ("A", 210)]


def test_same_track_again_after_unknown_stretch() -> None:
    assert run("A A _ _ _ _ A A") == [("A", 0), ("ID", 60), ("A", 180)]


def test_transition_with_alternating_detections() -> None:
    # Mezcla larga: los dos tracks suenan a la vez y el reconocimiento alterna.
    assert run("A A A B A B B B") == [("A", 0), ("B", 90)]


def test_false_positive_inside_a_track_is_dropped() -> None:
    assert run("A A X A A") == [("A", 0)]


def test_short_blend_inside_a_track_is_dropped() -> None:
    assert run("A A A X X A A A") == [("A", 0)]


# --- ID – ID ------------------------------------------------------------------------------


def test_long_unrecognized_stretch_between_tracks_is_marked_unknown() -> None:
    entries = aggregate(scenario("A A _ _ _ _ B B"))
    assert summary(entries) == [("A", 0), ("ID", 60), ("B", 180)]
    unknown = entries[1]
    assert (unknown.artist, unknown.title) == ("ID", "ID")
    assert unknown.confidence is None
    assert unknown.end_s == 5 * STEP + 12.0


def test_short_unrecognized_stretch_is_not_marked() -> None:
    assert run("A A _ _ B B") == [("A", 0), ("B", 120)]


def test_discarded_and_failed_segments_count_as_unrecognized() -> None:
    assert run("A A _ x ! _ B B") == [("A", 0), ("ID", 60), ("B", 180)]


def test_unknown_threshold_is_configurable() -> None:
    assert run("A _ _ _ B", unknown_min_segments=4) == [("A", 0), ("B", 120)]
    assert run("A _ _ _ B", unknown_min_segments=2) == [("A", 0), ("ID", 30), ("B", 120)]


def test_edges_are_not_marked_by_default() -> None:
    assert run("_ _ _ _ A A _ _ _ _") == [("A", 120)]


def test_edges_can_be_marked() -> None:
    assert run("_ _ _ _ A A _ _ _ _", mark_unknown_edges=True) == [
        ("ID", 0),
        ("A", 120),
        ("ID", 180),
    ]
    assert run("_ _ _", mark_unknown_edges=True) == [("ID", 0)]


def test_overlapping_tracks_do_not_create_unknown_between_them() -> None:
    assert run("A A B A A _ _ B B", max_gap_segments=4) == [("A", 0), ("B", 60)]


# --- Identidad de los tracks --------------------------------------------------------------


def _seg(i: int, match: Match) -> SegmentResult:
    return SegmentResult(index=i, start_s=i * STEP, match=match)


def test_same_isrc_groups_even_if_text_differs() -> None:
    results = [
        _seg(0, track("a", artist="Marco Carola", title="Space", isrc="IT-ABC-24-00001")),
        _seg(1, track("a", artist="M. Carola", title="Space (Ibiza)", isrc="itabc2400001")),
    ]
    entries = aggregate(results)
    assert len(entries) == 1
    assert entries[0].isrc == "ITABC2400001"


def test_different_isrc_but_same_text_is_same_track() -> None:
    results = [
        _seg(0, track("a", artist="Ilario Alicante", title="Vibes", isrc="ITAAA2400001")),
        _seg(1, track("a", artist="Ilario Alicante", title="Vibes", isrc="ITBBB2400002")),
    ]
    assert len(aggregate(results)) == 1


def test_isrc_missing_in_some_detections_uses_text() -> None:
    results = [
        _seg(0, track("a", artist="Miguelle & Tons", title="Groove", isrc=None)),
        _seg(1, track("a", artist="Tons, Miguelle", title="Groove (Original Mix)", isrc=None)),
        _seg(2, track("a", artist="Miguelle & Tons", title="Groove", isrc="GBXXX2400001")),
    ]
    entries = aggregate(results)
    assert len(entries) == 1
    assert entries[0].isrc == "GBXXX2400001"


def test_metadata_from_best_detection_and_label_filled_from_others() -> None:
    results = [
        _seg(0, track("a", confidence=0.6, artist="Artist", title="Song", label="Music On")),
        _seg(1, track("a", confidence=0.95, artist="ARTIST", title="Song", label=None)),
    ]
    [entry] = aggregate(results)
    assert entry.artist == "ARTIST"
    assert entry.label == "Music On"
    assert entry.confidence == 0.95


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Track (Original Mix)", "Track"),
        ("Track (Extended Mix)", "track"),
        ("Track - Original Mix", "Track"),
        ("Track (Radio Edit)", "TRACK"),
        ("Café del Mar", "Cafe Del Mar"),
        ("Track feat. Someone", "Track"),
        ("Track (feat. Someone) [Extended Mix]", "Track"),
        ("Track!!", "track"),
    ],
)
def test_title_normalization_equivalences(a: str, b: str) -> None:
    assert normalize_title(a) == normalize_title(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Track (Ilario Alicante Remix)", "Track"),
        ("Track (Dub Mix)", "Track"),
        ("Track Part 2", "Track"),
    ],
)
def test_remixes_and_versions_are_different_tracks(a: str, b: str) -> None:
    assert normalize_title(a) != normalize_title(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Miguelle & Tons", "Tons & Miguelle"),
        ("Miguelle, Tons", "Miguelle & Tons"),
        ("Miguelle and Tons", "Miguelle x Tons"),
        ("Marco Carola feat. Someone", "Marco Carola"),
        ("Ilário Alicante", "ilario alicante"),
    ],
)
def test_artist_normalization_equivalences(a: str, b: str) -> None:
    assert normalize_artist(a) == normalize_artist(b)


def test_same_track_requires_matching_artist() -> None:
    assert not same_track(
        track("a", artist="Artist One", title="Song"), track("a", artist="Other", title="Song")
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("US-RC1-76-07839", "USRC17607839"), ("usrc17607839", "USRC17607839"), ("bad", None)],
)
def test_isrc_normalization(raw: str, expected: str | None) -> None:
    assert normalize_isrc(raw) == expected


# --- Escenario realista -------------------------------------------------------------------


def test_realistic_hour_long_set() -> None:
    spec = (
        "_ _ A A A A a A A A"  # intro sin reconocer + track A con un segmento débil
        " A B A B B B B _ B B"  # transición larga A→B y un hueco dentro de B
        " B _ _ _ _ _ C C C C"  # tramo unreleased (ID – ID) y C
        " C x C C ! C C D D D"  # falso positivo débil y un error dentro de C
        " D D D D D A A A A A"  # vuelve A más tarde
        " A A E E E E E E E E"
    )
    assert run(spec) == [
        ("A", 60),
        ("B", 330),
        ("ID", 630),
        ("C", 780),
        ("D", 1110),
        ("A", 1350),
        ("E", 1560),
    ]

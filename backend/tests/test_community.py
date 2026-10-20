from __future__ import annotations

from typing import Any

import pytest

from setid.community import (
    HintKind,
    ParsedTrack,
    parse_community,
    parse_timestamp,
    split_track,
    suggestions_for,
    track_key,
    tracklist_from_text,
)


def comment(
    text: str,
    id: str = "c1",
    parent: str = "root",
    likes: int = 0,
    author: str = "@fan",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": id,
        "parent": parent,
        "text": text,
        "like_count": likes,
        "author": author,
        **extra,
    }


# --- Piezas sueltas -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "seconds"), [("0:00", 0), ("12:30", 750), ("1:02:10", 3730), ("02:05", 125)]
)
def test_parse_timestamp(text: str, seconds: float) -> None:
    assert parse_timestamp(text) == seconds


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Marco Carola - Space", ("Marco Carola", "Space", False)),
        ("Marco Carola – Space 🔥🔥", ("Marco Carola", "Space", False)),
        (
            "Miguelle & Tons — Groove (Extended Mix)",
            ("Miguelle & Tons", "Groove (Extended Mix)", False),
        ),
        ("Jay-Z - Song", ("Jay-Z", "Song", False)),
        ("Ilario Alicante - Vibes (Unreleased)", ("Ilario Alicante", "Vibes", True)),
        ("Ilario Alicante - Vibes [forthcoming Cocoon]", ("Ilario Alicante", "Vibes", True)),
        ("Toman - ID", ("Toman", "ID", True)),
        ("ID - ID", ("ID", "ID", True)),
        ("Artist - Title sin publicar todavía", ("Artist", "Title sin publicar todavía", True)),
        ('"Artist - Title"', ("Artist", "Title", False)),
    ],
)
def test_split_track(text: str, expected: tuple[str, str, bool]) -> None:
    assert split_track(text) == ParsedTrack(*expected)


@pytest.mark.parametrize("text", ["", "🔥🔥🔥", "what a drop", "this part - 🔥", "-", "a" * 400])
def test_split_track_rejects_noise(text: str) -> None:
    assert split_track(text) is None


DESCRIPTION = """Live at LOAD, 25.09.2026

Tracklist:
00:00 Joey Harmless - So Shady
[06:30] Cris Ocana – Brasuca Vibes (Extended Mix)
09:30 ID - ID
1:02:10 Bassel Darwish - Lami

Follow us on instagram!"""


def test_tracklist_from_description() -> None:
    tracks = tracklist_from_text(DESCRIPTION)
    assert [(t[0], t[1].artist, t[1].title) for t in tracks] == [
        (0, "Joey Harmless", "So Shady"),
        (390, "Cris Ocana", "Brasuca Vibes (Extended Mix)"),
        (570, "ID", "ID"),
        (3730, "Bassel Darwish", "Lami"),
    ]


def test_numbered_tracklist_without_timestamps() -> None:
    tracks = tracklist_from_text("1. A - One\n2. B - Two\n3) C - Three")
    assert [(t[0], t[1].title) for t in tracks] == [(None, "One"), (None, "Two"), (None, "Three")]


def test_too_few_lines_is_not_a_tracklist() -> None:
    assert tracklist_from_text("00:00 Intro - Something\n05:00 A - B") == []


# --- Comentarios --------------------------------------------------------------------------


def test_description_tracklist_wins() -> None:
    result = parse_community(
        DESCRIPTION, [comment("0:00 X - Y\n1:00 Z - W\n2:00 Q - R", likes=900)]
    )
    assert result.tracklist_origin == "descripción"
    assert result.tracklist[0].kind is HintKind.TRACKLIST
    assert result.tracklist[2].is_id


def test_pinned_comment_tracklist_beats_popular_one() -> None:
    popular = comment("0:00 X - Y\n1:00 Z - W\n2:00 Q - R", id="a", likes=900)
    pinned = comment("0:00 A - B\n1:00 C - D\n2:00 E - F", id="b", likes=3, is_pinned=True)
    result = parse_community(None, [popular, pinned])
    assert result.tracklist_origin == "comentario fijado"
    assert result.tracklist[0].artist == "A"


def test_single_timestamped_mention() -> None:
    result = parse_community(None, [comment("45:10 Toman - Bounce 🔥🔥", likes=12)])
    [hint] = result.hints
    assert (hint.kind, hint.start_s, hint.artist, hint.title) == (
        HintKind.COMMENT,
        2710,
        "Toman",
        "Bounce",
    )
    assert hint.likes == 12
    assert hint.origin == "comentario de @fan"


@pytest.mark.parametrize(
    "question",
    [
        "23:15 track id?",
        "Track ID at 23:15 please 🙏",
        "what's the song at 23:15??",
        "23:15 ID?",
        "alguien sabe qué tema es el del 23:15?",
        "23:15 cómo se llama este temazo",
    ],
)
@pytest.mark.parametrize(
    "answer",
    [
        "It's Daniel Insogna - Hold On",
        "@fan Daniel Insogna - Hold On",
        "es Daniel Insogna – Hold On (unreleased)",
        "i think it's Daniel Insogna - Hold On",
    ],
)
def test_replies_to_track_id_questions(question: str, answer: str) -> None:
    result = parse_community(
        None,
        [comment(question, id="q"), comment(answer, id="r", parent="q", author="@digger", likes=4)],
    )
    [hint] = result.hints
    assert hint.kind is HintKind.REPLY
    assert hint.start_s == 1395
    assert (hint.artist, hint.title) == ("Daniel Insogna", "Hold On")
    assert hint.origin == "respuesta de @digger"


def test_reply_with_its_own_timestamp_uses_it() -> None:
    result = parse_community(
        None, [comment("track id?", id="q"), comment("23:40 A - B", id="r", parent="q")]
    )
    assert result.hints[0].start_s == 1420


def test_question_without_time_and_answer_without_time_is_ignored() -> None:
    result = parse_community(
        None, [comment("track id?", id="q"), comment("A - B", id="r", parent="q")]
    )
    assert result.hints == []


def test_replies_to_non_questions_are_ignored() -> None:
    result = parse_community(
        None, [comment("great set", id="q"), comment("A - B", id="r", parent="q")]
    )
    assert result.hints == []


def test_questions_are_not_hints_themselves() -> None:
    assert parse_community(None, [comment("23:15 Is this Artist - Title?")]).hints == []


def test_duplicates_keep_the_most_liked() -> None:
    result = parse_community(
        None,
        [
            comment("23:15 Toman - Bounce", id="a", likes=2),
            comment("23:40 toman - bounce!!", id="b", likes=30),
        ],
    )
    assert len(result.hints) == 1
    assert result.hints[0].likes == 30


def test_garbage_comments_are_safe() -> None:
    weird: list[Any] = [
        None,
        3,
        {"text": None},
        {"text": ""},
        {"text": "x" * 10_000},
        {"text": "1:00", "like_count": -5},
    ]
    assert parse_community("", weird).all == []


# --- Sugerencias --------------------------------------------------------------------------


def test_suggestions_for_unknown_stretch() -> None:
    result = parse_community(
        DESCRIPTION,
        [
            comment("23:15 track id?", id="q"),
            comment("It's Daniel Insogna - Hold On", id="r", parent="q", likes=9),
            comment("9:50 Toman - Bounce", id="m", likes=1),
            comment("40:00 Far - Away", id="x"),
        ],
    )
    # Tramo ID – ID de 9:30 a 11:30
    near = suggestions_for(570, 690, result.all)
    assert [(h.artist, h.title) for h in near] == [("Toman", "Bounce"), ("ID", "ID")]
    assert near[-1].is_id  # el «ID – ID» del tracklist va al final: no da nombre

    later = suggestions_for(1380, 1500, result.all)
    assert [(h.artist, h.title) for h in later] == [("Daniel Insogna", "Hold On")]
    assert suggestions_for(3000, 3100, result.all) == []


def test_suggestions_skip_tracks_already_identified() -> None:
    result = parse_community("00:00 A - One\n01:30 ID - ID\n03:30 Sofia Varela - Groove Theory", [])
    known = frozenset({track_key("Sofia Varela & K-Loop", "Groove Theory")})
    names = [(h.artist, h.title) for h in suggestions_for(90, 210, result.all, known=known)]
    assert names == [("ID", "ID")]
    # Mismo título pero otro artista: no es el mismo track, se sugiere.
    other = frozenset({track_key("Someone Else", "Groove Theory")})
    assert ("Sofia Varela", "Groove Theory") in [
        (h.artist, h.title) for h in suggestions_for(90, 210, result.all, known=other)
    ]


# --- Casos reales (comentario de un set de Franky Rizardo en Music On) -------------------


@pytest.mark.parametrize(
    ("text", "artist", "title", "note", "unreleased"),
    [
        (
            "James Wyler - Mongo Tango/ W  Max Dean & Luke Dean - Gets Like That (Acapella)",
            "James Wyler", "Mongo Tango", "Max Dean & Luke Dean - Gets Like That (Acapella)", False,
        ),
        (
            "Tatan Bilbao - Disco Sound /W E samba e samba Acappella - Junior Jack (unreleased)",
            "Tatan Bilbao", "Disco Sound", "E samba e samba Acappella - Junior Jack", True,
        ),
        (
            "Simes - Funky Feeling /W i never knew love like this before acapella",
            "Simes", "Funky Feeling", "i never knew love like this before acapella", False,
        ),
        ("A - Track w/ B - Vocal", "A", "Track", "B - Vocal", False),
        (
            "Kiko - Mrs (with Someone - Acapella)",
            "Kiko", "Mrs (with Someone - Acapella)", None, False,
        ),
    ],
)  # fmt: skip
def test_mashups_keep_the_main_track_and_note_the_acapella(
    text: str, artist: str, title: str, note: str | None, unreleased: bool
) -> None:
    track = split_track(text)
    assert track is not None
    assert (track.artist, track.title, track.note, track.unreleased) == (
        artist,
        title,
        note,
        unreleased,
    )


@pytest.mark.parametrize(
    "text",
    [
        "Everything but the Girl - Missing (Franky Rizardo Remix) (NOT RELEASING)",
        "Artist - Track (never released)",
        "Artist - Track [won't be released]",
        "Artist - Track (no va a salir)",
    ],
)
def test_more_unreleased_wordings(text: str) -> None:
    track = split_track(text)
    assert track is not None
    assert track.unreleased
    assert "releas" not in track.title.lower() and "salir" not in track.title


def test_mashup_note_is_kept_in_hints() -> None:
    result = parse_community("0:00 A - One\n1:00 B - Two /W C - Acapella\n2:00 D - Three", [])
    assert result.tracklist[1].note == "C - Acapella"
    assert result.tracklist[1].title == "Two"

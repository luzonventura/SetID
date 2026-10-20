"""Tests de integración de la app: base de datos real, ffmpeg real, FakeProvider y la API
del puente tal y como la llamará la interfaz."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session

from setid.app.bridge import Api
from setid.app.context import AppContext, create_app
from setid.audio.demo import DemoPart, generate_demo_set
from setid.config import Settings
from setid.db.tables import Job, JobStatus
from setid.models import Match, SourceType
from setid.proc import ProcessError
from setid.providers.base import PermanentProviderError, RecognitionProvider
from setid.providers.fake import FakeProvider
from setid.settings_store import MemorySecrets
from setid.sources import ytdlp
from setid.sources.url import CanonicalSource
from setid.sources.ytdlp import CommunityData, SourceMetadata

pytestmark = pytest.mark.ffmpeg

VID = "dQw4w9WgXcQ"
SHORT_SET = (
    DemoPart(90, 330.0),
    DemoPart(120, None),
    DemoPart(90, 440.0),
    DemoPart(60, 330.0),
)
EXPECTED = [("Night Shift", 0.0), ("ID", 90.0), ("Groove Theory", 210.0), ("Night Shift", 300.0)]
TIMEOUT = 30


@pytest.fixture(scope="module")
def demo_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("demo") / "short-set.wav"
    return generate_demo_set(path, SHORT_SET)


class Events:
    """Recoge los eventos del gestor y permite esperar a uno concreto."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self._cond = threading.Condition()

    def __call__(self, event: dict[str, Any]) -> None:
        with self._cond:
            self.items.append(event)
            self._cond.notify_all()

    def wait(
        self, predicate: Callable[[dict[str, Any]], bool], timeout: float = TIMEOUT
    ) -> dict[str, Any]:
        with self._cond:
            found: list[dict[str, Any]] = []

            def check() -> bool:
                found[:] = [e for e in self.items if predicate(e)]
                return bool(found)

            if not self._cond.wait_for(check, timeout):
                raise AssertionError(f"no llegó el evento esperado; eventos: {self.items[-5:]}")
            return found[0]

    def wait_status(self, job_id: int, *statuses: JobStatus) -> dict[str, Any]:
        wanted = {s.value for s in statuses}
        return self.wait(
            lambda e: (
                e["type"] == "job" and e["job"]["id"] == job_id and e["job"]["status"] in wanted
            )
        )["job"]

    def statuses(self, job_id: int) -> list[str]:
        return [
            e["job"]["status"]
            for e in self.items
            if e["type"] == "job" and e["job"]["id"] == job_id
        ]


def make_app(
    data_dir: Path, provider_factory: Callable[[Settings], RecognitionProvider] | None = None
) -> AppContext:
    app = create_app(
        data_dir,
        secrets=MemorySecrets(),
        provider_factory=provider_factory or (lambda _s: FakeProvider()),
        log_to_file=False,
    )
    app.store.update({"provider": "fake"})
    return app


@pytest.fixture
def app(tmp_path: Path) -> Iterator[AppContext]:
    context = make_app(tmp_path / "data")
    yield context
    context.close()


@pytest.fixture
def events(app: AppContext) -> Events:
    collector = Events()
    app.manager.subscribe(collector)
    return collector


def ok(response: dict[str, Any]) -> Any:
    assert response["ok"], response
    return response["data"]


def summary(tracklist: list[dict[str, Any]]) -> list[tuple[str, float]]:
    return [("ID" if e["source"] == "unknown" else e["title"], e["start_s"]) for e in tracklist]


def temp_files(app: AppContext) -> list[Path]:
    root = app.store.load().temp_root
    return list(root.rglob("*")) if root.exists() else []


# --- Flujo completo -----------------------------------------------------------------------


def test_file_job_end_to_end(app: AppContext, events: Events, demo_file: Path) -> None:
    job = ok(app.api.create_job_from_file(str(demo_file)))
    assert job["status"] == "queued"
    final = events.wait_status(job["id"], JobStatus.DONE, JobStatus.FAILED)
    assert final["status"] == "done", final
    assert final["queries_used"] == 12
    assert final["cached"] is False
    assert final["duration_s"] == pytest.approx(360)

    seen = events.statuses(job["id"])
    for status in ("downloading", "analyzing", "aggregating", "done"):
        assert status in seen
    live = [e for e in events.items if e["type"] == "tracklist" and e["live"]]
    assert live, "debería emitir el tracklist provisional mientras analiza"

    detail = ok(app.api.get_job(job["id"]))
    assert summary(detail["tracklist"]) == EXPECTED
    assert detail["live"] is False
    first = detail["tracklist"][0]
    assert first["search"]["beatport"].startswith("https://www.beatport.com/search?q=")
    assert first["timestamp_url"] is None  # archivo local: no hay a dónde saltar
    assert temp_files(app) == []
    assert demo_file.exists()


def test_history_lists_newest_first(app: AppContext, events: Events, demo_file: Path) -> None:
    first = ok(app.api.create_job_from_file(str(demo_file)))
    events.wait_status(first["id"], JobStatus.DONE)
    second = ok(app.api.create_job_from_file(str(demo_file)))
    events.wait_status(second["id"], JobStatus.DONE)
    history = ok(app.api.list_jobs())
    assert [j["id"] for j in history] == [second["id"], first["id"]]


# --- Caché --------------------------------------------------------------------------------


def test_same_file_uses_cache_unless_forced(
    app: AppContext, events: Events, demo_file: Path
) -> None:
    first = ok(app.api.create_job_from_file(str(demo_file)))
    events.wait_status(first["id"], JobStatus.DONE)

    # Copia con otro nombre: misma huella de contenido, mismo resultado.
    copy = demo_file.with_name("otro-nombre.wav")
    shutil.copy(demo_file, copy)
    cached = ok(app.api.create_job_from_file(str(copy)))
    done = events.wait_status(cached["id"], JobStatus.DONE)
    assert done["cached"] is True
    assert done["queries_used"] == 0
    assert summary(ok(app.api.get_job(cached["id"]))["tracklist"]) == EXPECTED

    forced = ok(app.api.create_job_from_file(str(demo_file), True))
    done = events.wait_status(forced["id"], JobStatus.DONE)
    assert done["cached"] is False
    assert done["queries_used"] == 12


@pytest.fixture
def fake_youtube(monkeypatch: pytest.MonkeyPatch, demo_file: Path) -> list[str]:
    """Sustituye yt-dlp: metadatos fijos y una «descarga» que copia el set de demo."""
    downloads: list[str] = []

    def fetch_metadata(
        source: CanonicalSource, *, max_duration_s: float, timeout: float
    ) -> SourceMetadata:
        return SourceMetadata(
            id=source.id, title="Demo Live @ Club", uploader="Demo", duration_s=360
        )

    def download_audio(
        source: CanonicalSource, workdir: Path, *, max_bytes: int, timeout: float
    ) -> Path:
        downloads.append(source.url)
        target = workdir / "source.webm"
        shutil.copy(demo_file, target)
        return target

    def fetch_community(
        source: CanonicalSource, *, max_comments: int, timeout: float
    ) -> CommunityData:
        return CommunityData(description="Grabado en directo.", comments=[])

    monkeypatch.setattr(ytdlp, "fetch_metadata", fetch_metadata)
    monkeypatch.setattr(ytdlp, "download_audio", download_audio)
    monkeypatch.setattr(ytdlp, "fetch_community", fetch_community)
    return downloads


COMMENTS: list[dict[str, Any]] = [
    # El tramo ID – ID del set de demo va de 1:30 a 3:30.
    {
        "id": "q",
        "parent": "root",
        "text": "2:10 track id?? 🔥",
        "like_count": 40,
        "author": "@raver",
    },
    {
        "id": "r",
        "parent": "q",
        "text": "It's Toman - Bounce (unreleased)",
        "like_count": 25,
        "author": "@digger",
    },
    {
        "id": "m",
        "parent": "root",
        "text": "5:10 Lumen Grid - Night Shift what a tune",
        "like_count": 3,
        "author": "@x",
    },
]


def test_community_suggestions_fill_unknown_stretches(
    app: AppContext, events: Events, fake_youtube: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ytdlp,
        "fetch_community",
        lambda source, **_: CommunityData(
            description=(
                "00:00 Lumen Grid - Night Shift\n01:30 ID - ID\n03:30 Sofia Varela - Groove Theory"
            ),
            comments=COMMENTS,
        ),
    )
    job = ok(app.api.create_job(f"https://youtu.be/{VID}"))
    events.wait_status(job["id"], JobStatus.DONE)
    community_event = events.wait(lambda e: e["type"] == "community" and e["job_id"] == job["id"])
    assert community_event["community"]["tracklist_origin"] == "descripción"

    detail = ok(app.api.get_job(job["id"]))
    unknown = detail["tracklist"][1]
    assert unknown["source"] == "unknown"
    names = [(s["artist"], s["title"]) for s in unknown["suggestions"]]
    assert names[0] == ("Toman", "Bounce")  # la respuesta a «track id?» da nombre
    first = unknown["suggestions"][0]
    assert first["unreleased"] is True
    assert first["origin"] == "respuesta de @digger"
    assert first["timestamp_url"] == f"https://www.youtube.com/watch?v={VID}&t=130s"
    assert ("ID", "ID") in names  # el tracklist de la descripción también lo marca como ID
    # Las pistas identificadas por huella no reciben sugerencias.
    assert detail["tracklist"][0]["suggestions"] == []

    community = detail["community"]
    assert [h["title"] for h in community["tracklist"]] == ["Night Shift", "ID", "Groove Theory"]
    assert {h["kind"] for h in community["mentions"]} == {"reply", "comment"}

    # Una copia de caché conserva las sugerencias sin volver a leer comentarios.
    again = ok(app.api.create_job(f"https://www.youtube.com/watch?v={VID}"))
    events.wait_status(again["id"], JobStatus.DONE)
    cached = ok(app.api.get_job(again["id"]))
    assert cached["cached"] is True
    assert cached["tracklist"][1]["suggestions"][0]["title"] == "Bounce"


def test_comment_errors_do_not_fail_the_job(
    app: AppContext, events: Events, fake_youtube: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(source: CanonicalSource, **_: Any) -> CommunityData:
        raise ProcessError("yt-dlp", "terminó con código 1")

    monkeypatch.setattr(ytdlp, "fetch_community", broken)
    job = ok(app.api.create_job(f"https://youtu.be/{VID}"))
    assert events.wait_status(job["id"], JobStatus.DONE, JobStatus.FAILED)["status"] == "done"
    assert ok(app.api.get_job(job["id"]))["community"]["mentions"] == []


def test_community_can_be_disabled(
    app: AppContext, events: Events, fake_youtube: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ytdlp, "fetch_community", lambda source, **_: calls.append(source.url) or CommunityData()
    )
    ok(app.api.update_settings({"community_enabled": False}))
    job = ok(app.api.create_job(f"https://youtu.be/{VID}"))
    events.wait_status(job["id"], JobStatus.DONE)
    assert calls == []


def test_url_job_and_cache_across_url_variants(
    app: AppContext, events: Events, fake_youtube: list[str]
) -> None:
    job = ok(app.api.create_job(f"https://youtu.be/{VID}?si=abc"))
    assert job["source_type"] == "youtube"
    assert job["canonical_id"] == f"yt:{VID}"
    done = events.wait_status(job["id"], JobStatus.DONE, JobStatus.FAILED)
    assert done["status"] == "done", done
    assert done["title"] == "Demo Live @ Club"

    detail = ok(app.api.get_job(job["id"]))
    third = detail["tracklist"][2]
    assert third["timestamp_url"] == f"https://www.youtube.com/watch?v={VID}&t=210s"

    again = ok(app.api.create_job(f"https://m.youtube.com/watch?v={VID}&list=PL1"))
    assert events.wait_status(again["id"], JobStatus.DONE)["cached"] is True
    assert fake_youtube == [f"https://www.youtube.com/watch?v={VID}"]  # una sola descarga
    assert temp_files(app) == []


# --- Errores ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/watch?v=x",
        "javascript:alert(1)",
        "",
        "https://youtube.com/playlist?list=P",
    ],
)
def test_invalid_urls_are_rejected_without_creating_jobs(app: AppContext, url: str) -> None:
    response = app.api.create_job(url)
    assert response["ok"] is False
    assert response["error"]
    assert ok(app.api.list_jobs()) == []


def test_bridge_validates_argument_types(app: AppContext) -> None:
    assert app.api.create_job(123)["ok"] is False
    assert app.api.create_job("https://youtu.be/dQw4w9WgXcQ", "yes")["ok"] is False
    assert app.api.get_job("1")["ok"] is False
    assert app.api.get_job(True)["ok"] is False
    assert app.api.get_job(999)["ok"] is False
    assert app.api.list_jobs("all")["ok"] is False
    assert app.api.export_job(1, "exe")["ok"] is False


def test_non_audio_file_fails_with_clear_message(
    app: AppContext, events: Events, tmp_path: Path
) -> None:
    fake = tmp_path / "set.mp3"
    fake.write_text("no soy audio")
    job = ok(app.api.create_job_from_file(str(fake)))
    failed = events.wait_status(job["id"], JobStatus.FAILED)
    assert "audio" in failed["error"]
    assert temp_files(app) == []


def test_missing_file_is_rejected(app: AppContext, tmp_path: Path) -> None:
    response = app.api.create_job_from_file(str(tmp_path / "no-existe.wav"))
    assert response == {"ok": False, "error": "El archivo no existe."}


def test_provider_permanent_error_fails_job(tmp_path: Path, demo_file: Path) -> None:
    class BadKey(FakeProvider):
        async def identify(self, segment: bytes) -> Match | None:
            raise PermanentProviderError("acrcloud: credenciales rechazadas (401)")

    app = make_app(tmp_path / "data", lambda _s: BadKey())
    events = Events()
    app.manager.subscribe(events)
    try:
        job = ok(app.api.create_job_from_file(str(demo_file)))
        failed = events.wait_status(job["id"], JobStatus.FAILED)
        assert failed["error"] == "acrcloud: credenciales rechazadas (401)"
        assert temp_files(app) == []
    finally:
        app.close()


# --- Presupuesto --------------------------------------------------------------------------


def test_job_waits_in_queue_until_budget_allows(
    app: AppContext, events: Events, demo_file: Path
) -> None:
    ok(app.api.update_settings({"daily_query_budget": 5}))
    job = ok(app.api.create_job_from_file(str(demo_file)))
    waiting = events.wait(
        lambda e: (
            e["type"] == "job"
            and e["job"]["id"] == job["id"]
            and e["job"]["status"] == "queued"
            and "presupuesto" in (e["job"]["message"] or "")
        )
    )["job"]
    assert "12 consultas" in waiting["message"]
    assert ok(app.api.get_budget())["used_today"] == 0

    ok(app.api.update_settings({"daily_query_budget": 100}))  # despierta al trabajo
    done = events.wait_status(job["id"], JobStatus.DONE)
    assert done["queries_used"] == 12
    budget = ok(app.api.get_budget())
    assert budget["used_today"] == 12
    assert budget["remaining"] == 88


# --- Cancelar y borrar --------------------------------------------------------------------


def test_cancel_running_job_cleans_up(tmp_path: Path, demo_file: Path) -> None:
    app = make_app(tmp_path / "data", lambda _s: FakeProvider(latency_s=0.3))
    events = Events()
    app.manager.subscribe(events)
    try:
        job = ok(app.api.create_job_from_file(str(demo_file)))
        events.wait_status(job["id"], JobStatus.ANALYZING)
        cancelled = ok(app.api.cancel_job(job["id"]))
        assert cancelled["status"] == "cancelled"
        assert temp_files(app) == []

        # El worker sigue vivo para el siguiente trabajo.
        app.store.update({"provider": "fake"})
        next_job = ok(app.api.create_job_from_file(str(demo_file), True))
        assert (
            events.wait_status(next_job["id"], JobStatus.DONE, JobStatus.FAILED)["status"] == "done"
        )
    finally:
        app.close()


def test_cancel_queued_job(tmp_path: Path, demo_file: Path) -> None:
    app = make_app(tmp_path / "data", lambda _s: FakeProvider(latency_s=0.3))
    events = Events()
    app.manager.subscribe(events)
    try:
        first = ok(app.api.create_job_from_file(str(demo_file)))
        second = ok(app.api.create_job_from_file(str(demo_file), True))
        events.wait_status(first["id"], JobStatus.ANALYZING)
        assert ok(app.api.cancel_job(second["id"]))["status"] == "cancelled"
        ok(app.api.cancel_job(first["id"]))
        assert ok(app.api.get_job(second["id"]))["status"] == "cancelled"
    finally:
        app.close()


def test_delete_job_removes_entries(app: AppContext, events: Events, demo_file: Path) -> None:
    job = ok(app.api.create_job_from_file(str(demo_file)))
    events.wait_status(job["id"], JobStatus.DONE)
    assert ok(app.api.delete_job(job["id"])) is None
    events.wait(lambda e: e["type"] == "job_deleted" and e["job_id"] == job["id"])
    assert app.api.get_job(job["id"])["ok"] is False
    assert app.manager.repo.entries(job["id"]) == []


# --- Reinicio -----------------------------------------------------------------------------


def test_restart_marks_interrupted_and_resumes_queued(tmp_path: Path, demo_file: Path) -> None:
    data = tmp_path / "data"
    app = make_app(data)
    app.close()
    with Session(app.engine) as session:
        session.add(
            Job(
                source_type=SourceType.UPLOAD,
                source=str(demo_file),
                provider="fake",
                status=JobStatus.ANALYZING,
            )
        )
        session.add(Job(source_type=SourceType.UPLOAD, source=str(demo_file), provider="fake"))
        session.commit()

    events = Events()
    restarted = make_app(data)
    restarted.manager.subscribe(events)
    try:
        interrupted, queued = sorted(ok(restarted.api.list_jobs()), key=lambda j: j["id"])
        assert interrupted["status"] == "failed"
        assert "Interrumpido" in interrupted["error"]
        # El segundo seguía en cola al cerrar: se retoma solo al arrancar.
        events.wait_status(queued["id"], JobStatus.DONE)
    finally:
        restarted.close()


# --- Exportación --------------------------------------------------------------------------


def test_exports(app: AppContext, events: Events, demo_file: Path) -> None:
    job = ok(app.api.create_job_from_file(str(demo_file)))
    events.wait_status(job["id"], JobStatus.DONE)

    txt = ok(app.api.export_job(job["id"], "txt"))
    assert txt["filename"] == "short-set.txt"
    assert txt["content"].splitlines()[2:] == [
        "00:00 Lumen Grid – Night Shift [Demo Records]",
        "01:30 ID – ID",
        "03:30 Sofia Varela & K-Loop – Groove Theory [Fake Tones]",
        "05:00 Lumen Grid – Night Shift [Demo Records]",
    ]
    csv = ok(app.api.export_job(job["id"], "csv"))["content"].splitlines()
    assert csv[0].startswith("position,start,start_s,artist,title")
    assert len(csv) == 5
    m3u = ok(app.api.export_job(job["id"], "m3u"))["content"]
    assert m3u.startswith("#EXTM3U")
    assert m3u.count("#EXTINF") == 3  # los ID – ID no van en la lista
    data = ok(app.api.export_job(job["id"], "json"))
    assert '"provider": "fake"' in data["content"]


def test_save_export_uses_native_dialog(
    app: AppContext, events: Events, demo_file: Path, tmp_path: Path
) -> None:
    saved: dict[str, str] = {}

    class Window:
        def pick_audio_file(self) -> str | None:
            return str(demo_file)

        def save_file(self, suggested_name: str, content: str) -> str | None:
            saved[suggested_name] = content
            return str(tmp_path / suggested_name)

    api = Api(app.manager, app.store, Window())
    job = ok(api.create_job_from_file())  # sin ruta: abre el diálogo
    events.wait_status(job["id"], JobStatus.DONE)
    assert ok(api.save_export(job["id"], "csv"))["path"].endswith("short-set.csv")
    assert "short-set.csv" in saved


# --- Ajustes y seguridad del puente -------------------------------------------------------


def test_settings_never_expose_secret_values(app: AppContext) -> None:
    assert ok(app.api.get_settings())["secrets"]["audd_api_token"] is False
    secrets = ok(app.api.set_secret("audd_api_token", "super-secreto-123"))
    assert secrets["audd_api_token"] is True
    view = ok(app.api.get_settings())
    assert "super-secreto-123" not in repr(view)
    assert app.store.load().audd_api_token is not None
    ok(app.api.set_secret("audd_api_token", None))
    assert ok(app.api.get_settings())["secrets"]["audd_api_token"] is False


def test_settings_are_validated(app: AppContext) -> None:
    assert app.api.update_settings({"window_s": -1})["ok"] is False
    assert app.api.update_settings({"provider": "spotify"})["ok"] is False
    assert app.api.update_settings({"data_dir": "C:/Windows"})["ok"] is False
    assert app.api.set_secret("data_dir", "x")["ok"] is False
    view = ok(app.api.update_settings({"step_s": 60, "provider": "shazam"}))
    assert view["values"]["step_s"] == 60
    assert view["effective_limits"] == {"concurrency": 1, "min_interval_s": 1.5}
    assert app.store.load().step_s == 60  # persistido en settings.json


def test_open_external_only_allows_whitelisted_https(app: AppContext) -> None:
    opened: list[str] = []
    api = Api(app.manager, app.store, open_url=opened.append)
    assert ok(api.open_external("https://www.beatport.com/search?q=x")) is None
    for bad in [
        "http://www.beatport.com/",
        "https://evil.com/",
        "file:///C:/Windows/System32/calc.exe",
        "javascript:alert(1)",
        "https://www.beatport.com.evil.com/",
    ]:
        assert api.open_external(bad)["ok"] is False
    assert opened == ["https://www.beatport.com/search?q=x"]


def test_bridge_exposes_only_methods(app: AppContext) -> None:
    # pywebview expone también los atributos públicos (y sus métodos) a JavaScript.
    public = {name: getattr(app.api, name) for name in dir(app.api) if not name.startswith("_")}
    assert public
    assert all(callable(value) and hasattr(value, "__wrapped__") for value in public.values())

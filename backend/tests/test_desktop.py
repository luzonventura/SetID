"""Tests de la capa de escritorio sin abrir ninguna ventana."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Any

import pytest

from setid.app import desktop
from setid.app.desktop import DesktopWindow, event_script, handle_drop
from setid.jobs.manager import JobError
from setid.jobs.views import JobView


class FakeWindow:
    def __init__(self, dialog_result: Any = None) -> None:
        self.dialog_result = dialog_result
        self.dialogs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.scripts: list[str] = []

    def create_file_dialog(self, *args: Any, **kwargs: Any) -> Any:
        self.dialogs.append((args, kwargs))
        return self.dialog_result

    def run_js(self, script: str) -> Any:
        self.scripts.append(script)


def test_event_script_cannot_break_out_of_the_payload() -> None:
    evil = {"type": "job", "job": {"title": '"}));alert(1);//</script>\u2028'}}
    script = event_script(evil)
    assert script.startswith('window.dispatchEvent(new CustomEvent("setid:event", {detail: ')
    payload = script.removeprefix(
        'window.dispatchEvent(new CustomEvent("setid:event", {detail: '
    ).removesuffix("}))")
    assert json.loads(payload) == evil
    assert "\u2028" not in script  # ensure_ascii: sin separadores de línea crudos


def test_pick_audio_file_returns_first_path_or_none() -> None:
    window = FakeWindow(("C:/sets/a.wav",))
    assert DesktopWindow(window, 10, 30).pick_audio_file() == "C:/sets/a.wav"
    assert window.dialogs[0][0] == (10,)
    assert "file_types" in window.dialogs[0][1]
    assert DesktopWindow(FakeWindow(None), 10, 30).pick_audio_file() is None


def test_save_file_writes_where_the_user_chose(tmp_path: Path) -> None:
    target = tmp_path / "set.csv"
    window = FakeWindow(str(target))
    saved = DesktopWindow(window, 10, 30).save_file("set.csv", "a,b\n1,2\n")
    assert saved == str(target)
    assert target.read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert window.dialogs[0][1]["save_filename"] == "set.csv"
    assert DesktopWindow(FakeWindow(None), 10, 30).save_file("x", "y") is None


def test_emit_never_raises() -> None:
    class Closing(FakeWindow):
        def run_js(self, script: str) -> Any:
            raise RuntimeError("window closed")

    DesktopWindow(Closing(), 10, 30).emit({"type": "job"})


class FakeManager:
    def __init__(self, error: str | None = None) -> None:
        self.submitted: list[str] = []
        self.error = error

    def submit_file(self, path: str, *, force: bool = False) -> JobView:
        if self.error:
            raise JobError(self.error)
        self.submitted.append(path)
        return JobView.model_validate(
            {
                "id": 7, "source_type": "upload", "source": path, "canonical_id": None,
                "title": None, "uploader": None, "duration_s": None, "provider": "fake",
                "status": "queued", "progress": 0, "message": "En cola", "error": None,
                "queries_used": 0, "retries": 0, "estimated_cost": 0, "cached": False,
                "created_at": "2026-10-18T00:00:00Z", "started_at": None, "finished_at": None,
            }
        )  # fmt: skip


def drop_event(*paths: str | None) -> dict[str, Any]:
    return {"dataTransfer": {"files": [{"name": "x", "pywebviewFullPath": p} for p in paths]}}


def test_drop_creates_job_and_notifies_page() -> None:
    manager = FakeManager()
    events: list[dict[str, Any]] = []
    handle_drop(drop_event("C:/sets/set.wav"), manager, events.append)  # type: ignore[arg-type]
    assert manager.submitted == ["C:/sets/set.wav"]
    assert events[0]["type"] == "file_dropped"
    assert events[0]["job"]["id"] == 7


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (drop_event(None), "No se pudo leer"),
        ({"dataTransfer": {}}, "No se pudo leer"),
        (drop_event("a.wav", "b.wav"), "único archivo"),
    ],
)
def test_bad_drops_report_errors(event: dict[str, Any], message: str) -> None:
    manager = FakeManager()
    events: list[dict[str, Any]] = []
    handle_drop(event, manager, events.append)  # type: ignore[arg-type]
    assert manager.submitted == []
    assert events[0]["type"] == "error"
    assert message in events[0]["error"]


def test_drop_rejected_by_manager_reports_error() -> None:
    events: list[dict[str, Any]] = []
    handle_drop(drop_event("C:/x.wav"), FakeManager("El archivo no existe."), events.append)  # type: ignore[arg-type]
    assert events == [{"type": "error", "error": "El archivo no existe."}]


@pytest.mark.parametrize(
    "url",
    ["https://evil.com", "http://evil.com:5173", "http://localhost.evil.com:5173", "file:///C:/x"],
)
def test_dev_url_only_allows_localhost(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("SETID_DEV_URL", url)
    with pytest.raises(ValueError):
        desktop.dev_url()


def test_dev_url_accepts_vite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETID_DEV_URL", "http://localhost:5173")
    assert desktop.dev_url() == "http://localhost:5173"
    monkeypatch.delenv("SETID_DEV_URL")
    assert desktop.dev_url() is None


def test_frontend_entry_honours_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    monkeypatch.setenv("SETID_FRONTEND_DIR", str(tmp_path))
    assert desktop.frontend_entry() == tmp_path / "index.html"


def test_window_icon_is_a_valid_multi_size_ico() -> None:
    path = desktop.icon_path()
    assert path is not None
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)  # cabecera ICO
    sizes = {struct.unpack("<B", data[6 + 16 * i : 7 + 16 * i])[0] or 256 for i in range(count)}
    assert {16, 24, 32, 48, 256} <= sizes


def test_yt_dlp_runs_from_the_cli_exe_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    from setid import proc

    assert proc.yt_dlp_command()[1:] == ["-m", "yt_dlp"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\SetID\SetID.exe")
    command = proc.yt_dlp_command()
    assert Path(command[0]) == Path(r"C:\Apps\SetID\setid-cli.exe")
    assert command[1:] == ["--yt-dlp"]


def test_cli_passes_yt_dlp_flag_through(monkeypatch: pytest.MonkeyPatch) -> None:
    import yt_dlp

    from setid import cli

    received: list[list[str]] = []

    def fake_main(argv: list[str]) -> None:
        received.append(argv)
        raise SystemExit(0)

    monkeypatch.setattr(yt_dlp, "main", fake_main)
    assert cli.main(["--yt-dlp", "--version"]) == 0
    assert received == [["--version"]]

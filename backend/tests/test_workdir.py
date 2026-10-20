import os
import sys
import threading
import time
from pathlib import Path

import pytest

from setid import proc
from setid.workdir import job_workdir, purge_stale


def test_workdir_is_removed_on_success_and_on_error(tmp_path: Path) -> None:
    with job_workdir(tmp_path) as work:
        (work / "audio.wav").write_bytes(b"x")
    assert list(tmp_path.iterdir()) == []

    with pytest.raises(RuntimeError), job_workdir(tmp_path) as work:
        (work / "audio.wav").write_bytes(b"x")
        raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


def test_purge_only_removes_old_job_dirs(tmp_path: Path) -> None:
    old = tmp_path / "job-old"
    old.mkdir()
    (old / "normalized.wav").write_bytes(b"x")
    long_ago = time.time() - 7 * 3600
    os.utime(old, (long_ago, long_ago))
    recent = tmp_path / "job-recent"  # podría ser un trabajo vivo de otro proceso
    recent.mkdir()
    other = tmp_path / "not-a-job"
    other.mkdir()
    os.utime(other, (long_ago, long_ago))

    assert purge_stale(tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["job-recent", "not-a-job"]


def test_proc_run_can_be_cancelled() -> None:
    event = threading.Event()
    token = proc.cancel_event.set(event)
    try:
        threading.Timer(0.3, event.set).start()
        started = time.monotonic()
        with pytest.raises(proc.ProcessCancelled):
            proc.run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=60,
            )
        assert time.monotonic() - started < 5
    finally:
        proc.cancel_event.reset(token)


def test_proc_run_times_out() -> None:
    with pytest.raises(proc.ProcessTimeout):
        proc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)


def test_proc_run_reports_missing_program() -> None:
    with pytest.raises(proc.ProgramNotFound):
        proc.run(["setid-programa-que-no-existe"], timeout=5)

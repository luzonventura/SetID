from __future__ import annotations

import shutil

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if HAS_FFMPEG:
        return
    skip = pytest.mark.skip(reason="ffmpeg/ffprobe no están instalados")
    for item in items:
        if "ffmpeg" in item.keywords:
            item.add_marker(skip)

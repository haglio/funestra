from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from funestra import flick_decode
from funestra.flick_decode import load_flick_frames

WIDTH, HEIGHT = 4, 2


class _FakeFfmpeg:
    def __init__(self, raw: bytes, *, returncode: int = 0, stderr: bytes = b""):
        self.stdout = io.BytesIO(raw)
        self.stderr = io.BytesIO(stderr)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


@pytest.fixture
def ffmpeg(monkeypatch):
    def install(raw: bytes, **kwargs):
        monkeypatch.setattr(flick_decode.subprocess, "check_output",
                            lambda *_args, **_kw: f"{WIDTH}x{HEIGHT}\n")
        monkeypatch.setattr(flick_decode.subprocess, "Popen",
                            lambda *_args, **_kw: _FakeFfmpeg(raw, **kwargs))
    return install


def _frame_bytes(value: int) -> bytes:
    return bytes([value]) * (WIDTH * HEIGHT * 3)


def test_every_frame_of_the_flick_comes_back_as_an_image_of_its_size(ffmpeg):
    ffmpeg(_frame_bytes(10) + _frame_bytes(20) + _frame_bytes(30))

    frames = load_flick_frames(Path("scene one.mp4"))

    assert [frame.shape for frame in frames] == [(HEIGHT, WIDTH, 3)] * 3
    assert [int(frame[0, 0, 0]) for frame in frames] == [10, 20, 30]
    assert all(isinstance(frame, np.ndarray) for frame in frames)


def test_a_torn_last_frame_is_left_off(ffmpeg):
    ffmpeg(_frame_bytes(10) + _frame_bytes(20)[:5])

    assert len(load_flick_frames(Path("scene one.mp4"))) == 1


def test_a_failed_decode_says_what_ffmpeg_said(ffmpeg):
    ffmpeg(b"", returncode=1, stderr=b"moov atom not found")

    with pytest.raises(RuntimeError, match="moov atom not found"):
        load_flick_frames(Path("scene one.mp4"))


def test_a_flick_with_no_frames_is_refused(ffmpeg):
    ffmpeg(b"")

    with pytest.raises(RuntimeError, match="No frames"):
        load_flick_frames(Path("scene one.mp4"))


def test_a_caller_still_naming_the_old_frame_cache_folder_gets_the_flick_decoded(ffmpeg, tmp_path):
    ffmpeg(_frame_bytes(10))

    assert len(load_flick_frames(Path("scene one.mp4"), tmp_path / "frames")) == 1

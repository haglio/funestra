from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from funestra import flick_decode
from funestra.flick_decode import load_flick_frames

WIDTH, HEIGHT = 4, 2


class _ReadOnlyIntoTheImage(io.BytesIO):
    def read(self, *_args):
        raise AssertionError("a frame read as bytes is a second copy of it to make and throw away")


class _FakeFfmpeg:
    def __init__(self, raw: bytes, *, returncode: int = 0, stderr: bytes = b""):
        self.stdout = _ReadOnlyIntoTheImage(raw)
        self.stderr = io.BytesIO(stderr)
        self._returncode = returncode
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    def wait(self) -> int:
        return self._returncode


@pytest.fixture
def ffmpeg(monkeypatch):
    def install(raw: bytes, *, size=lambda: f"{WIDTH}x{HEIGHT}\n", **kwargs):
        started: list = []

        def probe(*_args, **_kw):
            started.append("ffprobe")
            return size()

        def decode(*_args, **_kw):
            started.append(_FakeFfmpeg(raw, **kwargs))
            return started[-1]

        monkeypatch.setattr(flick_decode.subprocess, "check_output", probe)
        monkeypatch.setattr(flick_decode.subprocess, "Popen", decode)
        return started
    return install


def _frame_bytes(value: int) -> bytes:
    return bytes([value]) * (WIDTH * HEIGHT * 3)


def test_every_frame_of_the_flick_comes_back_as_an_image_of_its_size_the_whole_flick_in_memory_since_genau_jumps_to_any_frame_at_any_moment(ffmpeg):
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


def test_the_decode_is_under_way_while_the_size_is_asked_for_so_a_step_does_not_wait_out_one_program_before_starting_the_next(ffmpeg):
    started = ffmpeg(_frame_bytes(10))

    load_flick_frames(Path("scene one.mp4"))

    assert [program if program == "ffprobe" else "ffmpeg" for program in started] == ["ffmpeg", "ffprobe"]


def test_a_size_that_cannot_be_read_ends_the_decode_that_had_started(ffmpeg):
    def no_size():
        raise OSError("ffprobe is not installed")

    started = ffmpeg(_frame_bytes(10), size=no_size)

    with pytest.raises(OSError, match="not installed"):
        load_flick_frames(Path("scene one.mp4"))

    assert started[0].killed
    assert started[0].stdout.closed


def test_each_frame_is_an_image_of_its_own_that_can_be_drawn_on(ffmpeg):
    ffmpeg(_frame_bytes(10) + _frame_bytes(20))

    first, second = load_flick_frames(Path("scene one.mp4"))
    first[0, 0, 0] = 99

    assert (int(first[0, 0, 0]), int(second[0, 0, 0])) == (99, 20)

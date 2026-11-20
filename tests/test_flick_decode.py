from __future__ import annotations

import io
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from funestra import flick_decode
from funestra.flick_decode import load_flick_frames

WIDTH, HEIGHT = 4, 2


class _ReadOnlyIntoTheImage(io.BytesIO):
    def __init__(self, raw: bytes):
        super().__init__(raw)
        self.reads = 0

    def read(self, *_args):
        raise AssertionError("a frame read as bytes is a second copy of it to make and throw away")

    def readinto(self, into) -> int:
        self.reads += 1
        return super().readinto(into)


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

        def decode(_cmd):
            started.append(_FakeFfmpeg(raw, **kwargs))
            return started[-1], started[-1].stdout

        monkeypatch.setattr(flick_decode.subprocess, "check_output", probe)
        monkeypatch.setattr(flick_decode, "_start_ffmpeg", decode)
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


def test_frames_are_read_a_block_at_a_time_since_each_read_waits_its_turn_behind_the_window_drawing_genau(ffmpeg, monkeypatch):
    monkeypatch.setattr(flick_decode, "FRAMES_PER_READ", 4)
    started = ffmpeg(b"".join(_frame_bytes(value) for value in range(8)))

    frames = load_flick_frames(Path("scene one.mp4"))

    assert [int(frame[0, 0, 0]) for frame in frames] == list(range(8))
    assert started[0].stdout.reads == 3


def test_the_last_frames_hold_no_memory_for_frames_the_flick_does_not_have(ffmpeg, monkeypatch):
    monkeypatch.setattr(flick_decode, "FRAMES_PER_READ", 4)
    ffmpeg(b"".join(_frame_bytes(value) for value in range(5)))

    last = load_flick_frames(Path("scene one.mp4"))[-1]

    assert int(last[0, 0, 0]) == 4
    assert (last.base if last.base is not None else last).nbytes == last.nbytes


def test_ffmpeg_can_write_far_ahead_of_genau_so_a_read_waiting_its_turn_comes_back_with_many_frames():
    reader, writer = flick_decode._pipe_far_ahead()
    try:
        assert os.write(writer, bytes(flick_decode.PIPE_AHEAD_BYTES)) == flick_decode.PIPE_AHEAD_BYTES
    finally:
        reader.close()
        os.close(writer)


def test_ffmpeg_writes_its_frames_into_the_pipe_that_runs_far_ahead_and_genau_reads_them_to_the_end(monkeypatch):
    def ffmpeg_writing(cmd, *, stdout, stderr, **_kw):
        os.write(stdout, _frame_bytes(10))
        return SimpleNamespace(cmd=cmd, stderr=stderr)

    monkeypatch.setattr(flick_decode.subprocess, "Popen", ffmpeg_writing)

    proc, frames_stream = flick_decode._start_ffmpeg(["ffmpeg"])
    try:
        assert frames_stream.readall() == _frame_bytes(10)
        assert proc.stderr == flick_decode.subprocess.PIPE
    finally:
        frames_stream.close()


def test_an_ffmpeg_that_cannot_start_leaves_no_pipe_open(monkeypatch):
    pipes = []

    def remembered_pipe():
        pipes.append(real_pipe())
        return pipes[-1]

    def no_ffmpeg(*_args, **_kw):
        raise FileNotFoundError("ffmpeg is not installed")

    real_pipe = flick_decode._pipe_far_ahead
    monkeypatch.setattr(flick_decode, "_pipe_far_ahead", remembered_pipe)
    monkeypatch.setattr(flick_decode.subprocess, "Popen", no_ffmpeg)

    with pytest.raises(FileNotFoundError):
        flick_decode._start_ffmpeg(["ffmpeg"])

    reader, writer = pipes[0]
    assert reader.closed
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.close(writer)


def test_a_pipe_windows_will_not_make_is_refused_out_loud():
    refusing = SimpleNamespace(CreatePipe=lambda *_args: 0)

    with pytest.raises(OSError, match="WinError"):
        flick_decode._pipe_far_ahead(refusing)

from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import msvcrt
import os
import subprocess
from pathlib import Path

import numpy as np
from app_support.subprocess_utils import hidden_subprocess_kwargs


def _ffprobe_size(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True, **hidden_subprocess_kwargs()).strip()
    width, height = out.split("x", 1)
    return int(width), int(height)


FRAMES_PER_READ = 16


def _fill(stream, block: np.ndarray) -> int:
    into = memoryview(block).cast("B")
    filled = 0
    while filled < len(into):
        read = stream.readinto(into[filled:])
        if not read:
            break
        filled += read
    return filled


def _read_frames(stream, width: int, height: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    while True:
        block = np.empty((FRAMES_PER_READ, height, width, 3), dtype=np.uint8)
        whole_frames = _fill(stream, block) // block[0].nbytes
        if whole_frames < FRAMES_PER_READ:
            frames.extend(frame.copy() for frame in block[:whole_frames])
            return frames
        frames.extend(block)


PIPE_AHEAD_BYTES = 64 * 1024 * 1024


def _pipe_far_ahead(kernel32=None):
    read_handle, write_handle = ctypes.wintypes.HANDLE(), ctypes.wintypes.HANDLE()
    kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.CreatePipe(ctypes.byref(read_handle), ctypes.byref(write_handle), None, PIPE_AHEAD_BYTES):
        raise ctypes.WinError(ctypes.get_last_error())
    reader = io.FileIO(msvcrt.open_osfhandle(read_handle.value, os.O_RDONLY), "rb")
    return reader, msvcrt.open_osfhandle(write_handle.value, 0)


def _start_ffmpeg(cmd: list[str]):
    frames_stream, ffmpeg_writes_into = _pipe_far_ahead()
    try:
        proc = subprocess.Popen(cmd, stdout=ffmpeg_writes_into, stderr=subprocess.PIPE, **hidden_subprocess_kwargs())
    except BaseException:
        frames_stream.close()
        raise
    finally:
        os.close(ffmpeg_writes_into)
    return proc, frames_stream


def load_flick_frames(path: Path, _frame_cache_dir: Path | None = None) -> list[np.ndarray]:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-vsync",
        "0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]

    proc, frames_stream = _start_ffmpeg(cmd)

    try:
        width, height = _ffprobe_size(path)
    except BaseException:
        proc.kill()
        frames_stream.close()
        proc.stderr.close()
        proc.wait()
        raise

    try:
        frames = _read_frames(frames_stream, width, height)
    finally:
        frames_stream.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(stderr.strip() or f"ffmpeg failed for {path}")

    if not frames:
        raise RuntimeError(f"No frames decoded from: {path}")

    return frames

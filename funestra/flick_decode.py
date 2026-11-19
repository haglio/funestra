from __future__ import annotations

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


def _read_whole(stream, frame: np.ndarray) -> bool:
    into = memoryview(frame).cast("B")
    filled = 0
    while filled < len(into):
        read = stream.readinto(into[filled:])
        if not read:
            return False
        filled += read
    return True


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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **hidden_subprocess_kwargs())
    frames: list[np.ndarray] = []

    try:
        width, height = _ffprobe_size(path)
    except BaseException:
        proc.kill()
        proc.stdout.close()
        proc.stderr.close()
        proc.wait()
        raise

    try:
        while True:
            frame = np.empty((height, width, 3), dtype=np.uint8)
            if not _read_whole(proc.stdout, frame):
                break
            frames.append(frame)
    finally:
        if proc.stdout:
            proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(stderr.strip() or f"ffmpeg failed for {path}")

    if not frames:
        raise RuntimeError(f"No frames decoded from: {path}")

    return frames

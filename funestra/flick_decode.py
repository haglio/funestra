"""A flick's frames, as RGB arrays, decoded whole with ffmpeg: Genau scrubs
rather than plays, so it has to be able to show any frame at any moment."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from app_support.subprocess_utils import hidden_subprocess_kwargs

__all__ = [
    "load_flick_frames",
]

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


def load_flick_frames(path: Path, _frame_cache_dir: Path | None = None) -> list[np.ndarray]:
    width, height = _ffprobe_size(path)
    frame_size = width * height * 3

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
        while True:
            buf = proc.stdout.read(frame_size) if proc.stdout else b""
            if not buf:
                break
            if len(buf) != frame_size:
                break
            frames.append(
                np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3)).copy()
            )
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

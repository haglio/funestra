from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .file_channel import publish_whole
from .playback_rate import NORMAL_RATE


@dataclass(frozen=True)
class FunestraStatus:
    video: str = ""
    position_ms: int = 0
    duration_ms: int = 0
    paused: bool = False
    locked: bool = False
    speed: float = NORMAL_RATE
    image: bool = False
    read_at: float = 0.0


def _flag(on: bool) -> str:
    return "1" if on else "0"


def status_fields(status: FunestraStatus) -> dict[str, str]:
    return {
        "video": status.video,
        "position_ms": str(int(status.position_ms)),
        "duration_ms": str(int(status.duration_ms)),
        "paused": _flag(status.paused),
        "locked": _flag(status.locked),
        "speed": f"{status.speed:g}",
        "picture": _flag(status.image),
        "read_at": f"{status.read_at:.3f}",
    }


def _int(text: str | None, default: int) -> int:
    if text is None:
        return default
    try:
        return int(text.strip())
    except ValueError:
        return default


def _rate(text: str | None, default: float) -> float:
    if text is None:
        return default
    try:
        return float(text.strip())
    except ValueError:
        return default


def _bool(text: str | None, default: bool) -> bool:
    return default if text is None else text.strip() == "1"


def parse_status(fields: Mapping[str, str], *, default: FunestraStatus | None = None) -> FunestraStatus:
    if default is None:
        default = FunestraStatus()
    return FunestraStatus(
        video=fields.get("video", default.video).strip(),
        position_ms=_int(fields.get("position_ms"), default.position_ms),
        duration_ms=_int(fields.get("duration_ms"), default.duration_ms),
        paused=_bool(fields.get("paused"), default.paused),
        locked=_bool(fields.get("locked"), default.locked),
        speed=_rate(fields.get("speed"), default.speed),
        image=_bool(fields.get("picture"), default.image),
        read_at=_rate(fields.get("read_at"), default.read_at),
    )

class StatusWriter:
    def __init__(
        self,
        path: Path,
        fields: Callable[[object], Mapping[str, str]],
        *,
        min_interval: float = 0.2,
        now_source=time.monotonic,
    ) -> None:
        self._path = path
        self._fields = fields
        self._min_interval = min_interval
        self._now = now_source
        self._last_write: float | None = None

    def write(self, session) -> bool:
        now = self._now()
        if self._last_write is not None and now - self._last_write < self._min_interval:
            return False
        text = "".join(f"{key}={value}\n" for key, value in self._fields(session).items())
        if not publish_whole(self._path, text):
            return False
        self._last_write = now
        return True

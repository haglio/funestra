"""The status file a Funestra publishes for its content source to read.

The reverse leg of :mod:`funestra.file_channel`: commands and the paused flag
go in, this comes back out.  Fun Time polls it to know what each Funestra is
showing — the item on screen, the playhead, whether the Funestra is paused or
holding — and whatever else that Funestra's features need.

Every Funestra leads with the same lines, :class:`FunestraStatus`, written by
:func:`status_fields` and read back by :func:`parse_status`; a Funestra adds its
own lines after them (the Main Funestra's loop and funscript, a satellite's
playlist length), and its reader takes those off the same file.

Writes are throttled because the playhead changes every tick, while a poller
only ever samples a few times a second.  *What* to publish arrives as a
``fields`` callable; *how* to publish it — the throttle, the directory, and
surviving a locked or vanished file — is identical everywhere and lives here.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .file_channel import publish_whole
from .renamed import old_name_getter

__all__ = [
    "FunestraStatus",
    "parse_status",
    "status_fields",
]

_RENAMED = {"PlayerStatus": "FunestraStatus"}

__getattr__ = old_name_getter(__name__, _RENAMED)


@dataclass(frozen=True)
class FunestraStatus:
    """What every Funestra says about itself: the item on screen, where the
    playhead is in it and when that was read, whether the Funestra is paused or
    holding it, the rate it plays at, and whether what is on screen is a still
    picture."""

    video: str = ""
    position_ms: int = 0
    duration_ms: int = 0
    paused: bool = False
    locked: bool = False
    speed: float = 1.0
    picture: bool = False
    read_at: float = 0.0


def stamp_the_playhead(position_ms: float) -> tuple[int, float]:
    return int(position_ms), time.time()


def _flag(on: bool) -> str:
    return "1" if on else "0"


def status_fields(status: FunestraStatus) -> dict[str, str]:
    """The lines every Funestra publishes, in the order they are written."""
    return {
        "video": status.video,
        "position_ms": str(int(status.position_ms)),
        "duration_ms": str(int(status.duration_ms)),
        "paused": _flag(status.paused),
        "locked": _flag(status.locked),
        "speed": f"{status.speed:g}",
        "picture": _flag(status.picture),
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
    """The record a read status file's ``key=value`` pairs carry.

    A key the file does not carry keeps *default*'s answer — a status from before
    the key existed, or one read before the Funestra's first write, says what that
    Funestra is doing at rest, which differs: a satellite opens unlocked, the Main
    Funestra locked.  A number that cannot be read keeps it too.
    """
    if default is None:
        default = FunestraStatus()
    return FunestraStatus(
        video=fields.get("video", default.video).strip(),
        position_ms=_int(fields.get("position_ms"), default.position_ms),
        duration_ms=_int(fields.get("duration_ms"), default.duration_ms),
        paused=_bool(fields.get("paused"), default.paused),
        locked=_bool(fields.get("locked"), default.locked),
        speed=_rate(fields.get("speed"), default.speed),
        picture=_bool(fields.get("picture"), default.picture),
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
        """Publish *session*'s status, unless the last write was too recent.

        Returns whether anything reached disk, so a caller can tell a throttled
        tick from a failed one.
        """
        now = self._now()
        if self._last_write is not None and now - self._last_write < self._min_interval:
            return False
        text = "".join(f"{key}={value}\n" for key, value in self._fields(session).items())
        # Published whole rather than truncated in place: the orchestrator polls
        # this file, and a poller that caught a truncating write would read no
        # clip at all — which it cannot tell from a Funestra that has none.
        if not publish_whole(self._path, text):
            return False
        self._last_write = now
        return True

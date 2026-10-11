"""What a Funestra publishes in its status file, after the lines every Funestra leads with."""
from __future__ import annotations

from .status import FunestraStatus
from .status import status_fields as leading_fields

__all__ = [
    "status_fields",
]


def status_fields(playback, handoff_touch_ms: int | None) -> dict[str, str]:
    return {
        **leading_fields(FunestraStatus(
            video=str(playback.current_video),
            position_ms=int(playback.position_ms),
            duration_ms=int(playback.duration_ms),
            paused=playback.is_paused,
            locked=playback.is_locked,
            speed=playback.speed,
            picture=playback.showing_picture,
        )),
        "playlist_length": str(playback.playlist_length),
        "has_funscript": "1" if playback.has_funscript else "0",
        "funscript_resting": "1" if playback.funscript_resting else "0",
        "handoff_touch_ms": "" if handoff_touch_ms is None else str(int(handoff_touch_ms)),
        "portrait": "" if playback.portrait is None else "1" if playback.portrait else "0",
    }

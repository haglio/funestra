"""What a Funestra publishes in its status file, after the lines every Funestra leads with."""
from __future__ import annotations

from .renamed import value_of
from .status import FunestraStatus
from .status import status_fields as leading_fields
from .volume import VolumeHud


def status_fields(playback, handoff_touch_ms: int | None) -> dict[str, str]:
    return {
        **leading_fields(FunestraStatus(
            video=str(playback.current_video),
            position_ms=int(playback.position_ms),
            duration_ms=int(playback.duration_ms),
            paused=playback.is_paused,
            locked=playback.is_locked,
            speed=playback.speed,
            image=value_of(playback, "showing_image", old_name="showing_picture"),
        )),
        "playlist_length": str(playback.playlist_length),
        "has_funscript": "1" if playback.has_funscript else "0",
        "funscript_resting": "1" if playback.funscript_resting else "0",
        "handoff_touch_ms": "" if handoff_touch_ms is None else str(int(handoff_touch_ms)),
        "portrait": "" if playback.portrait is None else "1" if playback.portrait else "0",
        "loads": str(playback.loads),
        "idle": "1" if playback.idle else "0",
    }


def volume_fields(hud: VolumeHud) -> dict[str, str]:
    return {"volume": str(hud.volume), "muted": "1" if hud.muted else "0"}

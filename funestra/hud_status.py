"""The HUD's title under the name it had before it was called the title, for
checkouts from before the rename; nothing new may use it."""
from __future__ import annotations

from .hud_title import (  # noqa: F401
    ENHANCED_LABEL,
    F_MODE_LABEL,
    LATEST_LABEL,
    LOCKED_LABEL,
    PLAYBACK_SPEED_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    UNLOCKED_LABEL,
    hud_title,
    looping_label,
)


def status_line(*, filter_label: str = "", **slots) -> str:
    return hud_title(filters=(filter_label,), **slots)

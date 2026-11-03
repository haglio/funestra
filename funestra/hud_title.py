from __future__ import annotations

from collections.abc import Sequence

SEPARATOR = " · "

LOCKED_LABEL = "Locked"
UNLOCKED_LABEL = "Unlocked"

LATEST_LABEL = "Latest"
SHUFFLE_LABEL = "Shuffle"

F_MODE_LABEL = "F-Mode"

PLAYBACK_SPEED_LABEL = "Playback speed"


ENHANCED_LABEL = "Enhanceds"


def looping_label(axis: str) -> str:
    return f"Looping {axis}s"


def hud_title(*, locked: bool, playing_set: str = "", order: str = "",
              f_mode: bool = False, enhanced: bool = False,
              filters: Sequence[str] = ()) -> str:
    parts = [playing_set] if playing_set else []
    if locked:
        parts.append(LOCKED_LABEL)
    elif not playing_set:
        parts.append(UNLOCKED_LABEL)
    if order:
        parts.append(order)
    if f_mode:
        parts.append(F_MODE_LABEL)
    if enhanced:
        parts.append(ENHANCED_LABEL)
    parts.extend(word for word in filters if word)
    return SEPARATOR.join(parts)

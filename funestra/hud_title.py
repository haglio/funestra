from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True)
class HudTitleFacts:
    locked: bool
    playing_set: str = ""
    order: str = ""
    f_mode: bool = False
    enhanced: bool = False
    filters: Sequence[str] = ()


def hud_title(facts: HudTitleFacts | None = None, **old) -> str:
    facts = HudTitleFacts(**old) if facts is None else facts
    parts = [facts.playing_set] if facts.playing_set else []
    if facts.locked:
        parts.append(LOCKED_LABEL)
    elif not facts.playing_set:
        parts.append(UNLOCKED_LABEL)
    if facts.order:
        parts.append(facts.order)
    if facts.f_mode:
        parts.append(F_MODE_LABEL)
    if facts.enhanced:
        parts.append(ENHANCED_LABEL)
    parts.extend(word for word in facts.filters if word)
    return SEPARATOR.join(parts)

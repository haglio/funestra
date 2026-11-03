from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app_support.state_files import GENAU_STATUS

from .file_channel import publish_whole
from .flick_advance import FlickAdvanceState
from .learned_motion import LearnedMotionState
from .robot_hand import RobotHandState, control_limits

GENAU_STATUS_FILENAME = GENAU_STATUS


def _flag_or_unknown(flag: bool | None) -> str:
    return "" if flag is None else "1" if flag else "0"


@dataclass(frozen=True)
class FlickOnScreen:
    path: Path | None = None
    flipped: bool = False
    portrait: bool | None = None


def build_status_text(
    hand: RobotHandState,
    *,
    learned: LearnedMotionState | None = None,
    flick_advance: FlickAdvanceState | None = None,
    on_screen: FlickOnScreen | None = None,
) -> str:
    limits = control_limits(hand)
    on_screen = on_screen or FlickOnScreen()
    advance = flick_advance or FlickAdvanceState()
    return (
        f"learned={'1' if learned is not None and learned.active else '0'}\n"
        f"locked={'1' if advance.locked else '0'}\n"
        f"flick={on_screen.path if on_screen.path is not None else ''}\n"
        f"flipped={'1' if on_screen.flipped else '0'}\n"
        f"portrait={_flag_or_unknown(on_screen.portrait)}\n"
        f"shape={hand.shape.value}\n"
        f"amp_at_max={'1' if limits.amp_at_max else '0'}\n"
        f"amp_at_min={'1' if limits.amp_at_min else '0'}\n"
        f"ctr_at_max={'1' if limits.ctr_at_max else '0'}\n"
        f"ctr_at_min={'1' if limits.ctr_at_min else '0'}\n"
        f"spd_at_max={'1' if limits.spd_at_max else '0'}\n"
        f"spd_at_min={'1' if limits.spd_at_min else '0'}\n"
        f"playing={'1' if hand.playing else '0'}\n"
        f"interval={advance.interval}\n"
        f"max_intensity={hand.max_intensity}\n"
    )


def write_status_file(path: Path, text: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, ValueError):
        pass
    return publish_whole(path, text)

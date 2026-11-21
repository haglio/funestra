from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app_support.state_files import GENAU_STATUS

from .file_channel import publish_whole
from .flick_advance import DEFAULT_INTERVAL_S, FlickAdvanceState
from .learned_motion import LearnedMotionState
from .robot_hand import RobotHandState, control_limits

GENAU_STATUS_FILENAME = GENAU_STATUS
GENAU_OPENS_LOCKED = FlickAdvanceState().locked


def _flag_or_unknown(flag: bool | None) -> str:
    return "" if flag is None else "1" if flag else "0"


@dataclass(frozen=True)
class FlickOnScreen:
    path: Path | None = None
    flipped: bool = False
    portrait: bool | None = None
    up_at: float | None = None
    whole: bool = False
    unreadable: bool = False


def _up_at(on_screen: FlickOnScreen) -> str:
    return "" if on_screen.up_at is None else f"{on_screen.up_at:.3f}"


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
        f"robot_hand_off={'1' if hand.off else '0'}\n"
        f"locked={'1' if advance.locked else '0'}\n"
        f"flick={on_screen.path if on_screen.path is not None else ''}\n"
        f"up_at={_up_at(on_screen)}\n"
        f"whole={'1' if on_screen.whole else '0'}\n"
        f"unreadable={'1' if on_screen.unreadable else '0'}\n"
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


class StatusFile:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._written: str | None = None

    def write(self, text: str) -> bool:
        if text == self._written or not publish_whole(self._path, text):
            return False
        self._written = text
        return True


@dataclass(frozen=True)
class GenauStatus:
    learned_active: bool = False
    robot_hand_off: bool = False
    locked: bool = GENAU_OPENS_LOCKED
    shape: str = "sine"
    flick: str = ""
    flipped: bool = False
    portrait: bool | None = None
    up_at: float | None = None
    interval: int = DEFAULT_INTERVAL_S


def _on(values: dict[str, str], key: str, *, at_rest: bool = False) -> bool:
    return values.get(key, "1" if at_rest else "0").strip() not in ("0", "false", "")


def _on_or_unknown(values: dict[str, str], key: str) -> bool | None:
    return {"1": True, "0": False}.get(values.get(key, "").strip())


def _seconds_or_none(values: dict[str, str], key: str) -> float | None:
    try:
        return float(values.get(key, ""))
    except ValueError:
        return None


def _whole_seconds(values: dict[str, str], key: str, at_rest: int) -> int:
    said = values.get(key, "").strip()
    return int(said) if said.isdigit() else at_rest


def genau_status_from(values: dict[str, str]) -> GenauStatus:
    return GenauStatus(
        learned_active=_on(values, "learned"),
        robot_hand_off=_on(values, "robot_hand_off"),
        locked=_on(values, "locked", at_rest=GENAU_OPENS_LOCKED),
        shape=values.get("shape", "sine").strip(),
        flick=values.get("flick", "").strip(),
        flipped=_on(values, "flipped"),
        portrait=_on_or_unknown(values, "portrait"),
        up_at=_seconds_or_none(values, "up_at"),
        interval=_whole_seconds(values, "interval", DEFAULT_INTERVAL_S),
    )

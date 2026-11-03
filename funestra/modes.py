from __future__ import annotations

from enum import Enum, StrEnum

from app_support.osr2_device import Osr2Mode, Osr2Trouble


class MainMode(StrEnum):
    KINO = "kino"
    GENAU = "genau"


class SatellitesMode(StrEnum):
    KINO = "kino"
    ORIGENERATOR = "origenerator"


class LoopState(StrEnum):
    NORMAL = "normal"
    RECORDING = "recording"
    LOOPING = "looping"


class Osr2State(StrEnum):
    OFF = "off"
    AUTO = "auto"
    FUNSCRIPT = "funscript"
    ROBOT_HAND = "robot_hand"
    UNPLUGGED = "unplugged"
    NO_ANSWER = "no_answer"

    @classmethod
    def of(cls, device: Osr2Mode, *, funscript_driving: bool,
           trouble: Osr2Trouble | None = None) -> Osr2State:
        if device is Osr2Mode.OFF:
            return _UNHEARD_BECAUSE.get(trouble, cls.OFF)
        if device is Osr2Mode.AUTO:
            return cls.AUTO
        return cls.FUNSCRIPT if funscript_driving else cls.ROBOT_HAND


_UNHEARD_BECAUSE = {
    Osr2Trouble.NOT_FOUND: Osr2State.UNPLUGGED,
    Osr2Trouble.NOT_ANSWERING: Osr2State.NO_ANSWER,
}
UNHEARD = frozenset({Osr2State.OFF, *_UNHEARD_BECAUSE.values()})


class LengthMode(StrEnum):
    MIXED = "mixed"
    CLIPS = "clips"
    FULL = "full"
    NONE = "none"


class MessageLevel(StrEnum):
    WARNING = "warning"
    NORMAL = "notice"
    HIGHLIGHT = "favorite"


def read_mode[M: Enum, D](enum: type[M], raw: object, default: D) -> M | D:
    if isinstance(raw, enum):
        return raw
    try:
        return enum(raw)
    except ValueError:
        return default

"""The closed sets a Funestra and Fun Time agree on, each as the words on the wire.

Each of these travels between two processes as a bare word in a published file
-- the main console's JSON, the shared state INI, a status file -- and was
compared by literal at every site that read it.  Each entry's value IS that
word: a writer hands the entry to ``json.dumps`` and the word comes out, and
:func:`read_mode` turns the word back into the entry on the way in.

A word a reader does not know is the default, never an error.  The two sides of
every one of these files are separate processes that are not always the same
age, and a Funestra that refused a mode it had not heard of would stop drawing
over a difference of vocabulary.
"""
from __future__ import annotations

from enum import Enum, StrEnum

__all__ = [
    "LengthMode",
    "LoopState",
    "MainMode",
    "NoticeLevel",
    "Osr2State",
    "SatellitesMode",
    "read_mode",
]


class MainMode(StrEnum):
    """What holds the main slot: Kino's video, or Genau's flicks."""

    KINO = "kino"
    GENAU = "genau"
    VIDEO = KINO


class SatellitesMode(StrEnum):
    """What the satellite side shows: the two Funestras, or a hosted Origenerator's
    shows over them."""

    KINO = "kino"
    ORIGENERATOR = "origenerator"
    VIDEO = KINO


class LoopState(StrEnum):
    """Where Kino's loop machine is: idle, marking a loop's out point
    with the record key down, or repeating the loop it marked."""

    NORMAL = "normal"
    RECORDING = "recording"
    LOOPING = "looping"


class Osr2State(StrEnum):
    """What has the OSR2, as the console badges it: nothing, the broker's auto
    mode, the video's funscript, or the Robot Hand filling in."""

    OFF = "off"
    AUTO = "auto"
    FUNSCRIPT = "funscript"
    ROBOT_HAND = "robot_hand"


class LengthMode(StrEnum):
    """How long a video has to be to be in Kino's browse."""

    MIXED = "mixed"
    CLIPS = "clips"
    FULL = "full"
    NONE = "none"
    SHORTS = CLIPS

    @classmethod
    def _missing_(cls, value: object) -> LengthMode | None:
        return cls.CLIPS if value == "shorts" else None


class NoticeLevel(StrEnum):
    """What kind of thing a one-shot notice from the Main Funestra is, for Fun
    Time to pick the color: a request with nowhere to go, an ordinary word, or
    one about a funscript -- which wears the green this family keeps for the
    favorites and the funscripts, and travels under that word.
    """

    WARNING = "warning"
    NOTICE = "notice"
    HIGHLIGHT = "favorite"


def read_mode[M: Enum, D](enum: type[M], raw: object, default: D) -> M | D:
    """The entry of *enum* whose wire word is *raw*, or *default* for anything else
    -- an entry, or None from a reader for whom "no word" is itself an answer."""
    if isinstance(raw, enum):
        return raw
    try:
        return enum(raw)
    except ValueError:
        return default

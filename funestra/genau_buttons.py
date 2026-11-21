from __future__ import annotations

from .funestra_verbs import NEXT, PREV
from .genau_controls import FLICK_SECONDS, FLICK_SECONDS_DOWN, FLICK_SECONDS_UP, FLIP_ENDS

PREV_FLICK = "genau_prev_flick"
NEXT_FLICK = "genau_next_flick"
FLICK_SECONDS_LESS = "genau_flick_seconds_down"
FLICK_SECONDS_MORE = "genau_flick_seconds_up"
FLIP_THE_FLICK = "genau_flip_ends"
TRASH_FLICK = "genau_trash_flick"
FLICK_SECONDS_BUTTON = "genau_flick_seconds"

GENAU_VERBS: dict[str, str] = {
    PREV_FLICK: PREV,
    NEXT_FLICK: NEXT,
    FLICK_SECONDS_LESS: FLICK_SECONDS_DOWN,
    FLICK_SECONDS_MORE: FLICK_SECONDS_UP,
    FLIP_THE_FLICK: FLIP_ENDS,
}

GENAU_VALUED: dict[str, str] = {FLICK_SECONDS_BUTTON: FLICK_SECONDS}

ABOUT_GENAUS_FLICK = frozenset({*GENAU_VERBS, TRASH_FLICK, FLICK_SECONDS_BUTTON})

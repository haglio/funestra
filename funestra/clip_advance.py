"""What :mod:`funestra.flick_advance` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

__all__: list[str] = []

_RENAMED = {
    "ClipAdvanceState": "FlickAdvanceState",
    "DEFAULT_INTERVAL_S": "DEFAULT_INTERVAL_S",
    "MAX_INTERVAL_S": "MAX_INTERVAL_S",
    "MIN_INTERVAL_S": "MIN_INTERVAL_S",
    "adjust_interval": "adjust_interval",
    "set_interval": "set_interval",
    "tick_clip_advance": "tick_flick_advance",
}

__getattr__ = old_name_getter("funestra.flick_advance", _RENAMED)

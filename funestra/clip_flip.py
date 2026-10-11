"""What :mod:`funestra.flick_flip` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

__all__: list[str] = []

_RENAMED = {
    "ClipFlip": "FlickFlip",
    "FLIPPED": "FLIPPED",
    "GENAU_SECTION": "GENAU_SECTION",
    "HALF_A_LOOP": "HALF_A_LOOP",
    "logger": "logger",
}

__getattr__ = old_name_getter("funestra.flick_flip", _RENAMED)

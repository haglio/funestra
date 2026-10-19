"""What :mod:`funestra.flick_scrub` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "ClipScrub": "FlickScrub",
    "scrub_clip": "scrub_flick",
}

__getattr__ = old_name_getter("funestra.flick_scrub", _RENAMED)

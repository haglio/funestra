"""What :mod:`funestra.flick_decode` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "load_clip_frames": "load_flick_frames",
}

__getattr__ = old_name_getter("funestra.flick_decode", _RENAMED)

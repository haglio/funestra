"""What :mod:`funestra.flick_overlay` was called before an item was an image or a
video, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "BACKDROP_OVERLAY_ID": "BACKDROP_OVERLAY_ID",
    "FIRST_TILE_OVERLAY_ID": "FIRST_TILE_OVERLAY_ID",
    "FlickPicture": "FlickOverlay",
    "LOADING_OVERLAY_ID": "LOADING_OVERLAY_ID",
    "Picture": "FlickFrame",
    "SCALED_FRAMES_BYTES": "SCALED_FRAMES_BYTES",
    "black_bgra": "black_bgra",
    "loading_notice_bgra": "loading_notice_bgra",
    "scaled_bgra": "scaled_bgra",
    "tile_rects": "tile_rects",
}

__getattr__ = old_name_getter("funestra.flick_overlay", _RENAMED)

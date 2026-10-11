"""What :mod:`funestra.flick_folder` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

__all__: list[str] = []

_RENAMED = {
    "SUPPORTED_VIDEO_EXTS": "SUPPORTED_VIDEO_EXTS",
    "cache_dir_for_clips_folder": "cache_dir_for_flicks_folder",
    "flat_clips_in": "flat_flicks_in",
    "move_clip_to_weird": "move_flick_to_weird",
    "scan_clips": "scan_flicks",
    "vr_clips_in": "vr_flicks_in",
    "weird_dir_for_clips_folder": "weird_dir_for_flicks_folder",
    "weird_folder_for": "weird_folder_for",
}

__getattr__ = old_name_getter("funestra.flick_folder", _RENAMED)

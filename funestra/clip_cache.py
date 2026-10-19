"""What :mod:`funestra.flick_cache` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "ClipCacheStore": "FlickCacheStore",
    "DecodeRequestState": "DecodeRequestState",
    "trim_path_lru_cache": "trim_path_lru_cache",
}

__getattr__ = old_name_getter("funestra.flick_cache", _RENAMED)

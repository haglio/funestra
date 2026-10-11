"""What :mod:`funestra.mpv_engine` was called before the Player became the
Funestra, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

__all__: list[str] = []

_RENAMED = {
    "MpvPlayer": "MpvEngine",
    "_import_mpv": "_import_mpv",
}

__getattr__ = old_name_getter("funestra.mpv_engine", _RENAMED)

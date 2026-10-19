"""What :mod:`funestra.render_engine` was called before the Player became
the Funestra, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "MpvRenderPlayer": "MpvRenderEngine",
}

__getattr__ = old_name_getter("funestra.render_engine", _RENAMED)

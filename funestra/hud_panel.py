"""What :mod:`funestra.hud` was called before the HUD stopped being called a
panel, kept for the checkouts that still import it."""
from __future__ import annotations

from . import hud
from .renamed import old_name_getter

_RENAMED = {name: name for name in vars(hud) if not name.startswith("_")} | {"HudPanel": "Hud"}

__getattr__ = old_name_getter("funestra.hud", _RENAMED)

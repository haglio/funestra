"""What :mod:`funestra.hud` was called before the HUD stopped being called a
panel, kept for the Fun Time branches that still import it."""
from __future__ import annotations

from typing import Any

from . import hud


def __getattr__(name: str) -> Any:
    return hud.Hud if name == "HudPanel" else getattr(hud, name)

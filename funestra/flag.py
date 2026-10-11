"""A boolean two parts of an app share: whether the room is paused, whether the HUD is up."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Flag",
]

@dataclass
class Flag:
    on: bool = False

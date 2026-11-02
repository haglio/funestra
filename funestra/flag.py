"""A boolean two parts of an app share: whether the app is paused, whether the HUD is up."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Flag:
    on: bool = False

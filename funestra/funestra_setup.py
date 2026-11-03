from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .funestra import Channels, HudSurface, Users, UsersFrames
    from .host_controls import HostControls
    from .playlist import PlaylistItem
    from .radio import Tuner
    from .satellite_hud import HudModel
    from .volume import VolumeHud


def nothing_of_its_own(_command: str) -> bool:
    return False


class FunestraSetup(NamedTuple):
    channels: Channels
    playlist: list[PlaylistItem]
    tcode: object = None
    audible: bool = True
    tiles: bool = False
    locked: bool = False
    sound_is_the_rooms: bool = False
    users: Users | None = None
    hud: Callable[[], HudModel | None] | None = None
    muted: bool = True
    hud_surface: HudSurface | None = None
    users_frames: UsersFrames | None = None
    window_verbs: Callable[[str], bool] = nothing_of_its_own
    host_controls: HostControls | None = None
    radio: Tuner | None = None
    on_volume_moved: Callable[[VolumeHud], None] | None = None
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def of(cls, setup: FunestraSetup | None, old: dict) -> FunestraSetup:
        return cls(**old) if setup is None else setup

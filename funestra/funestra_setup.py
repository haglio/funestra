from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple

from .play_points import PlayPoints
from .playback import funscripts_of, points_of_interest_of
from .playback_setup import PlaybackSetup

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

    def playback_setup(self, start_paused: bool) -> PlaybackSetup:
        channels, playlist, tcode = self[:3]
        return PlaybackSetup(
            start_paused=start_paused, locked=self.locked,
            play_points=PlayPoints(channels.play_points),
            funscripts=funscripts_of(playlist),
            points_of_interest=points_of_interest_of(playlist), tcode=tcode)

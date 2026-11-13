from __future__ import annotations

from .flick_overlay import FlickFrame
from .hud_row import RowHud
from .playhead import framed_playhead, time_playhead, video_playhead
from .scrubber import Heatmap, MarkFollow
from .volume import VolumeHud


def frame_row(frame: FlickFrame, volume: VolumeHud) -> RowHud | None:
    if frame.count <= 0:
        return None
    return RowHud(position_ms=frame.elapsed_ms, duration_ms=frame.interval_ms,
                  volume=volume,
                  playhead=framed_playhead(frame.played, frame.count,
                                           frame.elapsed_ms, frame.interval_ms),
                  loop=(frame.played, frame.count))


class ItemsRow:
    def __init__(self, playback, engine) -> None:
        self._playback = playback
        self._engine = engine
        self.strip = Heatmap()

    def row(self, volume: VolumeHud, track_width: int) -> RowHud:
        playback, engine = self._playback, self._engine
        mark = playback.mark
        follow = None if mark is None else MarkFollow(mark, playback.position_ms)
        self.strip.update(playback.showing, playback.current_funscript,
                          playback.duration_ms, track_width, follow)
        if playback.showing_image:
            elapsed_ms, pace_ms = engine.image_time or (0.0, 0.0)
            return RowHud(position_ms=elapsed_ms, duration_ms=pace_ms, volume=volume,
                          playhead=time_playhead(elapsed_ms, pace_ms))
        start_ms, end_ms = self.strip.window
        bounds = playback.ab_loop
        return RowHud(
            position_ms=playback.position_ms - start_ms,
            duration_ms=end_ms - start_ms,
            volume=volume,
            playhead=video_playhead(playback.position_ms, playback.duration_ms,
                                    engine.frame_rate),
            loop_bounds=None if bounds is None else (bounds[0] - start_ms,
                                                     bounds[1] - start_ms),
            record_in_ms=None if mark is None else mark - start_ms,
        )

    def seek_along_the_track(self, ms: float) -> None:
        if self._playback.showing_image:
            self._engine.seek_image(ms)
            return
        start_ms, _end_ms = self.strip.window
        self._playback.seek_to(start_ms + ms)

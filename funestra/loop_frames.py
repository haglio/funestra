from __future__ import annotations

from .scrubber import Heatmap, LoopThumbCapture, ThumbRow, loop_thumbnail_xys

IN_FRAME_OVERLAY_ID = 8
OUT_FRAME_OVERLAY_ID = 9


class LoopFrames:
    def __init__(self, engine) -> None:
        self._engine = engine
        self._frames = LoopThumbCapture()
        self._up = False

    def paint(self, playback, strip: Heatmap, track: tuple[int, int, int] | None,
              viewport_width: int) -> None:
        which = self._frames.needed(playback.ab_loop, playback.position_ms)
        if which is not None:
            self._frames.set(which, self._engine.screenshot_bgra())
        if playback.ab_loop is None or track is None:
            self.take_down()
            return
        x0, x1, top = track
        in_at, out_at = loop_thumbnail_xys(
            strip, self._frames, playback.ab_loop, ThumbRow((x0, x1), viewport_width, top))
        if in_at is not None:
            self._engine.overlay(IN_FRAME_OVERLAY_ID, *in_at, self._frames.in_thumb)
            self._up = True
        if out_at is not None:
            self._engine.overlay(OUT_FRAME_OVERLAY_ID, *out_at, self._frames.out_thumb)
            self._up = True

    def take_down(self) -> None:
        if not self._up:
            return
        self._up = False
        self._engine.remove_overlay(IN_FRAME_OVERLAY_ID)
        self._engine.remove_overlay(OUT_FRAME_OVERLAY_ID)

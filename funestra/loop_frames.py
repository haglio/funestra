from __future__ import annotations

from .scrubber import Heatmap, LoopThumbCapture, ThumbRow, loop_thumbnail_xys

IN_FRAME_OVERLAY_ID = 8
OUT_FRAME_OVERLAY_ID = 9


PASSES_BEFORE_ASKING_AGAIN = 15


class LoopFrames:
    def __init__(self, engine) -> None:
        self._engine = engine
        self._frames = LoopThumbCapture()
        self._up: dict[int, tuple[tuple[int, int], object]] = {}
        self._passes_to_wait = 0

    def paint(self, playback, strip: Heatmap, track: tuple[int, int, int] | None,
              viewport_width: int) -> None:
        which = self._frames.needed(playback.ab_loop, playback.position_ms)
        if which is not None:
            self._take_the_frame(which)
        if playback.ab_loop is None or track is None:
            self.take_down()
            return
        x0, x1, top = track
        in_at, out_at = loop_thumbnail_xys(
            strip, self._frames, playback.ab_loop, ThumbRow((x0, x1), viewport_width, top))
        if in_at is not None:
            self._hang(IN_FRAME_OVERLAY_ID, in_at, self._frames.in_thumb)
        if out_at is not None:
            self._hang(OUT_FRAME_OVERLAY_ID, out_at, self._frames.out_thumb)

    def _take_the_frame(self, which: str) -> None:
        if self._passes_to_wait:
            self._passes_to_wait -= 1
            return
        frame = self._engine.screenshot_bgra()
        self._frames.set(which, frame)
        if frame is None:
            self._passes_to_wait = PASSES_BEFORE_ASKING_AGAIN

    def _hang(self, ident: int, at: tuple[int, int], thumb) -> None:
        there = self._up.get(ident)
        if there is not None and there[0] == at and there[1] is thumb:
            return
        self._engine.overlay(ident, *at, thumb)
        self._up[ident] = (at, thumb)

    def take_down(self) -> None:
        if not self._up:
            return
        self._up = {}
        self._engine.remove_overlay(IN_FRAME_OVERLAY_ID)
        self._engine.remove_overlay(OUT_FRAME_OVERLAY_ID)

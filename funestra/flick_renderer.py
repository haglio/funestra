"""Which frame of the flick on screen is up, and putting a chosen one up.

The renderer knows the flick and the frame index; the surface it draws on is the
shell's, reached through the one ``blit_frame`` callable it is built with, so
the same renderer serves a pygame window and a headset texture.
"""
from __future__ import annotations

from pathlib import Path

from .renamed import answers_to_old_names

__all__ = [
    "FlickRenderController",
]

def display_index_for_phase(phase: float, frame_count: int) -> int:
    logical_index = min(int(phase * frame_count), frame_count - 1)
    return (frame_count - 1) - logical_index


@answers_to_old_names({
    "clip_store": "flick_store",
    "current_clip_entry": "current_flick_entry",
    "current_clip_path": "current_flick_path",
    "prepare_active_clip_for_current_size": "prepare_active_flick_for_current_size",
    "set_current_clip_path": "set_current_flick_path",
})
class FlickRenderController:
    def __init__(
        self,
        *,
        flick_store,
        blit_frame,
    ):
        self.flick_store = flick_store
        self.blit_frame = blit_frame
        self.current_flick_path: Path | None = None
        self.current_frame_index: int | None = None

    def set_current_flick_path(self, path: Path | None) -> None:
        self.current_flick_path = path
        self.current_frame_index = None

    def current_flick_entry(self):
        path = self.current_flick_path
        if path is None or path not in self.flick_store.flick_cache:
            return None
        return self.flick_store.flick_cache.get(path)

    @property
    def portrait(self) -> bool | None:
        entry = self.current_flick_entry()
        if entry is None or not entry["frames"]:
            return None
        height, width = entry["frames"][0].shape[:2]
        return height > width

    @property
    def playhead(self) -> tuple[int, int] | None:
        """How many of the loop's frames have played, of how many -- the dial
        and the frame count; None before a frame is up.  Counted up while the
        index counts down, the way :func:`display_index_for_phase` chose the
        frame."""
        entry = self.current_flick_entry()
        index = self.current_frame_index
        if entry is None or not entry["frames"] or index is None:
            return None
        count = len(entry["frames"])
        return max(0, count - 1 - index), count

    def prepare_active_flick_for_current_size(self) -> None:
        path = self.current_flick_path
        if path is None or path not in self.flick_store.flick_cache:
            return

        entry = self.flick_store.flick_entry_for(path)
        if entry["frames"]:
            self.show_frame_at(0)

    def show_frame_at(self, index: int) -> bool:
        """Put frame *index* of the flick on screen, or say there was none.

        Named for the choice rather than the drawing: the view's own
        ``blit_frame`` takes an image, and one name for both would leave a call
        site not saying which of the two it meant.
        """
        path = self.current_flick_path
        if path is None or path not in self.flick_store.flick_cache:
            return False

        entry = self.flick_store.flick_entry_for(path)
        frames = entry["frames"]
        if not frames or index < 0 or index >= len(frames):
            return False

        if self.current_frame_index != index:
            self.blit_frame(frames[index])
            self.current_frame_index = index
        return True

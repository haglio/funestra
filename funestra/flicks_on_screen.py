from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .flick_advance import FlickAdvanceState, tick_flick_advance
from .flick_renderer import display_index_for_phase


@dataclass(frozen=True)
class FlicksOnScreen:
    loader: Any
    renderer: Any
    selection: Any
    notifier: Any
    set_loading_text: Callable[[str | None], None]

    def adopt_whatever_finished_decoding(self) -> None:
        self.loader.adopt_loaded_flick_if_ready()
        self.loader.adopt_prefetch_if_ready()
        self.selection.adopt_pending_flick()

    @property
    def path(self) -> Path | None:
        return self.renderer.current_flick_path

    @property
    def portrait(self) -> bool | None:
        return self.renderer.portrait

    @property
    def frame_count(self) -> int:
        entry = self.renderer.current_flick_entry()
        return len(entry["frames"]) if entry and entry.get("frames") else 0

    @property
    def has_a_frame_up(self) -> bool:
        return self.renderer.current_frame_index is not None

    def show_the_frame_at(self, phase: float) -> None:
        self.renderer.show_frame_at(display_index_for_phase(phase, self.frame_count))

    def advance(self, state: FlickAdvanceState, now: float, *, playing: bool) -> None:
        tick_flick_advance(
            state, now, playing=playing,
            on_screen_flick=self.path if self.frame_count else None,
            step_flick=self.selection.step)

    def heard(self, heard: bool) -> None:
        self.notifier.notify_visible(heard)

    def say_what_is_loading(self) -> None:
        pending = self.selection.pending_flick_name
        self.set_loading_text(f"Loading {pending}" if pending else None)

    def fetch_the_ones_nearby(self) -> None:
        self.selection.request_nearby_prefetch()

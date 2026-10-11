"""Which flick is up: the step, the switch and what is deferred between them.

A step to a flick that is already decoded switches at once; a step to one that
is not keeps the current flick playing and takes the new one up when its decode
lands, so the screen never goes blank waiting.  A condemned flick's successor, a
reordered folder's head, and the head of a narrowed folder that left out the
flick on screen are never deferred, because in each the point is to see the new
flick now.
"""
from __future__ import annotations

from pathlib import Path

from .renamed import answers_to_old_names, method_of

__all__ = [
    "FlickSelectionController",
]

@answers_to_old_names({
    "adopt_pending_clip": "adopt_pending_flick",
    "clip_store": "flick_store",
    "condemn_clip": "condemn_flick",
    "pending_clip_name": "pending_flick_name",
    "set_current_clip": "set_current_flick",
})
class FlickSelectionController:
    def __init__(
        self,
        *,
        sequence,
        flick_store,
        loader,
        renderer,
        notifier,
        condemn_flick=lambda _path: None,
    ):
        self.sequence = sequence
        self.flick_store = flick_store
        self.loader = loader
        self.renderer = renderer
        self.notifier = notifier
        self.condemn_flick = condemn_flick
        self._pending_path: Path | None = None

    @property
    def count(self) -> int:
        return self.sequence.count

    @property
    def current_number(self) -> int:
        return self.sequence.current_number

    @property
    def current_path(self) -> Path:
        return self.sequence.current_path

    @property
    def pending_flick_name(self) -> str | None:
        return self._pending_path.name if self._pending_path is not None else None

    def set_current_flick(self, path: Path) -> None:
        """Switch to a flick immediately, decoding it if its frames aren't in hand."""
        self._pending_path = None
        self._show(path)

        if self.loader.frames_ready(path):
            self._prepare_active_flick()
        else:
            self.loader.request_flick_load(path)

    def play(self, flick: Path) -> None:
        self.set_current_flick(self.sequence.play(flick))

    def reorder(self, flicks: list[Path]) -> None:
        """Browse *flicks* — the folder rescanned in a new order — from the top.

        Unlike :meth:`step` the switch is never deferred: the point of asking for
        an order is to be shown what it puts first, so the new head takes the
        screen at once and decodes there, exactly as a condemned flick's successor
        does.
        """
        self.set_current_flick(self.sequence.take_up(flicks))

    def narrow(self, flicks: list[Path]) -> None:
        on_screen = self.renderer.current_flick_path
        up = self.sequence.take_up(flicks, holding=on_screen)
        if up == on_screen:
            self._pending_path = None
        else:
            self.set_current_flick(up)

    def step(self, delta: int) -> None:
        """Advance to next/prev flick.  A flick whose frames are in hand -- up
        before, or decoded ahead of being asked for -- goes up at once;
        otherwise the current flick keeps playing and the switch waits for the
        decode."""
        path = self.sequence.step(delta)

        if self.loader.frames_ready(path):
            self._switch_to(path)
            return

        self._pending_path = path
        self.loader.request_flick_load(path)

    def condemn_current(self) -> bool:
        """Condemn the flick on screen and move on to the one after it.

        Unlike :meth:`step` there is nothing to defer to: the condemned flick is
        on its way out of the folder, so the successor takes the screen at once
        even if it still has to be decoded.  Returns False, having done nothing,
        when it is the only flick left — Genau has to keep something on screen.
        """
        condemned = self.sequence.current_path
        successor = self.sequence.remove_current()
        if successor is None:
            return False

        self.condemn_flick(condemned)
        self.flick_store.flick_cache.pop(condemned, None)
        self.set_current_flick(successor)
        return True

    def adopt_pending_flick(self) -> bool:
        """Called from the refresh loop.  If a deferred flick has finished
        decoding, switch the renderer to it and return True."""
        if self._pending_path is None:
            return False
        if not self.loader.frames_ready(self._pending_path):
            return False

        self._switch_to(self._pending_path)
        return True

    def request_nearby_prefetch(self) -> None:
        if self.sequence.count <= 1 or self.loader.is_busy:
            return

        for candidate in self.sequence.nearby_candidates():
            if not self.flick_store.holds(candidate):
                self.loader.request_prefetch(candidate)
                return

    def _show(self, path: Path) -> None:
        """Point the renderer at a flick and tell the world it is up."""
        self.renderer.set_current_flick_path(path)
        method_of(self.notifier, "notify_flick", old_name="notify_clip")(path)

    def _switch_to(self, path: Path) -> None:
        """Take up an already-cached flick, cancelling any deferred switch."""
        self._pending_path = None
        self._show(path)
        self._prepare_active_flick()

    def _prepare_active_flick(self) -> None:
        self.renderer.prepare_active_flick_for_current_size()

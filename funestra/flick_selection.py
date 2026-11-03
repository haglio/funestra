from __future__ import annotations

from pathlib import Path


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
        self._pending_path = None
        self._show(path)

        if self.loader.frames_ready(path):
            self._prepare_active_flick()
        else:
            self.loader.request_flick_load(path)

    def play(self, flick: Path) -> None:
        self.set_current_flick(self.sequence.play(flick))

    def play_next(self, flick: Path) -> None:
        self.sequence.play_next(flick)

    def reorder(self, flicks: list[Path]) -> None:
        self.set_current_flick(self.sequence.take_up(flicks))

    def narrow(self, flicks: list[Path]) -> None:
        on_screen = self.renderer.current_flick_path
        up = self.sequence.take_up(flicks, holding=on_screen)
        if up == on_screen:
            self._pending_path = None
        else:
            self.set_current_flick(up)

    def step(self, delta: int) -> None:
        path = self.sequence.step(delta)

        if self.loader.frames_ready(path):
            self._switch_to(path)
            return

        self._pending_path = path
        self.loader.request_flick_load(path)

    def condemn_current(self) -> bool:
        condemned = self.sequence.current_path
        successor = self.sequence.remove_current()
        if successor is None:
            return False

        self.condemn_flick(condemned)
        self.flick_store.flick_cache.pop(condemned, None)
        self.set_current_flick(successor)
        return True

    def adopt_pending_flick(self) -> bool:
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
        self.renderer.set_current_flick_path(path)
        self.notifier.notify_flick(path)

    def _switch_to(self, path: Path) -> None:
        self._pending_path = None
        self._show(path)
        self._prepare_active_flick()

    def _prepare_active_flick(self) -> None:
        self.renderer.prepare_active_flick_for_current_size()

from __future__ import annotations

from pathlib import Path

from funestra.flick_cache import DecodeRequestState, FlickCacheStore
from funestra.flick_loader import FlickLoadController
from funestra.flick_renderer import FlickRenderController
from funestra.flick_selection import FlickSelectionController
from funestra.flick_sequence import FlickSequenceController

CACHE_LIMIT = 2


class FakeNotifier:
    def __init__(self):
        self.flicks: list[Path] = []

    def notify_flick(self, path: Path) -> None:
        self.flicks.append(path)


class Pipeline:
    def __init__(self, *names: str, logger=None):
        self.decodes: list[str] = []
        self.blits: list[object] = []
        self._running: list[tuple] = []
        self.flick_store = FlickCacheStore(limit=CACHE_LIMIT)
        self.renderer = FlickRenderController(
            flick_store=self.flick_store, blit_frame=self.blits.append,
        )
        self.notifier = FakeNotifier()
        self.loader = FlickLoadController(
            flick_store=self.flick_store,
            load_state=DecodeRequestState(),
            prefetch_state=DecodeRequestState(),
            current_flick_path_getter=lambda: self.renderer.current_flick_path,
            decode_flick=self._decode,
            start_thread=self._start_decode,
            logger=logger if logger is not None else _SilentLog(),
            on_active_flick_loaded=self.renderer.prepare_active_flick_for_current_size,
        )
        self.selection = FlickSelectionController(
            sequence=FlickSequenceController([Path(name) for name in names]),
            flick_store=self.flick_store,
            loader=self.loader,
            renderer=self.renderer,
            notifier=self.notifier,
        )

    def _decode(self, path: Path) -> list[str]:
        self.decodes.append(path.name)
        return [f"{path.name}:0"]

    def _start_decode(self, *, target, args, name) -> None:
        self._running.append((target, args))

    def open_on(self, name: str) -> None:
        self.selection.set_current_flick(Path(name))

    def turn(self) -> None:
        running, self._running = self._running, []
        for target, args in running:
            target(*args)
        self.loader.adopt_loaded_flick_if_ready()
        self.loader.adopt_prefetch_if_ready()
        self.selection.adopt_pending_flick()
        self.selection.request_nearby_prefetch()

    @property
    def on_screen(self) -> str | None:
        path = self.renderer.current_flick_path
        return None if path is None else path.name


class _SilentLog:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def warning(self, *_args, **_kwargs) -> None:
        pass

    def exception(self, *_args, **_kwargs) -> None:
        pass


def test_a_flick_is_decoded_once_however_long_the_sweep_runs():
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")

    pipeline.open_on("on_screen.mp4")
    for _ in range(20):
        pipeline.turn()

    assert pipeline.decodes == ["on_screen.mp4", "after.mp4", "before.mp4"]


def test_an_advance_to_a_flick_decoded_ahead_puts_it_up_with_no_wait():
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")
    pipeline.open_on("on_screen.mp4")
    for _ in range(4):
        pipeline.turn()
    assert pipeline.decodes == ["on_screen.mp4", "after.mp4", "before.mp4"]

    pipeline.selection.step(1)

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.selection.pending_flick_name is None


def test_a_flick_that_goes_up_gives_its_decode_ahead_slot_back():
    pipeline = Pipeline("trash.mp4", "after.mp4", "third.mp4", "before.mp4")
    pipeline.open_on("trash.mp4")
    for _ in range(4):
        pipeline.turn()
    assert pipeline.decodes == ["trash.mp4", "after.mp4", "before.mp4"]

    assert pipeline.selection.condemn_current() is True
    for _ in range(20):
        pipeline.turn()

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.decodes == [
        "trash.mp4", "after.mp4", "before.mp4", "third.mp4"]


def test_an_advance_that_catches_a_decode_running_does_not_start_it_again():
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")
    pipeline.open_on("on_screen.mp4")
    pipeline.turn()
    assert pipeline.decodes == ["on_screen.mp4"]

    pipeline.selection.step(1)
    assert pipeline.selection.pending_flick_name == "after.mp4"
    pipeline.turn()

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.decodes == ["on_screen.mp4", "after.mp4"]

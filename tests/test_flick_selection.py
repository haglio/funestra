from __future__ import annotations

from pathlib import Path

import pytest

from funestra.flick_cache import FlickCacheStore
from funestra.flick_selection import FlickSelectionController, FlickSelectionParts
from funestra.flick_sequence import FlickSequenceController


class FakeLoader:
    def __init__(self, flick_store: FlickCacheStore, *, is_busy: bool = False):
        self.flick_store = flick_store
        self.is_busy = is_busy
        self.load_requests: list[Path] = []
        self.prefetch_requests: list[Path] = []

    def frames_ready(self, path: Path) -> bool:
        if path in self.flick_store.flick_cache:
            return True
        frames = self.flick_store.decoded_frame_cache.get(path)
        if frames is None:
            return False
        self.flick_store.flick_cache[path] = {"frames": frames}
        return True

    def request_flick_load(self, path: Path) -> None:
        self.load_requests.append(path)

    def request_prefetch(self, path: Path) -> None:
        self.prefetch_requests.append(path)


class FakeRenderer:
    def __init__(self):
        self.current_flick_path: Path | None = None
        self.prepare_calls = 0

    def set_current_flick_path(self, path: Path) -> None:
        self.current_flick_path = path

    def prepare_active_flick_for_current_size(self) -> None:
        self.prepare_calls += 1


class FakeNotifier:
    def __init__(self):
        self.flick_notifications: list[Path] = []

    def notify_flick(self, path: Path) -> None:
        self.flick_notifications.append(path)


def _build_controller(*paths: str, loader_busy: bool = False, condemn_flick=None, clock=None):
    flick_store = FlickCacheStore(limit=3)
    sequence = FlickSequenceController([Path(path) for path in paths])
    loader = FakeLoader(flick_store, is_busy=loader_busy)
    renderer = FakeRenderer()
    notifier = FakeNotifier()

    kwargs = {} if condemn_flick is None else {"condemn_flick": condemn_flick}
    if clock is not None:
        kwargs["clock"] = clock
    controller = FlickSelectionController(FlickSelectionParts(
        sequence=sequence,
        flick_store=flick_store,
        loader=loader,
        renderer=renderer,
        notifier=notifier,
        **kwargs,
    ))
    return controller, flick_store, loader, renderer, notifier


def test_set_current_flick_uses_cached_entry_without_loading():
    controller, flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    path = Path("b.mp4")
    flick_store.flick_cache[path] = {"frames": ["f0"]}

    controller.set_current_flick(path)

    assert renderer.current_flick_path == path
    assert renderer.prepare_calls == 1
    assert notifier.flick_notifications == [path]
    assert loader.load_requests == []


def test_set_current_flick_requests_load_for_uncached_entry():
    controller, _flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    path = Path("b.mp4")

    controller.set_current_flick(path)

    assert renderer.current_flick_path == path
    assert renderer.prepare_calls == 0
    assert notifier.flick_notifications == [path]
    assert loader.load_requests == [path]


def test_set_current_flick_takes_up_frames_decoded_ahead_without_loading():
    controller, flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    path = Path("b.mp4")
    flick_store.decoded_frame_cache[path] = ["f0"]

    controller.set_current_flick(path)

    assert renderer.current_flick_path == path
    assert renderer.prepare_calls == 1
    assert notifier.flick_notifications == [path]
    assert loader.load_requests == []


def test_step_switches_immediately_when_cached():
    controller, flick_store, _loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

    controller.step(1)

    assert controller.current_number == 2
    assert renderer.current_flick_path == Path("b.mp4")
    assert notifier.flick_notifications == [Path("b.mp4")]
    assert renderer.prepare_calls == 1
    assert controller.pending_flick_name is None


@pytest.mark.parametrize(("pressed_at", "number"), [(9.5, 2), (10.5, 3)])
def test_a_step_pressed_before_the_flick_moved_on_by_itself_is_already_done(pressed_at, number):
    controller, flick_store, *_ = _build_controller("a.mp4", "b.mp4", "c.mp4", clock=lambda: 10.0)
    for name in ("b.mp4", "c.mp4"):
        flick_store.flick_cache[Path(name)] = {"frames": ["f0"]}
    controller.advance()

    controller.step(1, pressed_at=pressed_at)

    assert controller.current_number == number


def test_step_waits_for_the_next_flick_to_decode_so_the_screen_never_goes_blank():
    controller, _flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)

    assert controller.current_number == 2
    assert renderer.current_flick_path == Path("a.mp4")
    assert notifier.flick_notifications == []
    assert loader.load_requests == [Path("b.mp4")]
    assert controller.pending_flick_name == "b.mp4"


def test_adopt_pending_flick_switches_when_loaded():
    controller, flick_store, _loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)

    flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}
    result = controller.adopt_pending_flick()

    assert result is True
    assert renderer.current_flick_path == Path("b.mp4")
    assert notifier.flick_notifications == [Path("b.mp4")]
    assert renderer.prepare_calls == 1
    assert controller.pending_flick_name is None


def test_a_flick_still_decoding_is_not_adopted():
    controller, _flick_store, _loader, renderer, _notifier = _build_controller("a.mp4", "b.mp4")
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)

    result = controller.adopt_pending_flick()

    assert result is False
    assert renderer.current_flick_path == Path("a.mp4")
    assert controller.pending_flick_name == "b.mp4"


def test_adopt_pending_flick_noop_when_no_pending():
    controller, _flick_store, _loader, _renderer, _notifier = _build_controller("a.mp4", "b.mp4")

    result = controller.adopt_pending_flick()

    assert result is False


def test_request_nearby_prefetch_uses_first_uncached_neighbor():
    controller, flick_store, loader, _renderer, _notifier = _build_controller(
        "a.mp4",
        "b.mp4",
        "c.mp4",
    )
    flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

    controller.request_nearby_prefetch()

    assert loader.prefetch_requests == [Path("c.mp4")]


def test_request_nearby_prefetch_skips_when_busy():
    controller, _flick_store, loader, _renderer, _notifier = _build_controller(
        "a.mp4",
        "b.mp4",
        loader_busy=True,
    )

    controller.request_nearby_prefetch()

    assert loader.prefetch_requests == []


def test_request_nearby_prefetch_is_empty_for_single_flick():
    controller, _flick_store, loader, _renderer, _notifier = _build_controller("solo.mp4")

    controller.request_nearby_prefetch()

    assert loader.prefetch_requests == []


class TestReorder:
    def test_takes_the_head_of_the_new_order_at_once(self):
        controller, _store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
        renderer.current_flick_path = Path("a.mp4")

        controller.reorder([Path("newest.mp4"), Path("older.mp4")])

        assert renderer.current_flick_path == Path("newest.mp4")
        assert notifier.flick_notifications == [Path("newest.mp4")]
        assert loader.load_requests == [Path("newest.mp4")]
        assert controller.pending_flick_name is None
        assert controller.count == 2

    def test_drops_a_switch_that_was_still_waiting_to_load(self):
        controller, flick_store, _loader, renderer, _notifier = _build_controller("a.mp4", "b.mp4")
        renderer.current_flick_path = Path("a.mp4")
        controller.step(1)
        assert controller.pending_flick_name == "b.mp4"

        controller.reorder([Path("newest.mp4")])
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

        assert controller.adopt_pending_flick() is False
        assert renderer.current_flick_path == Path("newest.mp4")


class TestNarrow:
    def test_the_flick_on_screen_stays_where_it_survived(self):
        controller, _store, _loader, renderer, notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4")
        controller.set_current_flick(Path("b.mp4"))
        notifier.flick_notifications.clear()

        controller.narrow([Path("c.mp4"), Path("b.mp4")])

        assert renderer.current_flick_path == Path("b.mp4")
        assert notifier.flick_notifications == []
        assert controller.current_path == Path("b.mp4")
        assert controller.count == 2

    def test_a_flick_on_screen_that_was_dropped_gives_way_to_the_head_at_once(self):
        controller, _store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
        controller.set_current_flick(Path("a.mp4"))
        notifier.flick_notifications.clear()

        controller.narrow([Path("c.mp4"), Path("b.mp4")])

        assert renderer.current_flick_path == Path("c.mp4")
        assert notifier.flick_notifications == [Path("c.mp4")]
        assert loader.load_requests[-1] == Path("c.mp4")

    def test_a_step_still_waiting_to_load_is_dropped_with_the_list_it_stepped_along(self):
        controller, flick_store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4")
        controller.set_current_flick(Path("a.mp4"))
        controller.step(1)
        assert controller.pending_flick_name == "b.mp4"

        controller.narrow([Path("a.mp4"), Path("c.mp4")])
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

        assert controller.adopt_pending_flick() is False
        assert renderer.current_flick_path == Path("a.mp4")


class TestDiscardCurrent:
    def test_condemns_the_flick_and_moves_on_to_the_next(self):
        condemned: list[Path] = []
        controller, flick_store, _loader, renderer, notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4", condemn_flick=condemned.append,
        )
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

        assert controller.condemn_current() is True

        assert condemned == [Path("a.mp4")]
        assert controller.count == 2
        assert renderer.current_flick_path == Path("b.mp4")
        assert notifier.flick_notifications == [Path("b.mp4")]

    def test_a_condemned_flick_s_successor_goes_up_at_once_without_waiting_to_be_decoded(self):
        controller, _store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4", condemn_flick=lambda _path: None,
        )

        controller.condemn_current()

        assert renderer.current_flick_path == Path("b.mp4")

    def test_a_trash_aimed_at_a_flick_already_gone_from_the_screen_condemns_that_one_and_leaves_the_screen_be(
            self):
        condemned: list[Path] = []
        controller, flick_store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4", condemn_flick=condemned.append,
        )
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}
        controller.step(1)

        assert controller.condemn(Path("a.mp4")) is True

        assert condemned == [Path("a.mp4")]
        assert (controller.count, controller.current_path) == (2, Path("b.mp4"))
        assert renderer.current_flick_path == Path("b.mp4")

    def test_a_trash_aimed_at_the_flick_on_screen_condemns_it_as_a_bare_trash_does(self):
        condemned: list[Path] = []
        controller, _store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", condemn_flick=condemned.append,
        )

        assert controller.condemn(Path("a.mp4")) is True

        assert condemned == [Path("a.mp4")]
        assert renderer.current_flick_path == Path("b.mp4")

    def test_a_trash_aimed_at_a_flick_no_longer_listed_condemns_nothing(self):
        condemned: list[Path] = []
        controller, _store, _loader, _renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", condemn_flick=condemned.append,
        )

        assert controller.condemn(Path("gone.mp4")) is False

        assert (condemned, controller.count) == ([], 2)

    def test_the_only_flick_is_never_condemned(self):
        condemned: list[Path] = []
        controller, _store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", condemn_flick=condemned.append,
        )

        assert controller.condemn_current() is False

        assert condemned == []
        assert controller.count == 1
        assert renderer.current_flick_path is None


class TestPlayingAPickedFlick:
    def test_the_pick_takes_the_screen_at_once_and_decodes_there(self):
        controller, _store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
        controller.set_current_flick(Path("a.mp4"))
        notifier.flick_notifications.clear()

        controller.play(Path("picked.mp4"))

        assert renderer.current_flick_path == Path("picked.mp4")
        assert notifier.flick_notifications == [Path("picked.mp4")]
        assert loader.load_requests[-1] == Path("picked.mp4")
        assert controller.current_path == Path("picked.mp4")

    def test_a_step_still_waiting_to_load_gives_way_to_the_pick(self):
        controller, flick_store, _loader, renderer, _notifier = _build_controller(
            "a.mp4", "b.mp4", "c.mp4")
        controller.set_current_flick(Path("a.mp4"))
        controller.step(1)

        controller.play(Path("c.mp4"))
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

        assert controller.adopt_pending_flick() is False
        assert renderer.current_flick_path == Path("c.mp4")


def test_a_flick_put_next_leaves_the_one_on_screen_up_and_is_decoded_ahead():
    controller, _store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    controller.set_current_flick(Path("a.mp4"))
    notifier.flick_notifications.clear()

    controller.play_next(Path("new.mp4"))
    controller.request_nearby_prefetch()

    assert renderer.current_flick_path == Path("a.mp4")
    assert notifier.flick_notifications == []
    assert loader.prefetch_requests == [Path("new.mp4")]

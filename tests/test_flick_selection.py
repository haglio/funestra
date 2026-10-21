from __future__ import annotations

from pathlib import Path

from funestra.flick_cache import FlickCacheStore
from funestra.flick_selection import FlickSelectionController
from funestra.flick_sequence import FlickSequenceController


class FakeLoader:
    def __init__(self, flick_store: FlickCacheStore, *, is_busy: bool = False):
        self.flick_store = flick_store
        self.is_busy = is_busy
        self.load_requests: list[Path] = []
        self.prefetch_requests: list[Path] = []

    def frames_ready(self, path: Path) -> bool:
        """The real loader's one question, answered the way it answers it: in
        the flicks-on-screen cache, or decoded ahead and moved across by the
        asking."""
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


def _build_controller(*paths: str, loader_busy: bool = False, condemn_flick=None):
    flick_store = FlickCacheStore(limit=3)
    sequence = FlickSequenceController([Path(path) for path in paths])
    loader = FakeLoader(flick_store, is_busy=loader_busy)
    renderer = FakeRenderer()
    notifier = FakeNotifier()

    kwargs = {} if condemn_flick is None else {"condemn_flick": condemn_flick}
    controller = FlickSelectionController(
        sequence=sequence,
        flick_store=flick_store,
        loader=loader,
        renderer=renderer,
        notifier=notifier,
        **kwargs,
    )
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
    """A flick decoded ahead of being asked for is as ready as one that has been
    up before: it goes straight on screen, and nothing is decoded again."""
    controller, flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    path = Path("b.mp4")
    flick_store.decoded_frame_cache[path] = ["f0"]

    controller.set_current_flick(path)

    assert renderer.current_flick_path == path
    assert renderer.prepare_calls == 1
    assert notifier.flick_notifications == [path]
    assert loader.load_requests == []


def test_step_switches_immediately_when_cached():
    controller, flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

    controller.step(1)

    assert controller.current_number == 2
    assert renderer.current_flick_path == Path("b.mp4")
    assert notifier.flick_notifications == [Path("b.mp4")]
    assert renderer.prepare_calls == 1
    assert controller.pending_flick_name is None


def test_step_defers_switch_when_not_cached():
    controller, _flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    # Set initial flick on renderer
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)

    assert controller.current_number == 2
    # Renderer still shows old flick
    assert renderer.current_flick_path == Path("a.mp4")
    # No notification yet — deferred
    assert notifier.flick_notifications == []
    # Load was requested
    assert loader.load_requests == [Path("b.mp4")]
    # Pending flick name is set
    assert controller.pending_flick_name == "b.mp4"


def test_adopt_pending_flick_switches_when_loaded():
    controller, flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)  # defers — b.mp4 not cached

    # Simulate async load completing
    flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}
    result = controller.adopt_pending_flick()

    assert result is True
    assert renderer.current_flick_path == Path("b.mp4")
    assert notifier.flick_notifications == [Path("b.mp4")]
    assert renderer.prepare_calls == 1
    assert controller.pending_flick_name is None


def test_a_flick_still_decoding_is_not_adopted():
    controller, _flick_store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
    renderer.current_flick_path = Path("a.mp4")

    controller.step(1)  # defers

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
        """Never deferred the way a step is: the point of asking for an order is
        to be shown what it puts first, so the head takes the screen and decodes
        there rather than after the flick that was up."""
        controller, _store, loader, renderer, notifier = _build_controller("a.mp4", "b.mp4")
        renderer.current_flick_path = Path("a.mp4")

        controller.reorder([Path("newest.mp4"), Path("older.mp4")])

        assert renderer.current_flick_path == Path("newest.mp4")
        assert notifier.flick_notifications == [Path("newest.mp4")]
        assert loader.load_requests == [Path("newest.mp4")]
        assert controller.pending_flick_name is None
        assert controller.count == 2

    def test_drops_a_switch_that_was_still_waiting_to_load(self):
        """The deferred flick belongs to the order just replaced, so adopting it
        afterwards would put the old browse back on screen."""
        controller, flick_store, _loader, renderer, _notifier = _build_controller("a.mp4", "b.mp4")
        renderer.current_flick_path = Path("a.mp4")
        controller.step(1)
        assert controller.pending_flick_name == "b.mp4"

        controller.reorder([Path("newest.mp4")])
        flick_store.flick_cache[Path("b.mp4")] = {"frames": ["f0"]}

        assert controller.adopt_pending_flick() is False
        assert renderer.current_flick_path == Path("newest.mp4")


class TestNarrow:
    """The folder rescanned under a narrower choice of flick, which a reloaded
    playlist answers by keeping the item on screen where it survived."""

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

    def test_the_only_flick_is_never_condemned(self):
        """Genau always has something on screen, so the last flick is untouchable."""
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

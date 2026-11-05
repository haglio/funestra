from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from funestra.flick_cache import DecodeRequestState, FlickCacheStore
from funestra.flick_loader import FlickLoadController, FlickLoadParts


class JobStarter:
    def __init__(self):
        self.calls: list[tuple[object, tuple[Path, int], str]] = []

    def __call__(self, *, target, args: tuple[Path, int], name: str) -> None:
        self.calls.append((target, args, name))


def _make_loader(*, current_flick_path: Path | None = None):
    flick_store = FlickCacheStore(limit=2)
    load_state = DecodeRequestState()
    prefetch_state = DecodeRequestState()
    starter = JobStarter()
    logger = MagicMock()
    active_loaded: list[str] = []

    controller = FlickLoadController(FlickLoadParts(
        flick_store=flick_store,
        load_state=load_state,
        prefetch_state=prefetch_state,
        current_flick_path_getter=lambda: current_flick_path,
        decode_flick=lambda _path: ["f0", "f1"],
        start_thread=starter,
        logger=logger,
        on_active_flick_loaded=lambda: active_loaded.append("ready"),
    ))
    return controller, flick_store, load_state, prefetch_state, starter, logger, active_loaded


def test_request_flick_load_adopts_decoded_frames_without_starting_job():
    path = Path("demo.mp4")
    controller, flick_store, _load_state, _prefetch_state, starter, _logger, _active_loaded = _make_loader()
    flick_store.decoded_frame_cache[path] = ["f0", "f1"]

    controller.request_flick_load(path)

    assert path in flick_store.flick_cache
    assert starter.calls == []


def test_request_flick_load_starts_background_job():
    path = Path("demo.mp4")
    controller, _flick_store, load_state, _prefetch_state, starter, _logger, _active_loaded = _make_loader()

    controller.request_flick_load(path)

    assert load_state.loading is True
    assert [(call[1], call[2]) for call in starter.calls] == [((path, 1), "genau-loader")]


def test_adopt_loaded_flick_if_ready_promotes_frames_and_notifies_current_flick_on_the_frame_loop_s_thread_since_a_decode_thread_never_hands_its_frames_over_itself():
    path = Path("demo.mp4")
    controller, flick_store, load_state, _prefetch_state, _starter, _logger, active_loaded = _make_loader(current_flick_path=path)
    request_id = load_state.begin(path)
    load_state.record_success(path, ["f0", "f1"], request_id)

    controller.adopt_loaded_flick_if_ready()

    assert path in flick_store.flick_cache
    assert flick_store.flick_cache[path]["frames"] == ["f0", "f1"]
    assert active_loaded == ["ready"]


def test_adopt_loaded_flick_if_ready_takes_up_nothing_from_a_failed_decode():
    path = Path("demo.mp4")
    controller, flick_store, load_state, _prefetch_state, _starter, _logger, active_loaded = _make_loader(current_flick_path=path)
    request_id = load_state.begin(path)
    load_state.record_error(path, "boom", request_id)

    controller.adopt_loaded_flick_if_ready()

    assert path not in flick_store.flick_cache
    assert active_loaded == []


def test_request_prefetch_skips_when_busy():
    path = Path("demo.mp4")
    controller, _flick_store, load_state, _prefetch_state, starter, _logger, _active_loaded = _make_loader()
    load_state.begin(Path("other.mp4"))

    controller.request_prefetch(path)

    assert starter.calls == []


def test_request_prefetch_starts_background_job_for_uncached_path():
    path = Path("demo.mp4")
    controller, _flick_store, _load_state, prefetch_state, starter, _logger, _active_loaded = _make_loader()

    controller.request_prefetch(path)

    assert prefetch_state.loading is True
    assert [(call[1], call[2]) for call in starter.calls] == [((path, 1), "genau-prefetch")]


def test_adopt_prefetch_if_ready_caches_frames_without_active_notification():
    path = Path("demo.mp4")
    controller, flick_store, _load_state, prefetch_state, _starter, _logger, active_loaded = _make_loader()
    request_id = prefetch_state.begin(path)
    prefetch_state.record_success(path, ["f0"], request_id)

    controller.adopt_prefetch_if_ready()

    assert flick_store.decoded_frame_cache[path] == ["f0"]
    assert active_loaded == []


def test_a_flick_switched_to_while_it_was_decoding_ahead_goes_up_when_that_decode_lands():
    path = Path("demo.mp4")
    controller, flick_store, _load_state, prefetch_state, starter, _logger, active_loaded = _make_loader(
        current_flick_path=path)
    request_id = prefetch_state.begin(path)
    controller.request_flick_load(path)
    prefetch_state.record_success(path, ["f0", "f1"], request_id)

    controller.adopt_prefetch_if_ready()

    assert starter.calls == []
    assert flick_store.flick_cache[path]["frames"] == ["f0", "f1"]
    assert path not in flick_store.decoded_frame_cache
    assert active_loaded == ["ready"]


def test_a_flick_already_up_to_date_in_the_cache_is_ready_and_starts_no_job():
    path = Path("demo.mp4")
    controller, flick_store, _load_state, _prefetch_state, starter, _logger, _active_loaded = _make_loader()
    flick_store.cache_flick(path, ["f0"])

    assert controller.frames_ready(path) is True
    controller.request_flick_load(path)

    assert starter.calls == []


def test_taking_up_a_prefetched_flick_never_trims_out_the_flick_on_screen():
    on_screen, older, adopted = Path("a.mp4"), Path("b.mp4"), Path("c.mp4")
    controller, flick_store, _load_state, _prefetch_state, _starter, _logger, _active_loaded = _make_loader(
        current_flick_path=on_screen)
    flick_store.cache_flick(on_screen, ["f0"])
    flick_store.cache_flick(older, ["f0"])
    flick_store.decoded_frame_cache[adopted] = ["f0"]

    assert controller.frames_ready(adopted) is True

    assert on_screen in flick_store.flick_cache

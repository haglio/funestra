from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from funestra.flick_cache import (
    DecodeRequestState,
    FlickCacheStore,
    trim_path_lru_cache,
)


class TestDecodeRequestState:
    def test_begin_resets_previous_result_and_marks_loading(self):
        state = DecodeRequestState(
            request_id=2,
            loading=False,
            loaded_flick_path=Path("old.mp4"),
            loaded_frames=[1],
            load_error="boom",
            request_id_done=2,
        )

        request_id = state.begin(Path("new.mp4"))

        assert request_id == 3
        assert state.loading is True
        assert state.decoding_path == Path("new.mp4")
        assert state.loaded_flick_path is None
        assert state.loaded_frames is None
        assert state.load_error is None
        assert state.request_id_done is None

    def test_taking_a_finished_decode_hands_it_over_and_leaves_the_slot_free(self):
        state = DecodeRequestState(request_id=4, loading=True)
        state.record_success(Path("flick.mp4"), ["frame"], 4)

        result = state.take_completed_result()

        assert result == (Path("flick.mp4"), ["frame"], None)
        assert state.loading is False
        assert state.request_id_done is None

    def test_take_completed_result_ignores_stale_result_but_keeps_loading(self):
        state = DecodeRequestState(request_id=5, loading=True)
        state.record_error(Path("stale.mp4"), "bad", 4)

        result = state.take_completed_result()

        assert result is None
        assert state.loading is True
        assert state.request_id_done is None
        assert state.loaded_flick_path is None
        assert state.loaded_frames is None
        assert state.load_error is None


class TestFlickCacheStore:
    def test_flick_entry_for_marks_path_recently_used(self):
        store = FlickCacheStore(limit=2)
        first = Path("first.mp4")
        second = Path("second.mp4")
        store.flick_cache[first] = {"frames": []}
        store.flick_cache[second] = {"frames": []}

        entry = store.flick_entry_for(first)

        assert entry is store.flick_cache[first]
        assert list(store.flick_cache) == [second, first]

    def test_cache_decoded_frames_trims_unprotected_entries(self):
        store = FlickCacheStore(limit=2)
        first = Path("first.mp4")
        second = Path("second.mp4")
        third = Path("third.mp4")

        store.cache_decoded_frames(first, ["a"])
        store.cache_decoded_frames(second, ["b"])
        store.cache_decoded_frames(third, ["c"], protected_paths={second})

        assert list(store.decoded_frame_cache) == [second, third]

    def test_adopt_decoded_frames_populates_flick_cache_and_keeps_protected_current_flick(self):
        store = FlickCacheStore(limit=2)
        current = Path("current.mp4")
        next_path = Path("next.mp4")
        store.flick_cache[current] = {"frames": ["old"]}
        store.cache_decoded_frames(next_path, ["f1", "f2"])

        adopted = store.adopt_decoded_frames(next_path, protected_paths={current})

        assert adopted is True
        assert store.flick_cache[current]["frames"] == ["old"]
        assert store.flick_cache[next_path]["frames"] == ["f1", "f2"]

    def test_frames_that_were_never_decoded_are_not_adopted(self):
        store = FlickCacheStore(limit=1)

        assert store.adopt_decoded_frames(Path("missing.mp4")) is False



class TestTrimPathLruCache:
    def test_trims_oldest_unprotected_entries(self, tmp_path: Path):
        cache: OrderedDict[Path, str] = OrderedDict(
            [
                (tmp_path / "a", "a"),
                (tmp_path / "b", "b"),
                (tmp_path / "c", "c"),
            ]
        )

        trim_path_lru_cache(cache, limit=2)

        assert list(cache.values()) == ["b", "c"]

    def test_keeps_protected_entry_when_trimming(self, tmp_path: Path):
        protected = tmp_path / "a"
        cache: OrderedDict[Path, str] = OrderedDict(
            [
                (protected, "a"),
                (tmp_path / "b", "b"),
                (tmp_path / "c", "c"),
            ]
        )

        trim_path_lru_cache(cache, limit=2, protected_paths={protected})

        assert set(cache.values()) == {"a", "c"}

    def test_stops_when_all_entries_are_protected(self, tmp_path: Path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        cache: OrderedDict[Path, str] = OrderedDict([(a, "a"), (b, "b")])

        trim_path_lru_cache(cache, limit=1, protected_paths={a, b})

        assert set(cache.values()) == {"a", "b"}

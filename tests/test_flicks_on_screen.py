from __future__ import annotations

from pathlib import Path

from genau_fakes import FakeLoader, FakeNotifier, FakeRenderer, FakeSelection

from funestra.flick_advance import FlickAdvanceState
from funestra.flicks_on_screen import FlicksOnScreen


def _flicks(*, frames: int | None = 8, pending: str | None = None, frame_index: int | None = None):
    entry = None if frames is None else {"frames": [object()] * frames}
    renderer = FakeRenderer(path=Path("made-up.mp4"), entry=entry, current_frame_index=frame_index)
    selection = FakeSelection(pending_flick_name=pending)
    loading: list[str | None] = []
    flicks = FlicksOnScreen(FakeLoader(), renderer, selection, FakeNotifier(), loading.append)
    return flicks, renderer, selection, loading


def test_what_finished_decoding_is_adopted_from_the_loader_and_the_selection():
    flicks, _renderer, selection, _loading = _flicks()

    flicks.adopt_whatever_finished_decoding()

    assert (flicks.loader.loaded_adopt_calls, flicks.loader.prefetch_adopt_calls,
            selection.adopt_calls) == (1, 1, 1)


def test_a_flick_still_decoding_has_no_frames():
    assert _flicks(frames=None)[0].frame_count == 0
    assert _flicks(frames=0)[0].frame_count == 0
    assert _flicks(frames=8)[0].frame_count == 8


def test_the_frame_shown_is_the_one_at_that_point_of_the_loop():
    flicks, renderer, _selection, _loading = _flicks(frames=8)

    flicks.show_the_frame_at(0.25)

    assert renderer.display_calls == [5]
    assert flicks.has_a_frame_up


def test_before_any_frame_is_shown_none_is_up():
    assert not _flicks()[0].has_a_frame_up


def test_it_says_which_flick_is_loading_and_clears_the_words_when_none_is():
    loading_one, _r, _s, said = _flicks(pending="made-up two")
    loading_none, _r, _s, cleared = _flicks()

    loading_one.say_what_is_loading()
    loading_none.say_what_is_loading()

    assert (said, cleared) == (["Loading made-up two"], [None])


def test_the_flicks_nearby_are_fetched_through_the_selection():
    flicks, _renderer, selection, _loading = _flicks()

    flicks.fetch_the_ones_nearby()

    assert selection.prefetch_calls == 1


def test_being_heard_or_not_is_told_to_the_notifier():
    flicks, _renderer, _selection, _loading = _flicks()

    flicks.heard(False)

    assert flicks.notifier.visible_updates == [False]


class TestAdvancingToTheNextFlick:
    def test_an_unlocked_flick_whose_interval_is_up_steps_to_the_next(self):
        flicks, _renderer, selection, _loading = _flicks()
        state = FlickAdvanceState(locked=False, interval=1)

        for now in (10.0, 10.6, 11.2):
            flicks.advance(state, now, playing=True)

        assert selection.step_calls == [1]

    def test_a_flick_still_decoding_does_not_start_its_interval(self):
        flicks, _renderer, selection, _loading = _flicks(frames=None)
        state = FlickAdvanceState(locked=False, interval=1)

        for now in (10.0, 10.6, 11.2):
            flicks.advance(state, now, playing=True)

        assert selection.step_calls == []

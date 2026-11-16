from __future__ import annotations

from funestra.on_screen_history import OnScreenHistory


class TestPathAtSoACommandThatArrivesLateIsAppliedToWhatWasShowingWhenItWasGiven:
    def test_one_video_seen_all_session_is_the_whole_history(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        assert history.path_at(10.5) == "a.mp4"

    def test_a_transition_is_dated_to_the_midpoint_between_samples(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.observe("b.mp4", now=11.0)
        assert history.path_at(10.4) == "a.mp4"
        assert history.path_at(10.6) == "b.mp4"

    def test_a_change_seen_late_is_dated_by_how_long_the_new_video_has_played(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.observe("b.mp4", now=13.0, playing_for=0.5)
        assert history.path_at(12.4) == "a.mp4"
        assert history.path_at(12.6) == "b.mp4"

    def test_a_change_is_never_dated_before_the_last_sample_that_saw_the_old_video(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=8.0)
        history.observe("a.mp4", now=10.0)
        history.observe("b.mp4", now=13.0, playing_for=60.0)
        assert history.path_at(9.9) == "a.mp4"

    def test_a_change_that_was_asked_for_is_kept_however_late_it_was_seen(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.a_change_was_asked_for()
        history.observe("a.mp4", now=12.0)
        history.observe("b.mp4", now=13.0, playing_for=0.2)
        history.observe("c.mp4", now=14.0, playing_for=0.5)
        assert history.path_at(11.0) == "b.mp4"

    def test_only_the_change_after_the_ask_is_the_one_asked_for(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.a_change_was_asked_for()
        history.observe("b.mp4", now=13.0, playing_for=0.2)
        history.observe("c.mp4", now=14.0, playing_for=0.5)
        assert history.path_at(13.2) == "b.mp4"

    def test_forgets_what_was_shown_before_the_retention_window(self):
        history = OnScreenHistory(history_s=5.0)
        history.observe("a.mp4", now=0.0)
        history.observe("b.mp4", now=1.0)
        history.observe("c.mp4", now=10.0)
        assert history.path_at(0.2) == ""
        assert history.path_at(5.2) == "b.mp4"

    def test_a_failed_sample_is_not_a_transition(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.observe("", now=11.0)
        assert history.path_at(11.5) == "a.mp4"

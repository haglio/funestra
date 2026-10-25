"""Unit tests for what one Funestra had on screen over the last half minute."""
from __future__ import annotations

from funestra.on_screen_history import OnScreenHistory


class TestPathAt:
    def test_one_video_seen_all_session_is_the_whole_history(self):
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        assert history.path_at(10.5) == "a.mp4"

    def test_a_transition_is_dated_to_the_midpoint_between_samples(self):
        """Sampling only bounds a switch to the gap between two samples, so the
        history splits the difference — error is symmetric, not one-sided."""
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.observe("b.mp4", now=11.0)
        assert history.path_at(10.4) == "a.mp4"
        assert history.path_at(10.6) == "b.mp4"

    def test_forgets_what_was_shown_before_the_retention_window(self):
        """Only the recent past is kept — enough to cover any utterance — and
        what straddles the window's start survives so it stays queryable."""
        history = OnScreenHistory(history_s=5.0)
        history.observe("a.mp4", now=0.0)
        history.observe("b.mp4", now=1.0)   # b starts at 0.5
        history.observe("c.mp4", now=10.0)  # c starts at 5.5; cutoff is 5.0
        assert history.path_at(0.2) == ""       # 'a' has been forgotten
        assert history.path_at(5.2) == "b.mp4"  # 'b' still covers the window

    def test_a_failed_sample_is_not_a_transition(self):
        """A status carries no path before its Funestra has loaded anything —
        a gap in the record, not a change of what is shown."""
        history = OnScreenHistory()
        history.observe("a.mp4", now=10.0)
        history.observe("", now=11.0)
        assert history.path_at(11.5) == "a.mp4"

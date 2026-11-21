from __future__ import annotations

from pathlib import Path

from funestra.flick_frame_rates import UNREAD_FRAMES_PER_SECOND, FlickFrameRates


def test_a_flick_s_frame_rate_is_the_one_read_beside_its_frames():
    rates = FlickFrameRates(read=lambda _flick: 24.0)

    rates.read_ahead(Path("one.mp4"))

    assert rates.of(Path("one.mp4")) == 24.0


def test_a_flick_whose_frame_rate_was_never_read_plays_at_the_usual_rate():
    rates = FlickFrameRates(read=lambda _flick: 24.0)

    assert rates.of(Path("one.mp4")) == UNREAD_FRAMES_PER_SECOND


def test_a_frame_rate_that_cannot_be_read_leaves_the_usual_rate():
    def unreadable(_flick: Path) -> float:
        raise OSError("no such file")
    rates = FlickFrameRates(read=unreadable)

    rates.read_ahead(Path("one.mp4"))

    assert rates.of(Path("one.mp4")) == UNREAD_FRAMES_PER_SECOND


def test_only_the_last_few_flicks_frame_rates_are_kept():
    rates = FlickFrameRates(read=lambda _flick: 24.0)

    for number in range(20):
        rates.read_ahead(Path(f"{number}.mp4"))

    assert rates.of(Path("0.mp4")) == UNREAD_FRAMES_PER_SECOND
    assert rates.of(Path("19.mp4")) == 24.0

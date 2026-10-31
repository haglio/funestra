"""The readout at the left end of the timeline row: where the video is, and how long it runs."""
from __future__ import annotations

import numpy as np

from funestra.playhead import (
    FIGURE_SPACE,
    PlayheadHudPainter,
    flick_playhead,
    framed_playhead,
    readout_width,
    video_playhead,
)
from funestra.volume import CHIP_H


class TestWhatAVideosReadoutSays:
    def test_where_it_is_of_how_long_it_runs(self):
        assert video_playhead(42_000.0, 195_000.0, 0.0).text == "0:42 / 3:15"

    def test_its_frame_comes_first_with_how_many_there_are_then_the_time(self):
        """The way a flick's row reads, so the two modes differ only by the dial."""
        assert video_playhead(42_000.0, 195_000.0, 30.0).text == "frame 1260 / 5850 · 0:42 / 3:15"

    def test_its_frame_counts_up_in_the_room_its_last_frame_takes(self):
        assert video_playhead(300.0, 195_000.0, 30.0).text == f"frame {FIGURE_SPACE * 3}9 / 5850 · 0:00 / 3:15"

    def test_where_it_is_takes_the_shape_of_how_long_it_runs(self):
        """Every digit is as wide as every other in the face these are drawn in,
        so a clock with the length's own fields never moves along the row."""
        assert video_playhead(42_000.0, 2_715_000.0, 0.0).text == "00:42 / 45:15"

    def test_a_video_an_hour_long_counts_its_hours_on_both_sides(self):
        assert video_playhead(42_000.0, 6_315_000.0, 0.0).text == "0:00:42 / 1:45:15"

    def test_the_frame_is_the_one_mpv_counts_to(self):
        """libmpv's own estimated-frame-number, read off a 29.97fps test pattern
        paused on its last frame: 239.  The rate it reports is a float32, so
        truncating the product lands one frame short at 238."""
        playhead = video_playhead(7_974.633333333334, 8_008.0, 29.970029830932617)

        assert playhead.text == "frame 239 / 240 · 0:07 / 0:08"

    def test_a_video_whose_length_mpv_has_not_said_yet_has_no_readout(self):
        assert video_playhead(0.0, 0.0, 0.0) is None

    def test_a_video_whose_frame_rate_mpv_has_not_said_reads_its_clock_alone(self):
        assert video_playhead(1_000.0, 5_000.0, 0.0).text == "0:01 / 0:05"

    def test_the_widest_it_gets_is_what_it_says_on_the_last_frame(self):
        """The readout's room is sized to this, so a frame count that gains a
        digit partway through the video never pushes the clock along the row."""
        playhead = video_playhead(42_000.0, 2_715_000.0, 60.0)

        assert playhead.widest == "frame 162900 / 162900 · 45:15 / 45:15"


class TestWhatAClipsReadoutSays:
    def test_a_clip_has_frames_and_no_clock(self):
        """Genau's clips are frames the Robot Hand scrubs through, with no time in them."""
        playhead = flick_playhead(7, 20)

        assert (playhead.text, playhead.widest) == (f"frame {FIGURE_SPACE}7 / 20", "frame 20 / 20")

    def test_a_clip_still_decoding_has_no_readout(self):
        assert flick_playhead(0, 0) is None


class TestTheReadout:
    def test_it_is_the_words_alone_with_nothing_drawn_round_them(self):
        """He asked that the time and the frames not sit in a bubble as if
        they were a button: the HUD under them is ground enough."""
        bgra = PlayheadHudPainter().bgra(video_playhead(42_000.0, 195_000.0, 30.0))

        painted = bgra[:, :, 3] > 0
        assert painted.any()
        assert painted.mean() < 0.5
        assert not painted[0].any()
        assert not painted[-1].any()

    def test_it_is_as_tall_as_the_volume_chip_at_the_other_end_of_the_row(self):
        bgra = PlayheadHudPainter().bgra(video_playhead(42_000.0, 195_000.0, 30.0))

        assert bgra.shape[0] == CHIP_H

    def test_it_takes_the_room_its_widest_words_need(self):
        hud = video_playhead(0.0, 7_200_000.0, 60.0)

        assert PlayheadHudPainter().bgra(hud).shape[1] == readout_width(hud)
        assert readout_width(hud) > readout_width(video_playhead(0.0, 195_000.0, 30.0))

    def test_it_shows_where_the_video_has_got_to_without_changing_size(self):
        painter = PlayheadHudPainter()

        early = painter.bgra(video_playhead(1_000.0, 195_000.0, 30.0)).copy()
        later = painter.bgra(video_playhead(100_000.0, 195_000.0, 30.0))

        assert early.shape == later.shape
        assert not np.array_equal(early, later)

    def test_the_rest_of_its_line_holds_still_as_the_frame_gains_a_digit(self):
        painter = PlayheadHudPainter()

        nine = painter.bgra(framed_playhead(9, 20, 4_000, 10_000)).copy()
        ten = painter.bgra(framed_playhead(10, 20, 4_000, 10_000))
        half = nine.shape[1] // 2

        assert np.array_equal(nine[:, half:], ten[:, half:])

    def test_a_readout_that_has_not_moved_is_not_repainted(self):
        """Asked for on every frame a Funestra paints; a paused video's readout
        holds still for as long as the pause does."""
        painter = PlayheadHudPainter()
        hud = video_playhead(1_000.0, 195_000.0, 30.0)

        assert painter.bgra(hud) is painter.bgra(hud)

    def test_its_digits_sit_in_the_middle_of_the_row(self):
        """Centered on the digits' own ink.  Pillow's middle anchor centers the
        face's whole line, descender included, which sits a digit low."""
        bgra = PlayheadHudPainter().bgra(video_playhead(42_000.0, 195_000.0, 0.0))

        first_digit = bgra[:, :6, 3] > 128
        rows = np.flatnonzero(first_digit.any(axis=1))

        assert abs((rows[0] + rows[-1]) / 2 - (CHIP_H - 1) / 2) <= 0.5


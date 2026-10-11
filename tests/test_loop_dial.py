"""The dial beside a flick's track: a clock hand going round once per loop."""
from __future__ import annotations

import pytest

from funestra.loop_dial import DIAL_SIZE, LoopDialPainter, on_dial, turn_at

AT = (30, 1)  # where the row put the dial's top-left corner
CENTER = (AT[0] + DIAL_SIZE // 2, AT[1] + DIAL_SIZE // 2)


class TestAPressOnTheDial:
    def test_inside_the_dial_is_on_it_and_beside_it_is_not(self):
        cx, cy = CENTER

        assert on_dial(cx, cy, at=AT)
        assert on_dial(cx + DIAL_SIZE // 2 - 1, cy, at=AT)
        assert not on_dial(cx + DIAL_SIZE, cy, at=AT)
        assert not on_dial(cx, cy - DIAL_SIZE, at=AT)

    def test_twelve_o_clock_is_the_start_of_the_turn_and_the_hand_goes_clockwise(self):
        cx, cy = CENTER

        assert turn_at(cx, cy - 8, at=AT) == pytest.approx(0.0, abs=0.02)
        assert turn_at(cx + 8, cy, at=AT) == pytest.approx(0.25, abs=0.02)
        assert turn_at(cx, cy + 8, at=AT) == pytest.approx(0.5, abs=0.02)
        assert turn_at(cx - 8, cy, at=AT) == pytest.approx(0.75, abs=0.02)


class TestHowItIsDrawn:
    def _brightness(self, turn: float):
        bgra = LoopDialPainter().bgra(LoopDialPainter.hand(turn))
        assert bgra.shape == (DIAL_SIZE, DIAL_SIZE, 4)
        return bgra[:, :, :3].astype(int).sum(axis=2)  # row by column

    def test_the_hand_points_up_at_the_start_of_the_turn(self):
        ink = self._brightness(0.0)
        c = DIAL_SIZE // 2

        assert ink[c - 6, c] > ink[c + 6, c] + 150
        assert ink[c - 6, c] > ink[c, c + 6] + 150

    def test_and_a_quarter_turn_on_it_points_right(self):
        ink = self._brightness(0.25)
        c = DIAL_SIZE // 2

        assert ink[c, c + 6] > ink[c, c - 6] + 150
        assert ink[c, c + 6] > ink[c + 6, c] + 150

    def test_a_mark_at_twelve_and_a_dot_at_six_show_the_loops_two_ends(self):
        """With the hand pointing right, the top and the foot of the dial
        carry nothing but the marks."""
        ink = self._brightness(0.25)
        c = DIAL_SIZE // 2
        disc = ink[c + 3, c - 4]

        assert ink[2, c] > disc + 100
        assert ink[DIAL_SIZE - 3, c] > disc + 100
        assert ink[c - 3, c - 4] < disc + 40 and ink[c + 3, c + 4] < disc + 40

    def test_it_is_a_disc_that_leaves_its_corners_clear(self):
        alpha = LoopDialPainter().bgra(LoopDialPainter.hand(0.0))[:, :, 3]

        assert alpha[0, 0] == 0 and alpha[DIAL_SIZE - 1, DIAL_SIZE - 1] == 0
        assert alpha[DIAL_SIZE // 2, DIAL_SIZE // 2] > 0

    def test_it_is_repainted_only_when_the_hand_moves_a_step(self):
        assert LoopDialPainter.hand(0.0) == LoopDialPainter.hand(0.001)
        assert LoopDialPainter.hand(0.0) != LoopDialPainter.hand(0.25)
        assert LoopDialPainter.hand(1.0) == LoopDialPainter.hand(0.0)

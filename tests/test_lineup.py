from __future__ import annotations

from pathlib import Path

import pytest

from funestra.lineup import Lineup

ONE, TWO, THREE = Path("one.mp4"), Path("two.mp4"), Path("three.mp4")
TWO_UPSCALED = Path("two upscaled.mp4")
A_FRAME = Path("frame.png")


def test_a_lineup_of_nothing_is_refused():
    with pytest.raises(ValueError, match="empty"):
        Lineup([])


class TestWhatIsUp:
    def test_it_starts_on_its_first_video(self):
        lineup = Lineup([ONE, TWO])

        assert (lineup.index, lineup.current, lineup.showing, lineup.on_screen) == (
            0, ONE, ONE, ONE)

    def test_standing_past_the_end_comes_back_round(self):
        lineup = Lineup([ONE, TWO, THREE])

        lineup.stand_at(4)
        assert lineup.current == TWO

        lineup.stand_at(-1)
        assert lineup.current == THREE

    def test_the_caller_s_list_is_copied_both_ways(self):
        given = [ONE, TWO]
        lineup = Lineup(given)
        given.append(THREE)
        lineup.videos.append(THREE)

        assert lineup.videos == [ONE, TWO]
        assert len(lineup) == 2


class TestAFramePutUp:
    def test_it_is_what_is_on_screen_while_the_video_stays_the_one_showing(self):
        lineup = Lineup([ONE, TWO])

        lineup.put_up(A_FRAME)

        assert (lineup.on_screen, lineup.showing, lineup.an_image_was_put_up) == (
            A_FRAME, ONE, True)

    def test_taking_it_down_says_whether_one_was_up(self):
        lineup = Lineup([ONE, TWO])
        assert lineup.take_down_the_frame() is False

        lineup.put_up(A_FRAME)

        assert lineup.take_down_the_frame() is True
        assert lineup.on_screen == ONE

    def test_standing_somewhere_else_takes_it_down(self):
        lineup = Lineup([ONE, TWO])
        lineup.put_up(A_FRAME)

        lineup.stand_at(1)

        assert (lineup.on_screen, lineup.an_image_was_put_up) == (TWO, False)


class TestRolling:
    def test_the_roll_puts_up_the_next_video_and_comes_round_at_the_end(self):
        lineup = Lineup([ONE, TWO])
        assert lineup.what_the_roll_puts_up == TWO

        lineup.roll()
        assert (lineup.current, lineup.what_the_roll_puts_up) == (TWO, ONE)

        lineup.roll()
        assert lineup.current == ONE

    def test_a_roll_takes_a_frame_down(self):
        lineup = Lineup([ONE, TWO])
        lineup.put_up(A_FRAME)

        lineup.roll()

        assert (lineup.on_screen, lineup.an_image_was_put_up) == (TWO, False)

    def test_a_lineup_of_one_rolls_onto_what_is_on_screen_frame_and_all(self):
        lineup = Lineup([ONE])
        lineup.put_up(A_FRAME)
        assert lineup.what_the_roll_puts_up == A_FRAME

        lineup.roll()

        assert (lineup.on_screen, lineup.an_image_was_put_up) == (A_FRAME, True)


class TestVersions:
    def test_stepping_shows_the_next_version_of_the_video_that_is_up(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)

        assert lineup.step_version([TWO, TWO_UPSCALED], 1) is True

        assert (lineup.current, lineup.showing) == (TWO, TWO_UPSCALED)

    def test_stepping_back_onto_the_video_itself_forgets_the_choice(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)

        lineup.step_version([TWO, TWO_UPSCALED], 1)

        assert lineup.showing == TWO

    def test_a_video_with_one_version_or_one_not_among_them_does_not_step(self):
        lineup = Lineup([ONE, TWO])

        assert lineup.step_version([ONE], 1) is False
        assert lineup.step_version([TWO, TWO_UPSCALED], 1) is False

    def test_the_version_chosen_is_what_shows_when_the_lineup_comes_back_to_it(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)
        lineup.stand_at(0)

        assert lineup.what_the_roll_puts_up == TWO_UPSCALED

    def test_forgetting_the_versions_shows_every_video_as_itself(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)

        lineup.forget_versions()

        assert lineup.showing == TWO


class TestPuttingAVideoNext:
    def test_a_new_video_goes_in_after_the_one_that_is_up(self):
        lineup = Lineup([ONE, TWO])

        lineup.put_next(THREE)

        assert (lineup.videos, lineup.current) == ([ONE, THREE, TWO], ONE)

    def test_a_listed_video_moves_to_be_next_and_the_one_up_stays_up(self):
        lineup = Lineup([ONE, TWO, THREE])
        lineup.stand_at(2)

        lineup.put_next(ONE)

        assert (lineup.videos, lineup.current) == ([TWO, THREE, ONE], THREE)

    def test_where_a_video_is_listed(self):
        lineup = Lineup([ONE, TWO])

        assert (lineup.place_of(TWO), lineup.place_of(THREE)) == (1, None)


class TestDiscarding:
    def test_the_video_that_is_up_leaves_with_the_version_chosen_for_it(self):
        lineup = Lineup([ONE, TWO, THREE])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)

        assert lineup.discard() is True

        assert lineup.videos == [ONE, THREE]

    def test_the_last_video_cannot_be_discarded(self):
        lineup = Lineup([ONE])

        assert lineup.discard() is False
        assert lineup.videos == [ONE]


class TestTakingANewList:
    def test_starting_over_forgets_the_versions(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)

        lineup.start_over_with([TWO, THREE])
        lineup.stand_at(0)

        assert lineup.showing == TWO

    def test_starting_over_with_nothing_is_refused(self):
        with pytest.raises(ValueError, match="empty"):
            Lineup([ONE]).start_over_with([])

    def test_a_list_that_has_the_video_that_is_up_stands_on_it_with_its_version(self):
        lineup = Lineup([ONE, TWO])
        lineup.stand_at(1)
        lineup.step_version([TWO, TWO_UPSCALED], 1)

        assert lineup.take([THREE, TWO]) is True

        assert (lineup.index, lineup.showing) == (1, TWO_UPSCALED)

    def test_a_list_that_has_the_frame_put_up_stands_on_it_as_a_video_of_its_own(self):
        lineup = Lineup([ONE, TWO])
        lineup.put_up(A_FRAME)

        assert lineup.take([THREE, A_FRAME]) is True

        assert (lineup.current, lineup.on_screen) == (A_FRAME, A_FRAME)

    def test_a_list_with_neither_is_taken_and_says_it_could_not_stand(self):
        lineup = Lineup([ONE, TWO])

        assert lineup.take([THREE]) is False

        assert lineup.videos == [THREE]

    def test_taking_nothing_is_refused(self):
        with pytest.raises(ValueError, match="empty"):
            Lineup([ONE]).take([])

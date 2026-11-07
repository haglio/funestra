from __future__ import annotations

from funestra.descent_latch import _CROWDED, DescentChoice, DescentLatch, DriveKey
from funestra.osr2_visualizer import DriveHud

TURN_MS = 3_000
KEY = DriveKey(center=50, amplitude=100, speed=50, let_go=None)


def _choice(top: float = 0.35, touch: int | None = 3_600) -> DescentChoice:
    return DescentChoice(key=KEY, top=top, touch=touch)


class TestTheWaveAChoiceWasCutFrom:
    def test_a_key_is_the_five_fields_that_change_only_when_the_wave_itself_does_and_not_every_frame(self):
        publish = DriveHud(center=50, amplitude=100, speed=40, let_go=0.44, max_intensity=30)

        assert DriveKey.cut_from(publish) == DriveKey(
            center=50, amplitude=100, speed=40, let_go=0.44, max_intensity=30)

    def test_what_moves_every_frame_is_not_in_the_key(self):
        a_frame = DriveHud(center=50, amplitude=100, speed=40, let_go=0.44, max_intensity=30,
                           position=1_200, waveform=(0.1, 0.2), slide=0.3, edge=0.7,
                           segments=((0, "robot_hand"),))
        the_next = DriveHud(center=50, amplitude=100, speed=40, let_go=0.44, max_intensity=30,
                            position=1_240, waveform=(0.2, 0.3), slide=0.4, edge=0.8,
                            segments=((0, "robot_hand"), (3, "funscript")))

        assert DriveKey.cut_from(a_frame) == DriveKey.cut_from(the_next)


class TestWhatIsHeldForATurn:
    def test_a_remembered_choice_comes_back_for_its_turn(self):
        latch = DescentLatch()

        latch.remember(TURN_MS, _choice(), stale_before=0)

        assert latch.choice_for(TURN_MS) == _choice()

    def test_a_turn_nothing_was_chosen_for_holds_nothing(self):
        assert DescentLatch().choice_for(TURN_MS) is None

    def test_choosing_again_for_a_turn_replaces_what_was_held(self):
        latch = DescentLatch()
        latch.remember(TURN_MS, _choice(), stale_before=0)

        latch.remember(TURN_MS, _choice(top=0.5, touch=3_800), stale_before=0)

        assert latch.choice_for(TURN_MS) == _choice(top=0.5, touch=3_800)

    def test_voiding_leaves_nothing_held_for_any_turn(self):
        latch = DescentLatch()
        latch.remember(TURN_MS, _choice(), stale_before=0)

        latch.void_all()

        assert latch.choice_for(TURN_MS) is None


class TestTurnsThePlayheadHasPassed:
    CROWD = range(1_000, 1_000 * (_CROWDED + 2), 1_000)

    def test_a_turn_left_over_goes_once_there_are_enough_to_scan(self):
        latch = DescentLatch()

        for turn in self.CROWD:
            latch.remember(turn, _choice(), stale_before=9_000)

        assert latch.choice_for(1_000) is None

    def test_the_turns_still_in_play_stay(self):
        latch = DescentLatch()

        for turn in self.CROWD:
            latch.remember(turn, _choice(), stale_before=9_000)

        assert latch.choice_for(9_000) == _choice()
        assert latch.choice_for(17_000) == _choice()

    def test_a_handful_of_turns_is_never_scanned_so_a_turn_just_passed_is_still_there_for_a_status_read(self):
        latch = DescentLatch()

        latch.remember(1_000, _choice(), stale_before=9_000)

        assert latch.choice_for(1_000) == _choice()

"""What every Funestra's loop key steps through."""
from __future__ import annotations

from funestra.loop_cycle import ACTION, LOCK, OFF, SEED, next_stop, standing_at


def _any_group_loops(_axis: str) -> bool:
    return True


def test_four_presses_come_back_round_to_off():
    standing, stops = OFF, []
    for _press in range(4):
        standing = next_stop(standing, _any_group_loops)
        stops.append(standing)
    assert stops == [LOCK, SEED, ACTION, OFF]


def test_a_group_holding_only_what_is_on_screen_is_stepped_over():
    def only_the_action_column_loops(axis: str) -> bool:
        return axis == ACTION

    assert next_stop(LOCK, only_the_action_column_loops) == ACTION


def test_with_no_group_to_loop_the_key_locks_and_lets_go():
    def no_group_loops(_axis: str) -> bool:
        return False

    assert next_stop(OFF, no_group_loops) == LOCK
    assert next_stop(LOCK, no_group_loops) == OFF


def test_a_lock_with_no_loop_running_stands_at_the_lock():
    assert standing_at(loop=OFF, locked=True) == LOCK


def test_a_running_loop_stands_at_its_group_with_or_without_a_lock_inside_it():
    assert standing_at(loop=ACTION, locked=False) == ACTION
    assert standing_at(loop=SEED, locked=True) == SEED


def test_a_loop_it_does_not_know_reads_as_no_loop_at_all():
    assert standing_at(loop="sideways", locked=False) == OFF

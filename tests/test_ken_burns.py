"""The move across a still while it holds the screen: a zoom in, a zoom out, a pan."""
from __future__ import annotations

import itertools
import math
import random

import numpy as np
import pytest
from dealt_moves import CREEP, DRIFT, Deals

from funestra.ken_burns import (
    CLOSEST,
    ZOOMED_IN,
    Fit,
    KenBurns,
    Move,
    Moves,
    View,
    pan,
    zoom_in,
    zoom_out,
)


def assert_view(view: View, zoom: float, x: float, y: float) -> None:
    assert (view.zoom, view.align_x, view.align_y) == pytest.approx((zoom, x, y))


def test_a_zoom_in_starts_on_the_whole_picture_and_ends_closer_about_its_spot():
    move = zoom_in(-0.5, 0.25)

    assert_view(move.at(0.0), 1.0, -0.5, 0.25)
    assert_view(move.at(1.0), ZOOMED_IN, -0.5, 0.25)


def test_a_zoom_out_starts_close_about_its_spot_and_ends_on_the_whole_picture():
    move = zoom_out(0.75, -1.0)

    assert_view(move.at(0.0), ZOOMED_IN, 0.75, -1.0)
    assert_view(move.at(1.0), 1.0, 0.75, -1.0)


def test_a_pan_holds_the_picture_closer_and_crosses_it_to_the_opposite_corner():
    move = pan(1.0, -1.0)

    assert_view(move.at(0.0), ZOOMED_IN, 1.0, -1.0)
    assert_view(move.at(0.5), ZOOMED_IN, 0.0, 0.0)
    assert_view(move.at(1.0), ZOOMED_IN, -1.0, 1.0)


def test_a_move_grows_the_picture_by_the_same_factor_in_every_equal_stretch_of_it():
    move = Move(View(zoom=1.0), View(zoom=4.0))

    assert move.at(0.5).zoom == pytest.approx(2.0)


def kind_of(move: Move) -> str:
    if move.start.zoom < move.end.zoom:
        return "in"
    if move.start.zoom > move.end.zoom:
        return "out"
    return "pan"


def dealt(count: int, seed: int = 7) -> list[Move]:
    moves = Moves(random.Random(seed))
    return [moves.deal() for _ in range(count)]


def test_no_two_pictures_in_a_row_get_the_same_kind_of_move():
    kinds = [kind_of(move) for move in dealt(300)]

    assert all(one != next_one for one, next_one in itertools.pairwise(kinds))
    assert set(kinds) == {"in", "out", "pan"}


def test_a_picture_set_off_from_rest_zooms_in_and_the_next_one_moves_another_way():
    moves = Moves(random.Random(7))

    for _ in range(50):
        assert kind_of(moves.from_rest()) == "in"
        assert kind_of(moves.deal()) != "in"


def test_a_zoom_is_about_a_spot_anywhere_in_the_picture_not_only_its_middle():
    spots = [(move.start.align_x, move.start.align_y) for move in dealt(300) if kind_of(move) != "pan"]

    assert all(-1.0 <= x <= 1.0 and -1.0 <= y <= 1.0 for x, y in spots)
    assert max(abs(x) for x, _ in spots) > 0.9
    assert max(abs(y) for _, y in spots) > 0.9


def test_a_pan_sets_off_from_a_corner_so_it_crosses_whichever_way_the_picture_has_room():
    pans = [move for move in dealt(300) if kind_of(move) == "pan"]

    assert {(move.start.align_x, move.start.align_y) for move in pans} == {
        (-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)}


def paced(seconds: float = 4.0, *, now_s: float = 100.0, deals: Deals | None = None) -> KenBurns:
    still = KenBurns(deals or Deals(DRIFT))
    still.set_pace(seconds, now_s=now_s)
    still.new_picture(now_s=now_s)
    return still


def assert_along(view: View, move: Move, progress: float) -> None:
    expected = move.at(progress)
    assert_view(view, expected.zoom, expected.align_x, expected.align_y)


def test_a_picture_arrives_at_the_start_of_its_move():
    still = paced()

    assert_along(still.view(now_s=100.0), DRIFT, 0.0)


def test_halfway_through_the_hold_it_is_halfway_along_its_move():
    still = paced()

    assert_along(still.view(now_s=102.0), DRIFT, 0.5)


def test_a_picture_with_no_pace_is_held_whole_and_still():
    still = paced(0.0)  # a pace of nought holds the picture

    assert still.view(now_s=1000.0) == View()


def test_a_frozen_room_holds_the_picture_where_its_move_had_got_to():
    still = paced()

    still.set_paused(True, now_s=101.0)

    assert_along(still.view(now_s=103.0), DRIFT, 0.25)


def test_the_room_thawing_carries_the_move_on_from_where_it_stopped():
    still = paced()
    still.set_paused(True, now_s=101.0)

    still.set_paused(False, now_s=110.0)

    assert_along(still.view(now_s=111.0), DRIFT, 0.5)


def test_turning_the_pace_up_slows_the_move_instead_of_jumping_it_on():
    still = paced()

    still.set_pace(8.0, now_s=102.0)  # halfway along, and the show slows down

    assert_along(still.view(now_s=102.0), DRIFT, 0.5)
    assert_along(still.view(now_s=104.0), DRIFT, 0.75)


def test_a_room_told_again_that_it_is_frozen_holds_the_picture_from_the_first_time():
    still = paced()
    still.set_paused(True, now_s=101.0)

    still.set_paused(True, now_s=103.0)

    assert_along(still.view(now_s=107.0), DRIFT, 0.25)


def test_a_picture_stepped_to_while_the_room_is_frozen_waits_at_the_start_of_its_move():
    still = paced()
    still.set_paused(True, now_s=101.0)

    still.new_picture(now_s=106.0)

    assert_along(still.view(now_s=108.0), DRIFT, 0.0)
    still.set_paused(False, now_s=110.0)
    assert_along(still.view(now_s=111.0), DRIFT, 0.25)


def test_holding_a_moving_picture_keeps_it_where_its_move_had_got_to():
    still = paced()

    still.set_pace(0.0, now_s=102.0)

    assert_along(still.view(now_s=110.0), DRIFT, 0.5)


def test_letting_a_held_picture_go_carries_its_move_on_from_there():
    still = paced()
    still.set_pace(0.0, now_s=102.0)

    still.set_pace(4.0, now_s=110.0)

    assert_along(still.view(now_s=111.0), DRIFT, 0.75)


def test_a_picture_held_since_it_came_up_sets_off_zooming_in_from_the_whole_picture():
    still = paced(0.0, deals=Deals(DRIFT, from_rest=CREEP))

    still.set_pace(4.0, now_s=110.0)

    assert_along(still.view(now_s=110.0), CREEP, 0.0)
    assert_along(still.view(now_s=112.0), CREEP, 0.5)


def test_a_new_picture_is_dealt_its_own_move_from_the_start():
    deals = Deals(DRIFT)
    still = paced(deals=deals)

    still.new_picture(now_s=102.0)

    assert_along(still.view(now_s=102.0), DRIFT, 0.0)
    assert deals.dealt == 2


def test_a_picture_whose_hold_has_run_out_waits_at_the_end_of_its_move_for_the_next():
    still = paced()

    assert_along(still.view(now_s=104.05), DRIFT, 1.0)


def test_a_picture_has_run_out_once_its_pace_has_gone_by():
    still = paced()

    assert (still.ran_out(now_s=103.9), still.ran_out(now_s=104.0)) == (False, True)


def test_a_held_picture_never_runs_out():
    assert paced(0.0).ran_out(now_s=1000.0) is False


def test_a_locked_picture_never_runs_out():
    still = paced()

    still.set_looping(True, now_s=100.0)

    assert still.ran_out(now_s=1000.0) is False


def test_a_locked_picture_makes_the_next_move_dealt_each_time_it_comes_round():
    still = paced(deals=Deals(DRIFT, CREEP))

    still.set_looping(True, now_s=100.0)

    assert_along(still.view(now_s=106.0), CREEP, 0.5)


def test_a_locked_picture_keeps_one_move_the_whole_way_round():
    still = paced(deals=Deals(DRIFT, CREEP, DRIFT))
    still.set_looping(True, now_s=100.0)

    views = [still.view(now_s=now) for now in (105.0, 106.0, 107.0)]

    for view, progress in zip(views, (0.25, 0.5, 0.75), strict=True):
        assert_along(view, CREEP, progress)


def test_a_locked_picture_counts_its_rounds_from_when_it_came_up():
    still = paced(deals=Deals(DRIFT, CREEP))
    still.set_looping(True, now_s=100.0)

    assert_along(still.view(now_s=113.0), CREEP, 0.25)


def test_a_picture_let_go_of_its_lock_finishes_the_round_it_is_in():
    still = paced(deals=Deals(DRIFT, CREEP))
    still.set_looping(True, now_s=100.0)

    still.set_looping(False, now_s=104.5)

    assert_along(still.view(now_s=106.0), CREEP, 0.5)
    assert_along(still.view(now_s=109.0), CREEP, 1.0)


def test_a_picture_sent_back_along_its_hold_is_drawn_back_along_its_move():
    still = paced()

    still.seek(0.25, now_s=103.0)

    assert_along(still.view(now_s=103.0), DRIFT, 0.25)
    assert still.progress(now_s=104.0) == pytest.approx(0.5)


def test_a_locked_picture_sent_back_in_a_later_round_keeps_that_rounds_move():
    still = paced(deals=Deals(DRIFT, CREEP))
    still.set_looping(True, now_s=100.0)

    still.seek(0.25, now_s=106.0)

    assert_along(still.view(now_s=106.0), CREEP, 0.25)


def test_a_held_picture_sent_along_its_hold_stays_where_it_was_held():
    still = paced()
    still.set_pace(0.0, now_s=102.0)

    still.seek(0.75, now_s=103.0)

    assert_along(still.view(now_s=110.0), DRIFT, 0.5)


def test_a_frozen_picture_sent_back_waits_there_until_the_room_thaws():
    still = paced()
    still.set_paused(True, now_s=103.0)

    still.seek(0.25, now_s=104.0)

    assert_along(still.view(now_s=108.0), DRIFT, 0.25)
    still.set_paused(False, now_s=108.0)
    assert_along(still.view(now_s=109.0), DRIFT, 0.5)


WIDE = (1920, 1080)


def test_the_whole_picture_reaches_mpv_unzoomed_and_centered():
    assert View().placement() == (0.0, 0.0, 0.0)


def test_a_view_reaches_mpv_as_its_zoom_and_how_far_it_leans_each_way():
    assert View(ZOOMED_IN, 1.0, -0.5).placement() == (math.log2(ZOOMED_IN), 1.0, -0.5)


# mpv's own arithmetic for where a picture is drawn: aspect_calc_panscan and
# src_dst_split_scaling in video/out/aspect.c at the build the engines load
# (v0.41.0-724-g71ebd0840), with video-recenter on, single precision and
# truncated to whole pixels as mpv does it.
F32 = np.float32


def mpv_fitted(window: tuple[int, int], shown: tuple[int, int]) -> tuple[int, int]:
    (window_w, window_h), (shown_w, shown_h) = window, shown
    width, height = window_w, int(F32(window_w) / F32(shown_w) * F32(shown_h))
    if height > window_h or height < shown_h:
        narrower = int(F32(window_h) / F32(shown_h) * F32(shown_w))
        if narrower <= window_w:
            width, height = narrower, window_h
    return width, height


def mpv_span(window: int, fitted: int, video_zoom: float, align: float) -> tuple[int, int]:
    scaled = max(int(F32(fitted) * F32(2.0) ** F32(video_zoom)), 1)
    if window >= scaled:
        align = 0.0
    start = int(F32(window - scaled) * ((F32(align) + F32(1.0)) / F32(2.0)))
    return start, start + scaled


def drawn(window: tuple[int, int], shown: tuple[int, int], view: View) -> list[tuple[int, int, int]]:
    video_zoom, *aligns = view.placement()
    return [(side, *mpv_span(side, fitted, video_zoom, align))
            for side, fitted, align in zip(window, mpv_fitted(window, shown), aligns, strict=True)]


SHAPES = [(1920, 1080), (832, 1216), (3000, 1000), (1024, 1024)]
CORNERS = [(-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)]


@pytest.mark.parametrize("shown", SHAPES)
@pytest.mark.parametrize("corner", CORNERS)
@pytest.mark.parametrize("zoom", [1.01, ZOOMED_IN, 3.0, 8.0])
def test_no_view_draws_an_edge_of_the_picture_inside_the_window(shown, corner, zoom):
    centered = drawn(WIDE, shown, View(zoom))

    for (window, start, end), (_, centered_start, _) in zip(
            drawn(WIDE, shown, View(zoom, *corner)), centered, strict=True):
        if start > 0 or end < window:
            assert start == centered_start


@pytest.mark.parametrize("shown", SHAPES)
@pytest.mark.parametrize("corner", CORNERS)
def test_a_view_at_the_end_of_its_reach_brings_the_pictures_edge_up_to_the_windows(shown, corner):
    for window, start, end in drawn(WIDE, shown, View(8.0, *corner)):
        assert start <= 0 and end >= window
        assert min(-start, end - window) == 0


def test_a_picture_held_for_less_than_its_pace_runs_out_then_on_the_move_of_the_whole_pace():
    still = paced()

    still.hold_for(2.0)

    assert (still.ran_out(now_s=101.9), still.ran_out(now_s=102.0)) == (False, True)
    assert_along(still.view(now_s=101.0), DRIFT, 0.25)


def test_a_new_picture_holds_for_its_whole_pace_again():
    still = paced()
    still.hold_for(2.0)

    still.new_picture(now_s=103.0)

    assert (still.holds_for_s, still.ran_out(now_s=106.9)) == (4.0, False)


def test_a_locked_picture_held_for_less_than_its_pace_still_never_runs_out():
    still = paced()
    still.hold_for(2.0)

    still.set_looping(True, now_s=100.0)

    assert still.ran_out(now_s=103.0) is False


def part_drawn(window, shown, view: View, part):
    x0, y0, x1, y1 = part
    return [(side, start + low * (end - start), start + high * (end - start))
            for (side, start, end), (low, high) in zip(
                drawn(window, shown, view), ((x0, x1), (y0, y1)), strict=True)]


def test_a_close_up_fits_its_place_in_the_window_and_puts_it_in_the_middle():
    part = (0.25, 0.25, 0.75, 0.75)

    for window, start, end in part_drawn(WIDE, WIDE, Fit(WIDE, WIDE).framing(part), part):
        assert start == pytest.approx(0, abs=2)
        assert end == pytest.approx(window, abs=2)


@pytest.mark.parametrize("shown", SHAPES)
@pytest.mark.parametrize("part", [(0.75, 0.0, 1.0, 0.25), (0.0, 0.8, 0.3, 1.0), (0.4, 0.3, 0.6, 0.5)])
def test_a_place_anywhere_in_the_picture_is_drawn_whole_inside_the_window(shown, part):
    for window, start, end in part_drawn(WIDE, shown, Fit(WIDE, shown).framing(part), part):
        assert start >= -1
        assert end <= window + 1


def test_a_close_up_on_a_sliver_comes_no_closer_than_any_close_up_comes():
    assert Fit(WIDE, WIDE).framing((0.5, 0.2, 0.5, 0.3)).zoom == CLOSEST


def test_a_place_reaching_past_the_picture_is_framed_by_what_of_it_lies_inside():
    fit = Fit(WIDE, WIDE)

    assert fit.framing((-0.5, 0.25, 0.5, 0.75)) == fit.framing((0.0, 0.25, 0.5, 0.75))


def test_a_close_up_before_the_window_is_known_frames_as_if_it_had_the_pictures_shape():
    part = (0.0, 0.0, 0.5, 0.5)

    assert Fit((0, 0), WIDE).framing(part) == Fit(WIDE, WIDE).framing(part)


def test_a_close_up_on_a_picture_laid_out_in_tiles_frames_the_middle_tile():
    strip = (1920, 1080)

    assert Fit(WIDE, strip, tiles=3).framing((0.25, 0.25, 0.75, 0.75)) == Fit(
        WIDE, strip).framing((1.25 / 3, 0.25, 1.75 / 3, 0.75))


FACE = (0.4, 0.1, 0.6, 0.3)
HAND = (0.1, 0.6, 0.3, 0.8)


def locked_with_places(*places, deals: Deals | None = None) -> KenBurns:
    still = paced(deals=deals)
    still.set_points_of_interest(places, now_s=100.0)
    still.set_looping(True, now_s=100.0)
    return still


def test_a_locked_picture_comes_round_to_whichever_stop_its_moves_pick():
    deals = Deals(DRIFT, CREEP, stops=(HAND, None, FACE))
    still = locked_with_places(FACE, HAND, deals=deals)
    framed = Fit((0, 0), (0, 0)).framing

    views = [still.view(now_s=now) for now in (104.0, 108.0, 112.0)]

    assert views == [framed(HAND), CREEP.at(0.0), framed(FACE)]


def test_places_that_arrive_partway_round_are_the_ones_the_next_round_picks_among():
    deals = Deals(DRIFT, stops=(FACE, HAND))
    still = locked_with_places(FACE, HAND, deals=deals)
    still.view(now_s=104.0)

    still.set_points_of_interest((HAND,), now_s=105.0)
    still.view(now_s=108.0)

    assert deals.offered[-1] == (HAND,)


def test_a_new_picture_starts_its_round_of_places_on_the_whole_picture():
    deals = Deals(DRIFT, CREEP)
    still = locked_with_places(FACE, deals=deals)
    still.view(now_s=104.0)

    still.new_picture(now_s=105.0)

    assert still.view(now_s=105.0) == CREEP.at(0.0)
    assert still.view(now_s=109.0) == Fit((0, 0), (0, 0)).framing(FACE)


def test_a_picture_let_go_of_its_lock_makes_its_ordinary_move_and_no_close_up():
    deals = Deals(DRIFT)
    still = paced(deals=deals)

    still.set_points_of_interest((FACE,), now_s=100.0)

    assert_along(still.view(now_s=102.0), DRIFT, 0.5)
    assert deals.closed_up_on == []


def test_a_close_up_is_framed_for_the_window_the_picture_is_in_when_it_comes_round():
    window = Fit(WIDE, (832, 1216))
    still = KenBurns(Deals(DRIFT), fit=lambda: window)
    still.set_pace(4.0, now_s=100.0)
    still.new_picture(now_s=100.0)
    still.set_points_of_interest((FACE,), now_s=100.0)
    still.set_looping(True, now_s=100.0)

    assert still.view(now_s=104.0) == window.framing(FACE)


PLACE = (0.2, 0.4, 0.6, 0.6)


def as_drawn(box):
    return box


def size_of(box) -> tuple[float, float]:
    return box[2] - box[0], box[3] - box[1]


def inside(box, place) -> bool:
    return all(outer <= edge + 1e-9 for outer, edge in zip(place[:2], box[:2], strict=True)) and all(
        edge <= outer + 1e-9 for outer, edge in zip(place[2:], box[2:], strict=True))


def closed_up(count: int, seed: int = 7) -> list[Move]:
    moves = Moves(random.Random(seed))
    return [moves.close_up(as_drawn, PLACE) for _ in range(count)]


def test_no_close_up_makes_the_kind_of_move_the_round_before_it_made():
    moves = Moves(random.Random(7))
    dealt_in_turn = [moves.close_up(as_drawn, PLACE) if turn % 3 else moves.deal()
                     for turn in range(300)]

    kinds = [kind_of(move) if isinstance(move.start, View) else close_up_kind(move)
             for move in dealt_in_turn]

    assert all(one != next_one for one, next_one in itertools.pairwise(kinds))


def close_up_kind(move: Move) -> str:
    start, end = size_of(move.start)[0], size_of(move.end)[0]
    if start > end + 1e-9:
        return "in"
    if start < end - 1e-9:
        return "out"
    return "pan"


def test_a_close_up_zooms_between_the_whole_place_and_a_spot_inside_it_closer_by_the_ordinary_zoom():
    zooms = [move for move in closed_up(300) if close_up_kind(move) != "pan"]

    for move in zooms:
        whole, nearer = (move.start, move.end) if close_up_kind(move) == "in" else (move.end, move.start)
        assert whole == PLACE
        assert inside(nearer, PLACE)
        assert size_of(nearer) == pytest.approx(tuple(side / ZOOMED_IN for side in size_of(PLACE)))
    assert {close_up_kind(move) for move in zooms} == {"in", "out"}


def test_a_close_up_pan_crosses_the_place_from_a_corner_to_the_opposite_one():
    pans = [move for move in closed_up(300) if close_up_kind(move) == "pan"]

    for move in pans:
        assert inside(move.start, PLACE) and inside(move.end, PLACE)
        assert size_of(move.start) == pytest.approx(tuple(side / ZOOMED_IN for side in size_of(PLACE)))
        start_middle = ((move.start[0] + move.start[2]) / 2, (move.start[1] + move.start[3]) / 2)
        end_middle = ((move.end[0] + move.end[2]) / 2, (move.end[1] + move.end[3]) / 2)
        assert start_middle[0] + end_middle[0] == pytest.approx(PLACE[0] + PLACE[2])
        assert start_middle[1] + end_middle[1] == pytest.approx(PLACE[1] + PLACE[3])
    assert pans


def test_the_whole_picture_comes_round_as_often_as_all_the_places_together():
    moves = Moves(random.Random(7))
    places = (FACE, HAND, PLACE)

    stops = [moves.stop_among(places) for _ in range(6000)]

    assert stops.count(None) / len(stops) == pytest.approx(1 / 2, abs=0.03)
    for place in places:
        assert stops.count(place) / len(stops) == pytest.approx(1 / 6, abs=0.03)

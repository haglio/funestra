from __future__ import annotations

from funestra.hud_placement import HudCorner, HudEdge, hud_origin


def test_a_side_key_moves_the_hud_to_that_side_and_leaves_the_other_axis_alone():
    assert HudCorner.UPPER_LEFT.toward("right") is HudCorner.UPPER_RIGHT
    assert HudCorner.UPPER_RIGHT.toward("right") is HudCorner.UPPER_RIGHT
    assert HudCorner.LOWER_RIGHT.toward("up") is HudCorner.UPPER_RIGHT
    assert HudCorner.UPPER_RIGHT.toward("down") is HudCorner.LOWER_RIGHT
    assert HudCorner.LOWER_RIGHT.toward("left") is HudCorner.LOWER_LEFT
    assert HudCorner.LOWER_LEFT.toward("up") is HudCorner.UPPER_LEFT


def test_a_funestra_with_one_pair_of_keys_walks_the_four_corners_round():
    assert HudCorner.UPPER_LEFT.turned(clockwise=True) is HudCorner.UPPER_RIGHT
    assert HudCorner.UPPER_RIGHT.turned(clockwise=True) is HudCorner.LOWER_RIGHT
    assert HudCorner.LOWER_RIGHT.turned(clockwise=True) is HudCorner.LOWER_LEFT
    assert HudCorner.LOWER_LEFT.turned(clockwise=True) is HudCorner.UPPER_LEFT
    assert HudCorner.UPPER_LEFT.turned(clockwise=False) is HudCorner.LOWER_LEFT
    assert HudCorner.LOWER_LEFT.turned(clockwise=False) is HudCorner.LOWER_RIGHT


def test_a_hud_is_inset_from_whichever_corner_it_was_moved_to():
    at = dict(hud=(100, 60), window=(800, 600), margin=12)
    assert hud_origin(HudCorner.UPPER_LEFT, **at) == (12, 12)
    assert hud_origin(HudCorner.UPPER_RIGHT, **at) == (688, 12)
    assert hud_origin(HudCorner.LOWER_LEFT, **at) == (12, 528)
    assert hud_origin(HudCorner.LOWER_RIGHT, **at) == (688, 528)


def test_a_lower_corner_stands_on_the_funestras_own_lower_row_rather_than_over_it():
    assert hud_origin(HudCorner.LOWER_LEFT, hud=(100, 60), window=(800, 600),
                      margin=12, lower_edge=24) == (12, 504)
    assert hud_origin(HudCorner.UPPER_LEFT, hud=(100, 60), window=(800, 600),
                      margin=12, lower_edge=24) == (12, 12)


def test_a_hud_too_big_for_its_window_starts_at_the_edge_rather_than_off_it():
    assert hud_origin(HudCorner.LOWER_RIGHT, hud=(900, 700), window=(800, 600),
                      margin=12) == (0, 0)


def test_each_key_of_a_cluster_puts_the_hud_against_the_side_it_points_at():
    for edge in HudEdge:
        assert edge.toward("up") is HudEdge.UPPER
        assert edge.toward("down") is HudEdge.LOWER
        assert edge.toward("left") is HudEdge.LEFT
        assert edge.toward("right") is HudEdge.RIGHT


def test_a_word_that_names_no_direction_leaves_the_hud_against_its_side():
    assert HudEdge.LEFT.toward("sideways") is HudEdge.LEFT


def test_the_pair_of_keys_walks_the_four_sides_round_either_way():
    assert HudEdge.UPPER.turned(clockwise=True) is HudEdge.RIGHT
    assert HudEdge.RIGHT.turned(clockwise=True) is HudEdge.LOWER
    assert HudEdge.LOWER.turned(clockwise=True) is HudEdge.LEFT
    assert HudEdge.LEFT.turned(clockwise=True) is HudEdge.UPPER
    assert HudEdge.UPPER.turned(clockwise=False) is HudEdge.LEFT
    assert HudEdge.LOWER.turned(clockwise=False) is HudEdge.RIGHT

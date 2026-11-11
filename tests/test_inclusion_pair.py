from __future__ import annotations

from funestra.inclusion_pair import BOTH, InclusionPair, Kind

_PAIR = InclusionPair(
    Kind("Alpha", "alpha_mark", "alpha {things}"),
    Kind("Beta", "beta_mark", "beta {things}"),
    {(True, True): "pair_both", (True, False): "pair_alpha",
     (False, True): "pair_beta", (False, False): "pair_none"},
)


def test_each_button_asks_for_its_kind_turned_the_other_way_and_the_other_kept():
    alpha, beta = _PAIR.buttons(BOTH, remembered=False)

    assert (alpha.command, beta.command) == ("pair_beta", "pair_alpha")


def test_the_first_button_starts_a_group_of_its_own():
    alpha, beta = _PAIR.buttons(BOTH, remembered=False)

    assert (alpha.group_break, beta.group_break) == (True, False)


def test_a_button_says_whether_its_kind_is_included_in_the_things_it_names():
    alpha, beta = _PAIR.buttons((True, False), remembered=False, things="items")

    assert (alpha.tooltip, beta.tooltip) == ("Including alpha items", "Not including beta items")
    assert (alpha.lit, beta.lit) == (True, False)


def test_a_remembered_pair_marks_its_included_kind_as_remembered_rather_than_lit():
    alpha, _beta = _PAIR.buttons((True, False), remembered=True)

    assert (alpha.lit, alpha.remembered) == (False, True)


def test_the_flash_names_both_kinds_or_the_one_kept():
    assert [_PAIR.flash(included) for included in (BOTH, (True, False), (False, True),
                                                   (False, False))] == [
        "Alpha + Beta", "Alpha only", "Beta only", ""]


def test_the_title_names_only_the_one_kind_kept():
    assert [_PAIR.title_word(included) for included in (BOTH, (False, True), (False, False))] == [
        "", "Beta", ""]


def test_asked_reads_a_command_back_as_what_it_includes():
    assert _PAIR.asked["pair_alpha"] == (True, False)

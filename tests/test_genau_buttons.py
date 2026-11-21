from __future__ import annotations

from funestra.genau_buttons import (
    ABOUT_GENAUS_FLICK,
    FLICK_SECONDS_BUTTON,
    GENAU_VALUED,
    GENAU_VERBS,
    TRASH_FLICK,
)
from funestra.genau_controls import VERBS
from funestra.hud_kinds import HudFacts, HudKind, hud_rows
from funestra.modes import MainMode

_GENAU = HudFacts(main_mode=MainMode.GENAU, flick_one="flick", flick_many="flicks")


def _drawn(kind: HudKind, facts: HudFacts) -> set[str]:
    return {button.command for row in hud_rows(kind, facts) for button in row}


def test_every_flick_button_the_main_funestra_draws_in_genau_is_one_genau_has_a_verb_for():
    assert set(GENAU_VERBS) <= _drawn(HudKind.MAIN, _GENAU)


def test_a_slideshow_not_hosted_draws_the_same_flick_buttons_in_genau():
    assert set(GENAU_VERBS) <= _drawn(HudKind.SLIDESHOW, _GENAU)


def test_each_verb_a_flick_button_is_sent_on_as_is_one_genau_answers():
    assert {*GENAU_VERBS.values(), *GENAU_VALUED.values()} <= set(VERBS)


def test_the_flick_commands_are_its_buttons_its_trash_and_its_seconds():
    assert {*GENAU_VERBS, TRASH_FLICK, FLICK_SECONDS_BUTTON} == ABOUT_GENAUS_FLICK

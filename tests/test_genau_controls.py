"""The registry's own rules — the ones no single control's test would catch."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from funestra.control_registry import Control, Verb, bind
from funestra.flag import Flag
from funestra.genau_controls import CONTROLS, VERBS, GenauControls
from funestra.robot_hand import RobotHandState
from funestra.robot_hand_beat import BeatEngine


def _controls(**fields) -> GenauControls:
    return GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0),
        paused=Flag(),
        step_flick=lambda _step: None,
        **fields,
    )


def _moved(_controls_arg, _value) -> bool:
    return True


class TestOneVerbHasOneOwner:
    def test_two_controls_cannot_claim_the_same_spelling(self):
        """The loser would go silently unreachable, which is the drift the
        registry exists to stop."""
        clash = (
            Control(name="one", verbs=(Verb("EXAMPLE_VERB", _moved),)),
            Control(name="two", verbs=(Verb("EXAMPLE_VERB", _moved),)),
        )

        with pytest.raises(ValueError) as refused:
            bind(clash)

        assert "EXAMPLE_VERB" in str(refused.value)
        assert "one" in str(refused.value) and "two" in str(refused.value)

    def test_the_registry_that_ships_binds(self):
        assert set(VERBS) == {
            verb.spelling for control in CONTROLS for verb in control.verbs
        }

    def test_every_verb_names_the_control_that_owns_it(self):
        for spelling, (control, verb) in VERBS.items():
            assert verb.spelling == spelling
            assert verb in control.verbs


class TestAControlSaysWhatItCannotActWithout:
    def test_a_control_needing_nothing_can_always_act(self):
        assert Control(name="free", verbs=()).can_act(_controls()) is True

    def test_a_need_this_build_did_not_wire_stops_the_control(self):
        needy = Control(name="needy", verbs=(), needs=("robot_hand",))

        assert needy.can_act(_controls()) is False
        assert needy.can_act(_controls(robot_hand=RobotHandState())) is True

    def test_every_need_names_a_field_that_exists(self):
        """A misspelled need would read as absent and silence the control."""
        fields = set(GenauControls.__dataclass_fields__)

        for control in CONTROLS:
            assert set(control.needs) <= fields, control.name


class TestHalfACommandIsNotACommand:
    """The arity is part of the spelling, and both halves of the rule matter."""

    @pytest.mark.parametrize("spelling", ["SPEED", "AMP", "CENTER"])
    def test_a_verb_that_wants_a_value_says_so(self, spelling):
        assert VERBS[spelling][1].takes_a_value is True

    @pytest.mark.parametrize(
        "spelling", ["SPEED_UP", "SPEED_DOWN", "CYCLE_SHAPE", "CYCLE_SHAPE_PREV"],
    )
    def test_a_verb_that_stands_alone_says_so(self, spelling):
        assert VERBS[spelling][1].takes_a_value is False


# Every verb the registry answers.  Written down
# here so a verb added to the registry is a deliberate line in a diff -- the
# spellings are a contract with the orchestrator that sends them.
WRITTEN_DOWN_VERBS = frozenset({
    "QUIT", "PREV", "NEXT", "WEIRD", "FLIP_ENDS", "LATEST", "SHUFFLE", "OFFSET_QUARTER_CYCLE",
    "PAUSE", "RESUME", "PARK", "RETRACT", "SPEED_DOWN", "SPEED_UP", "AMPLITUDE_DOWN", "AMPLITUDE_UP",
    "CENTER_DOWN", "CENTER_UP", "CYCLE_SHAPE", "CYCLE_SHAPE_PREV",
    "TOGGLE_LEARNED", "LEARNED_ON", "LEARNED_OFF",
    "TOGGLE_LOCK", "LOCK_ON", "LOCK_OFF",
    "FLICK_SECONDS_DOWN", "FLICK_SECONDS_UP", "HUD_ON", "HUD_OFF",
    "AMP", "CENTER", "SPEED", "FLICK_SECONDS", "SET_VOLUME", "SET_TCODE_ENABLED", "SHAPES",
    "SET_MAX_INTENSITY", "PLAY_FILE",
    # The seconds verbs as an orchestrator from before the flicks were renamed
    # spells them.
    "CLIP_SECONDS_DOWN", "CLIP_SECONDS_UP", "CLIP_SECONDS",
})

class TestTheVocabularyIsWrittenDown:
    def test_the_registry_declares_exactly_the_verbs_written_down(self):
        assert set(VERBS) == WRITTEN_DOWN_VERBS


# The verbs Genau answers that every Funestra answers -- the family's, spelled in
# funestra_verbs and imported from there.  The rest are Genau's own.
FAMILY_VERBS = frozenset({
    "NEXT", "PREV", "TOGGLE_LOCK", "LOCK_ON", "LOCK_OFF", "QUIT", "SET_VOLUME",
    "SET_TCODE_ENABLED", "SET_MAX_INTENSITY", "SPEED_DOWN", "SPEED_UP", "PLAY_FILE",
})


class TestAVerbIsSpelledInOneFile:
    """A control used to be hand-plumbed through four to six files -- a branch in
    the dispatcher, a parameter and an attribute and a hand-off line on the
    tick, a branch in the key handler -- and the two hottest files in Genau's
    repo changed together in half its commits because of it.  Held as a ceiling
    that fails rather than as a note, and measured the way a reader would: which
    modules in this package spell the verb at all.  One is allowed: the
    registry that declares it, or funestra_verbs for a verb every Funestra answers.
    A module's table of the names it used to have spells none of them.
    """

    @staticmethod
    def _files_naming(verb: str) -> set[str]:

        package = Path(__file__).resolve().parents[1] / "funestra"
        naming = set()
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            spoken = [node for node in tree.body
                      if not (isinstance(node, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == "_RENAMED" for t in node.targets))]
            if any(isinstance(n, ast.Constant) and n.value == verb
                   for node in spoken for n in ast.walk(node)):
                naming.add(path.name)
        return naming

    @pytest.mark.parametrize("verb", sorted(WRITTEN_DOWN_VERBS - FAMILY_VERBS))
    def test_the_registry_is_the_one_module_that_spells_genaus_own(self, verb):
        assert self._files_naming(verb) == {"genau_controls.py"}

    @pytest.mark.parametrize("verb", sorted(FAMILY_VERBS))
    def test_funestra_verbs_is_the_one_module_that_spells_the_familys(self, verb):
        assert self._files_naming(verb) == {"funestra_verbs.py"}

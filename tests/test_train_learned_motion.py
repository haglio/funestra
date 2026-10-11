"""Fitting the learned motion's model from scripts: where the turning points
are, which stretches are continuous action, and how the phrases are cut.

Every script here is invented.
"""
from __future__ import annotations

import json
import random

from funestra import learned_model
from funestra.learned_model import Phrase
from tools import train_learned_motion as train


class TestFindingTheTurningPoints:
    def test_the_ends_of_each_swing_are_kept_and_the_points_between_are_not(self):
        actions = [(0, 10), (100, 50), (200, 90), (300, 50), (400, 10), (500, 90)]

        assert train.turning_points(actions) == [(0, 10), (200, 90), (400, 10), (500, 90)]

    def test_a_wobble_smaller_than_the_span_that_counts_is_not_a_turn(self):
        # The turn is the last time the script reached the top, so the wobble
        # belongs to the rise that ended there.
        actions = [(0, 10), (100, 90), (150, 86), (200, 90), (300, 10)]

        assert train.turning_points(actions) == [(0, 10), (200, 90), (300, 10)]


class TestContinuousAction:
    def test_a_gap_in_the_actions_ends_the_passage(self):
        actions = [(0, 10), (300, 90), (600, 10), (5000, 90), (5300, 10), (5600, 90)]

        passages = train.passages_of(actions)

        assert passages == [
            [train.Swing(0, 300, 10, 90), train.Swing(300, 600, 90, 10)],
            [train.Swing(5000, 5300, 90, 10), train.Swing(5300, 5600, 10, 90)],
        ]

    def test_a_hold_too_long_to_be_a_movement_ends_the_passage_too(self):
        # Held at the top by a run of points rather than by a gap: the rise that
        # arrived there is the hold's, and is dropped with it.
        actions = [(0, 10), (300, 90), (600, 10), (900, 90), (1500, 90), (2500, 90),
                   (3500, 90), (4500, 90), (4800, 10), (5100, 90)]

        passages = train.passages_of(actions)

        assert passages == [
            [train.Swing(0, 300, 10, 90), train.Swing(300, 600, 90, 10)],
            [train.Swing(4500, 4800, 90, 10), train.Swing(4800, 5100, 10, 90)],
        ]


def _passage(count: int, *, first_up: bool = True, duration_ms: int = 300) -> list[train.Swing]:
    swings = []
    for i in range(count):
        upward = (i % 2 == 0) == first_up
        swings.append(train.Swing(i * duration_ms, (i + 1) * duration_ms,
                                  10 if upward else 90, 90 if upward else 10))
    return swings


class TestCuttingPhrases:
    def test_a_passage_is_cut_into_whole_phrases_each_starting_upward(self):
        phrases = train.phrases_of(_passage(11, first_up=False), swings_per_phrase=4)

        assert phrases == [
            Phrase(((300, 90), (300, 10), (300, 90), (300, 10))),
            Phrase(((300, 90), (300, 10), (300, 90), (300, 10))),
        ]

    def test_a_passage_shorter_than_a_phrase_yields_none(self):
        assert train.phrases_of(_passage(3), swings_per_phrase=4) == []


def _script(swings: int, *, duration_ms: int, low: int, high: int, start_ms: int = 0,
            ) -> list[tuple[int, int]]:
    return [(start_ms + i * duration_ms, low if i % 2 == 0 else high) for i in range(swings + 1)]


class TestFittingTheModel:
    def test_the_model_carries_the_pace_the_scripts_were_written_at(self):
        steady = _script(64, duration_ms=300, low=10, high=90)

        model = train.fit([steady], rng=random.Random(1))

        assert model.native_cycle_ms == 600.0

    def test_phrases_are_kept_by_class_and_their_order_is_counted(self):
        steady = _script(32, duration_ms=300, low=10, high=90)
        quick = _script(16, duration_ms=150, low=40, high=60)

        model = train.fit([steady, quick], rng=random.Random(1))

        steady_class = learned_model.classify(train.phrases_of(train.passages_of(steady)[0])[0])
        quick_class = learned_model.classify(train.phrases_of(train.passages_of(quick)[0])[0])
        assert steady_class != quick_class
        assert model.seen == {steady_class: 2, quick_class: 1}
        assert len(model.phrases[steady_class]) == 2
        assert len(model.phrases[quick_class]) == 1
        assert model.successions == {steady_class: {steady_class: 1}}

    def test_only_so_many_phrases_of_a_class_are_kept_but_all_are_counted(self):
        steady = _script(16 * 5, duration_ms=300, low=10, high=90)

        model = train.fit([steady], rng=random.Random(1), kept_per_class=2)

        (cls,) = model.phrases
        assert len(model.phrases[cls]) == 2
        assert model.seen == {cls: 5}
        assert model.successions == {cls: {cls: 4}}

    def test_a_rest_in_a_script_separates_what_follows_from_what_came_before(self):
        before = _script(16, duration_ms=300, low=10, high=90)
        after = _script(16, duration_ms=300, low=10, high=90, start_ms=60_000)

        model = train.fit([before + after], rng=random.Random(1))

        (cls,) = model.phrases
        assert model.seen == {cls: 2}
        assert model.successions == {}


def _write_script(path, actions) -> None:
    path.write_text(json.dumps({"actions": [{"at": at, "pos": pos} for at, pos in actions]}),
                    encoding="utf-8")


class TestReadingTheCorpus:
    def test_a_skipped_tag_and_a_duplicate_are_left_out(self, tmp_path):
        harvested = tmp_path / "harvested"
        (harvested / "scripts").mkdir(parents=True)
        own = tmp_path / "own"
        own.mkdir()
        steady = _script(20, duration_ms=300, low=10, high=90)
        quick = _script(20, duration_ms=150, low=40, high=60)
        _write_script(harvested / "scripts" / "t1_p1_1.funscript", steady)
        _write_script(harvested / "scripts" / "t2_p1_1.funscript", quick)
        _write_script(own / "scene one.funscript", steady)
        (harvested / "index.jsonl").write_text(
            json.dumps({"file": "t1_p1_1.funscript", "tags": ["alpha"]}) + "\n"
            + json.dumps({"file": "t2_p1_1.funscript", "tags": ["alpha", "ai-generated"]}) + "\n",
            encoding="utf-8")

        scripts = list(train.scripts_in([harvested, own], skip_tags={"ai-generated"},
                                        keep_tags={"alpha"}))

        assert scripts == [steady]

    def test_only_scripts_wearing_a_kept_tag_are_taken_from_an_indexed_folder(self, tmp_path):
        harvested = tmp_path / "harvested"
        (harvested / "scripts").mkdir(parents=True)
        own = tmp_path / "own"
        own.mkdir()
        steady = _script(20, duration_ms=300, low=10, high=90)
        quick = _script(20, duration_ms=150, low=40, high=60)
        slow = _script(20, duration_ms=700, low=10, high=90)
        _write_script(harvested / "scripts" / "t1_p1_1.funscript", steady)
        _write_script(harvested / "scripts" / "t2_p1_1.funscript", quick)
        _write_script(own / "scene one.funscript", slow)
        (harvested / "index.jsonl").write_text(
            json.dumps({"file": "t1_p1_1.funscript", "tags": ["alpha", "beta"]}) + "\n"
            + json.dumps({"file": "t2_p1_1.funscript", "tags": ["gamma"]}) + "\n",
            encoding="utf-8")

        scripts = list(train.scripts_in([harvested, own], skip_tags=set(), keep_tags={"beta"}))

        # The kept one, and the un-indexed folder whole.
        assert scripts == [steady, slow]

    def test_a_folder_may_name_more_tags_to_skip_beside_its_index(self, tmp_path):
        harvested = tmp_path / "harvested"
        (harvested / "scripts").mkdir(parents=True)
        _write_script(harvested / "scripts" / "t1_p1_1.funscript",
                      _script(20, duration_ms=300, low=10, high=90))
        (harvested / "index.jsonl").write_text(
            json.dumps({"file": "t1_p1_1.funscript", "tags": ["gamma"]}) + "\n",
            encoding="utf-8")
        (harvested / train.SKIP_TAGS_FILENAME).write_text("# private\ngamma\n", encoding="utf-8")

        assert list(train.scripts_in([harvested], skip_tags=set())) == []

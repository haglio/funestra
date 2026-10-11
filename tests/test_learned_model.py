"""The learned motion's model: phrases of real swings, sorted by pace and
range, and which kind of phrase tends to follow which.

Every phrase here is invented.
"""
from __future__ import annotations

import random

from funestra import learned_model
from funestra.learned_model import LearnedModel, Phrase


def _phrase(duration_ms: int, low: int, high: int, swings: int = learned_model.PHRASE_SWINGS):
    """A steady phrase: up to *high*, down to *low*, every swing *duration_ms*."""
    return Phrase(tuple(
        (duration_ms, high if i % 2 == 0 else low) for i in range(swings)))


class TestClassifyingAPhrase:
    def test_the_class_is_the_pace_and_the_range_the_phrase_mostly_keeps(self):
        assert learned_model.classify(_phrase(400, 20, 80)) == (
            learned_model.tempo_bin(400), 1, 4)

    def test_a_faster_phrase_lands_in_a_lower_tempo_bin(self):
        assert learned_model.tempo_bin(150) < learned_model.tempo_bin(600)

    def test_the_tempo_bins_cover_the_whole_axis(self):
        assert learned_model.tempo_bin(1) == 0
        assert learned_model.tempo_bin(60_000) == learned_model.TEMPO_BINS - 1


def _model() -> LearnedModel:
    steady = _phrase(400, 20, 80)
    quick = _phrase(150, 40, 60)
    return LearnedModel(
        phrases={learned_model.classify(steady): [steady],
                 learned_model.classify(quick): [quick]},
        successions={learned_model.classify(steady): {learned_model.classify(quick): 3}},
        seen={learned_model.classify(steady): 5, learned_model.classify(quick): 3},
        native_cycle_ms=640.0,
    )


class TestSavingAndLoading:
    def test_a_model_comes_back_as_it_went_in(self, tmp_path):
        model = _model()
        learned_model.save(model, tmp_path / "model.json.gz")

        assert learned_model.load(tmp_path / "model.json.gz") == model


class TestTheNativePace:
    def test_it_is_the_cycle_the_phrases_mostly_keep_weighted_by_how_many_were_seen(self):
        # Three steady phrases kept for a class seen a hundred times outweigh
        # one quick phrase kept for a class seen once: the pace the model was
        # trained on is the steady one's, two swings of 400 ms a cycle.
        model = _model()
        model.seen = {learned_model.classify(_phrase(400, 20, 80)): 100,
                      learned_model.classify(_phrase(150, 40, 60)): 1}

        assert learned_model.measure_native_cycle_ms(model) == 800.0


class TestDrawingWhatComesNext:
    def test_what_follows_a_class_is_what_followed_it_in_the_scripts(self):
        model = _model()
        steady = learned_model.classify(_phrase(400, 20, 80))
        quick = learned_model.classify(_phrase(150, 40, 60))

        drawn = {learned_model.next_class(model, random.Random(seed), steady)
                 for seed in range(20)}

        assert drawn == {quick}

    def test_a_class_nothing_followed_is_followed_by_anything_seen(self):
        model = _model()
        quick = learned_model.classify(_phrase(150, 40, 60))

        drawn = {learned_model.next_class(model, random.Random(seed), quick)
                 for seed in range(40)}

        assert drawn == set(model.phrases)

    def test_the_first_class_is_drawn_from_everything_seen(self):
        model = _model()

        drawn = {learned_model.next_class(model, random.Random(seed), None)
                 for seed in range(40)}

        assert drawn == set(model.phrases)

    def test_a_phrase_of_a_class_is_one_of_that_classs_phrases(self):
        model = _model()
        steady = learned_model.classify(_phrase(400, 20, 80))

        assert learned_model.draw_phrase(model, random.Random(1), steady) == _phrase(400, 20, 80)

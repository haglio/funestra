"""Fit the learned motion's model from a folder of real funscripts.

    python tools/train_learned_motion.py [--corpus <dir> ...] --out <model.json.gz>

Each ``--corpus`` folder is searched for ``*.funscript``; a folder holding the
harvester's ``index.jsonl`` also has its topics' tags read: only a script whose
topic wears a tag in ``--keep-tag`` (:data:`KEPT_TAGS` unless said otherwise)
is taken, and one wearing a tag in ``--skip-tag`` (:data:`SKIPPED_TAGS`) is
left out.  A folder with no index -- his own scripts -- is taken whole.  What comes out is a
:class:`funestra.learned_model.LearnedModel`: up to ``--kept`` phrases per
class, drawn evenly from everything seen, and the counts of which class
followed which.  Nothing named in the corpus reaches the model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from collections.abc import Iterable, Iterator
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

from app_support import haglio_settings
from app_support.funscript import read_actions

from funestra.learned_model import (
    PHRASE_SWINGS,
    LearnedModel,
    Phrase,
    classify,
    measure_native_cycle_ms,
    save,
)

# A reversal has to travel at least this far to be a turn rather than a wobble
# on the way somewhere.
MIN_SPAN = 8
# Nothing scripted for this long is a rest, not a movement: the continuous
# action ends there.
REST_GAP_MS = 2000
# So is a swing longer than this: a hold written out point by point.
MAX_SWING_MS = 2500
# How many phrases of each class the model keeps.
KEPT_PER_CLASS = 64

logger = logging.getLogger("train")


class Swing(NamedTuple):
    start_ms: int
    end_ms: int
    start: int
    end: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def upward(self) -> bool:
        return self.end > self.start


def turning_points(actions: list[tuple[int, int]], *, min_span: int = MIN_SPAN,
                   ) -> list[tuple[int, int]]:
    """Where the script turns back: the highest point of each rise and the lowest
    of each fall, ignoring a reversal shorter than *min_span*.  A hold at a turn
    belongs to the swing that arrived there, so the swing that leaves is the
    movement alone."""
    if not actions:
        return []
    turns = [actions[0]]
    candidate = actions[0]
    direction = 0
    for point in actions[1:]:
        if direction == 0:
            if point[1] >= turns[-1][1] + min_span:
                direction, candidate = 1, point
            elif point[1] <= turns[-1][1] - min_span:
                direction, candidate = -1, point
        elif direction > 0:
            if point[1] >= candidate[1]:
                candidate = point
            elif point[1] <= candidate[1] - min_span:
                turns.append(candidate)
                direction, candidate = -1, point
        elif point[1] <= candidate[1]:
            candidate = point
        elif point[1] >= candidate[1] + min_span:
            turns.append(candidate)
            direction, candidate = 1, point
    if direction != 0:
        turns.append(candidate)
    return turns


def passages_of(actions: list[tuple[int, int]], *, rest_gap_ms: int = REST_GAP_MS,
                max_swing_ms: int = MAX_SWING_MS) -> list[list[Swing]]:
    """The script's continuous action, as swings.

    A passage ends at a gap in the actions -- the script had nothing to say for
    that long -- and at a swing too long to be a movement, which is a hold
    written out point by point.  A swing to nowhere, two turns at one moment,
    is dropped.
    """
    passages: list[list[Swing]] = []
    for chunk in _between_gaps(actions, rest_gap_ms):
        current: list[Swing] = []
        points = turning_points(chunk)
        for (start_ms, start), (end_ms, end) in pairwise(points):
            swing = Swing(start_ms, end_ms, start, end)
            if swing.duration_ms <= 0:
                continue
            if swing.duration_ms > max_swing_ms:
                if current:
                    passages.append(current)
                current = []
                continue
            current.append(swing)
        if current:
            passages.append(current)
    return passages


def _between_gaps(actions: list[tuple[int, int]], rest_gap_ms: int,
                  ) -> Iterator[list[tuple[int, int]]]:
    chunk: list[tuple[int, int]] = []
    for action in actions:
        if chunk and action[0] - chunk[-1][0] > rest_gap_ms:
            yield chunk
            chunk = []
        chunk.append(action)
    if chunk:
        yield chunk


def phrases_of(passage: list[Swing], *, swings_per_phrase: int = PHRASE_SWINGS,
               ) -> list[Phrase]:
    """The passage cut into whole phrases, each beginning with a swing upward,
    in the order they were played; what is left over at the end is dropped."""
    first_up = next((i for i, swing in enumerate(passage) if swing.upward), len(passage))
    phrases = []
    for start in range(first_up, len(passage) - swings_per_phrase + 1, swings_per_phrase):
        chunk = passage[start:start + swings_per_phrase]
        phrases.append(Phrase(tuple((swing.duration_ms, swing.end) for swing in chunk)))
    return phrases


def fit(scripts: Iterable[list[tuple[int, int]]], *, rng: random.Random,
        kept_per_class: int = KEPT_PER_CLASS) -> LearnedModel:
    """The model of *scripts*: every phrase classed and counted, up to
    *kept_per_class* of each class kept (drawn evenly from all of them), and
    each class's successors counted within a passage -- never across a rest."""
    model = LearnedModel()
    for actions in scripts:
        for passage in passages_of(actions):
            previous = None
            for phrase in phrases_of(passage):
                cls = classify(phrase)
                _keep(model, rng, cls, phrase, kept_per_class)
                if previous is not None:
                    following = model.successions.setdefault(previous, {})
                    following[cls] = following.get(cls, 0) + 1
                previous = cls
    model.native_cycle_ms = measure_native_cycle_ms(model)
    return model


def _keep(model: LearnedModel, rng: random.Random, cls, phrase: Phrase, limit: int) -> None:
    """Reservoir sampling: the phrases kept are a uniform draw from every phrase
    of the class seen, however many there were."""
    seen = model.seen.get(cls, 0)
    model.seen[cls] = seen + 1
    kept = model.phrases.setdefault(cls, [])
    if len(kept) < limit:
        kept.append(phrase)
        return
    slot = rng.randrange(seen + 1)
    if slot < limit:
        kept[slot] = phrase


# A script with fewer actions than this is a fragment or a placeholder.
MIN_ACTIONS = 20
# Left out by default: scripts a machine wrote, and scripts written to music
# or to spoken instruction rather than to a person's motion -- their swings
# are beats and buzzes, not what this model is for.  A corpus folder may name
# more in a ``skip_tags.txt`` beside its index, one tag per line.
SKIPPED_TAGS = (
    "ai-generated", "ai-assisted",
    "pmv", "hmv", "beat-based", "music-based", "music", "joi", "audio-only",
)
SKIP_TAGS_FILENAME = "skip_tags.txt"
# Taken by default, where a folder's index says what each script is of:
# scripts of real people.  Drawn and rendered scenes move as no person can,
# which is the motion this model is not for.
KEPT_TAGS = ("real",)


def scripts_in(folders: Iterable[Path], *, skip_tags: set[str],
               keep_tags: set[str] = frozenset(KEPT_TAGS)) -> Iterator[list[tuple[int, int]]]:
    """Every distinct script under *folders*, as sorted (ms, position) pairs.

    A folder holding the harvester's index has its scripts' tags read from it:
    only one tagged with something in *keep_tags* is taken, and one tagged with
    anything in *skip_tags*, or in the folder's own ``skip_tags.txt``, is left
    out.  A folder with no index is taken whole.  A script seen before,
    wherever it was, is not yielded twice.
    """
    seen: set[str] = set()
    for folder in folders:
        tags_of = _tags_by_file(Path(folder) / "index.jsonl")
        skipped = skip_tags | _tags_listed_in(Path(folder) / SKIP_TAGS_FILENAME)
        for path in sorted(Path(folder).rglob("*.funscript")):
            tags = set(tags_of.get(path.name, ()))
            if tags_of and not (tags & keep_tags):
                continue
            if skipped & tags:
                continue
            actions = _actions_of(path)
            if len(actions) < MIN_ACTIONS:
                continue
            digest = hashlib.sha1(repr(actions).encode("ascii")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            yield actions


def _tags_listed_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def _tags_by_file(index: Path) -> dict[str, list[str]]:
    if not index.exists():
        return {}
    tags: dict[str, list[str]] = {}
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            tags[record["file"]] = list(record.get("tags", ()))
    return tags


def _actions_of(path: Path) -> list[tuple[int, int]]:
    actions = []
    for action in read_actions(path):
        try:
            actions.append((int(action["at"]), min(100, max(0, int(action["pos"])))))
        except (KeyError, TypeError, ValueError):
            return []
    return sorted(set(actions))


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kept", type=int, default=KEPT_PER_CLASS)
    parser.add_argument("--skip-tag", action="append", default=list(SKIPPED_TAGS))
    parser.add_argument("--keep-tag", action="append", default=list(KEPT_TAGS))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.corpus:
        args.corpus = [Path(haglio_settings.value("funscript_corpus_dir")) / "eroscripts"]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    scripts = 0
    def counted() -> Iterator[list[tuple[int, int]]]:
        nonlocal scripts
        for actions in scripts_in(args.corpus, skip_tags=set(args.skip_tag),
                                  keep_tags=set(args.keep_tag)):
            scripts += 1
            yield actions

    model = fit(counted(), rng=random.Random(args.seed), kept_per_class=args.kept)
    save(model, args.out)
    logger.info("%s scripts, %s phrases in %s classes, %s kept -> %s",
                scripts, sum(model.seen.values()), len(model.seen),
                sum(len(kept) for kept in model.phrases.values()), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

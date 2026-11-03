from __future__ import annotations

import gzip
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

PHRASE_SWINGS = 16
_TEMPO_FLOOR_MS = 100.0
_TEMPO_RATIO = math.sqrt(2)
TEMPO_BINS = 10
_RANGE_STEP = 20
RANGE_BINS = 100 // _RANGE_STEP

Class = tuple[int, int, int]


@dataclass(frozen=True)
class Phrase:
    swings: tuple[tuple[int, int], ...]


def tempo_bin(duration_ms: float) -> int:
    if duration_ms <= _TEMPO_FLOOR_MS:
        return 0
    return min(TEMPO_BINS - 1,
               int(math.log(duration_ms / _TEMPO_FLOOR_MS) / math.log(_TEMPO_RATIO)))


def range_bin(position: float) -> int:
    return min(RANGE_BINS - 1, max(0, int(position) // _RANGE_STEP))


def classify(phrase: Phrase) -> Class:
    durations = [duration for duration, _end in phrase.swings]
    highs = [end for i, (_duration, end) in enumerate(phrase.swings) if i % 2 == 0]
    lows = [end for i, (_duration, end) in enumerate(phrase.swings) if i % 2 == 1]
    return (tempo_bin(median(durations)), range_bin(median(lows)), range_bin(median(highs)))


@dataclass
class LearnedModel:
    phrases: dict[Class, list[Phrase]] = field(default_factory=dict)
    successions: dict[Class, dict[Class, int]] = field(default_factory=dict)
    seen: dict[Class, int] = field(default_factory=dict)
    native_cycle_ms: float = 600.0

    def __bool__(self) -> bool:
        return bool(self.phrases)


def measure_native_cycle_ms(model: LearnedModel) -> float:
    weighted: list[tuple[int, float]] = []
    for cls, kept in model.phrases.items():
        weight = model.seen.get(cls, len(kept)) / len(kept)
        weighted.extend((duration, weight) for phrase in kept for duration, _end in phrase.swings)
    if not weighted:
        return LearnedModel.native_cycle_ms
    weighted.sort()
    half = sum(weight for _duration, weight in weighted) / 2
    run = 0.0
    for duration, weight in weighted:
        run += weight
        if run >= half:
            return 2.0 * duration
    return 2.0 * weighted[-1][0]


def save(model: LearnedModel, path: Path) -> None:
    document = {
        "version": 1,
        "phrase_swings": PHRASE_SWINGS,
        "phrases": {
            _key(cls): [[list(swing) for swing in phrase.swings] for phrase in kept]
            for cls, kept in model.phrases.items()
        },
        "successions": {
            _key(cls): {_key(after): count for after, count in following.items()}
            for cls, following in model.successions.items()
        },
        "seen": {_key(cls): count for cls, count in model.seen.items()},
        "native_cycle_ms": model.native_cycle_ms,
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(document, handle, separators=(",", ":"))


def load(path: Path) -> LearnedModel:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    return LearnedModel(
        phrases={
            _class(key): [Phrase(tuple(tuple(swing) for swing in swings)) for swings in kept]
            for key, kept in document["phrases"].items()
        },
        successions={
            _class(key): {_class(after): count for after, count in following.items()}
            for key, following in document["successions"].items()
        },
        seen={_class(key): count for key, count in document["seen"].items()},
        native_cycle_ms=float(document.get("native_cycle_ms", LearnedModel.native_cycle_ms)),
    )


def _key(cls: Class) -> str:
    return ",".join(str(part) for part in cls)


def _class(key: str) -> Class:
    tempo, low, high = (int(part) for part in key.split(","))
    return (tempo, low, high)


def next_class(model: LearnedModel, rng: random.Random, after: Class | None) -> Class:
    following = model.successions.get(after) if after is not None else None
    choices = {cls: count for cls, count in (following or model.seen).items()
               if cls in model.phrases}
    if not choices:
        choices = {cls: len(kept) for cls, kept in model.phrases.items()}
    classes = list(choices)
    return rng.choices(classes, weights=[choices[cls] for cls in classes])[0]


def draw_phrase(model: LearnedModel, rng: random.Random, cls: Class) -> Phrase:
    return rng.choice(model.phrases[cls])

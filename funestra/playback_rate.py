from __future__ import annotations

__all__ = [
    "RATE_STEP",
]

MIN_RATE = 0.25
MAX_RATE = 2.0
RATE_STEP = 0.25

_NAMED_RATES = {"min": MIN_RATE, "max": MAX_RATE}


def clamp_rate(rate: float) -> float:
    return max(MIN_RATE, min(MAX_RATE, rate))


def format_rate(rate: float) -> str:
    return f"{rate:g}×"


def parse_rate(said: str) -> float | None:
    named = _NAMED_RATES.get(said.lower())
    if named is not None:
        return named
    try:
        return float(said)
    except ValueError:
        return None

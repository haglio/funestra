"""The one title every Funestra's HUD leads with.

Three Funestras draw a HUD in this family — the two satellites and the Main
Funestra, whichever of Kino or Genau runs on it — and each one's title says what is
selecting what you are looking at.  They say different *things*: a satellite has a
loop over a map of clips, an act filter and a browse order; the primary has a
compilation, a length mode and a pace.  What they must not differ on is the
*grammar* — which fact comes first, which word names the lock, when a fact is worth
saying at all — because a reader glancing between two screens is reading one
sentence in two places.

So the slots and the wording live here, and each Funestra fills them with its own
words.  Kept apart from :mod:`funestra.hud`, which owns how a HUD is
*drawn*: this owns what it *says*, and a Funestra can want one without the other.
"""
from __future__ import annotations

from collections.abc import Sequence

SEPARATOR = " · "

# What the lock is called.  Every Funestra has this one and means the same by it —
# repeat-one on whatever is on screen — so it is named once, here.
LOCKED_LABEL = "Locked"
UNLOCKED_LABEL = "Unlocked"

# What the two browse orders are called.  Every Funestra browses in one of them —
# newest-first, or shuffled — and a reader glancing between two screens is
# comparing the same two words, so they are named once here.
LATEST_LABEL = "Latest"
SHUFFLE_LABEL = "Shuffle"

# What F-mode is called.  Every Funestra has one of its own, and a reader glancing
# between two screens is comparing the same switch, so it is named once here.
F_MODE_LABEL = "F-Mode"

PLAYBACK_SPEED_LABEL = "Playback speed"


# What Origenerator's enhanced-only filter is called where a HUD names it.  A
# plural of the thing itself, the way every other filter slot on these lines
# names what it kept rather than what it dropped: the reader wants to know what
# is on the screen, not what is missing from it.
ENHANCED_LABEL = "Enhanceds"


def looping_label(axis: str) -> str:
    """What a Funestra says while it is looping *axis* — "seed", "action".

    The lit loop button on a HUD's map and this phrase are the same fact said
    twice, once as a light and once in words, so a reader who saw the light on
    one screen finds the same sentence on the other.  Named here because more
    than one Funestra draws that map now: a satellite looping a seed row, and a
    hosted Origenerator's show, which IS a seed row played round and round.
    """
    return f"Looping {axis}s"


def hud_title(*, locked: bool, playing_set: str = "", order: str = "",
              f_mode: bool = False, enhanced: bool = False,
              filters: Sequence[str] = ()) -> str:
    """The title, from the slots a Funestra fills.

    Read left to right, the slots answer a reader's questions in the order they
    occur: what is playing (*playing_set* — a satellite's loop, the primary's
    compilation), whether it is being held (*locked*), how it moves on (*order* —
    Latest/Shuffle, or the seconds an unheld flick stays up), and what has been cut
    out of it — *f_mode* first, cutting the whole library to the funscripted
    videos, then *enhanced*, keeping only the images Origenerator has enhanced
    (a slot of its own, so the HUD that carries the switch for it has the word
    for it too without owning the label), then *filters*, each narrowing what is
    left.

    Every slot but the lock is optional and an empty one takes no room, so a Funestra
    with nothing to say in it prints nothing rather than an empty phrase.  The one
    rule beyond that: a *playing_set* drops "Unlocked", because a set playing
    through holds nothing and naming the absence of a hold that was never on offer
    is noise.  "Locked" still joins it — a hold taken inside a set is a stop at one
    clip of it, which is worth saying.
    """
    parts = [playing_set] if playing_set else []
    if locked:
        parts.append(LOCKED_LABEL)
    elif not playing_set:
        parts.append(UNLOCKED_LABEL)
    if order:
        parts.append(order)
    if f_mode:
        parts.append(F_MODE_LABEL)
    if enhanced:
        parts.append(ENHANCED_LABEL)
    parts.extend(word for word in filters if word)
    return SEPARATOR.join(parts)

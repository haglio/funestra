"""Which frame of the flick the motion is showing.

Genau scrubs a looping flick with the motion it is driving the device with. The
loop is one action and back: through its front half the flick travels from A to
B, through its back half from B to A, and the two ends are the one place a jump
between halves is invisible, because the frame there serves both.

The frame is a picture of where the device is: parked shows A, fully retracted
shows B, and everything between shows the frame that far through the half that
is showing. A motion that only works the middle of the axis therefore only
shows the middle of a half — the extent of what you watch is the extent of what
moves.

What half is showing is which way the device is going: it climbs through the
front half while the device retracts, and through the back half while the device
returns. So the cursor only ever goes forward. A turn short of an end does not
rewind the half it is in; it swaps to the other half, which reads as the cursor
carrying on forward and jumping across the frames the motion did not reach — up
to the far end when it turns high, across the loop's seam when it turns low. A
full motion reaches both ends and plays the whole flick once with no jump,
exactly as it always has.

The swap waits until the device has drawn back from its extreme by a frame's
worth of travel, so a reading that wobbles by less than one frame holds the
cursor rather than moving it — forward or back.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = []  # package-internal: no sibling reaches anything here


@dataclass
class FlickScrub:
    """Which half of the flick is showing, and the extreme of the current pass.

    ``back_half`` is False while the device is retracting (the front half) and
    True while it returns (the back half). ``extreme`` is the highest the device
    has reached this pass while retracting, or the lowest while returning: the
    cursor rides it, so a wobble short of a frame cannot pull the cursor back.
    """

    back_half: bool = False
    extreme: float = 0.0
    height: float = 0.0
    started: bool = False


def scrub_flick(state: FlickScrub, height: float, frame_count: int) -> float:
    """The flick's display phase for a device sitting at *height*.

    *height* is 0 at the park and 1 fully retracted — the device's own position
    on its axis.

    The returned phase is a place around the loop: 0 and 1 are its A end, 0.5 the
    B end, and the halves are the two ways between. It only ever advances (or
    jumps forward). Whoever is showing the flick turns it into a frame.
    """
    height = min(1.0, max(0.0, height))
    epsilon = 2.0 / frame_count if frame_count > 0 else 0.0
    if not state.started:
        state.extreme, state.started = height, True
    elif not state.back_half:
        if height >= state.extreme:
            state.extreme = height
        elif height <= state.extreme - epsilon:
            state.back_half, state.extreme = True, height
    elif height <= state.extreme:
        state.extreme = height
    elif height >= state.extreme + epsilon:
        state.back_half, state.extreme = False, height
    state.height = height
    half = state.extreme / 2
    return 1.0 - half if state.back_half else half

"""The timing questions every scripted Funestra asks of a funscript.

A funscript is a JSON list of (time, position) actions authored against one
video; what the document itself is belongs to the whole family and lives in
:mod:`app_support.funscript`.  What is here is what a *Funestra* asks of one:
where sustained action begins (so the OSR2 rests through a long quiet lead-in
instead of drifting toward it), whether a given playhead sits in a quiet stretch
(``is_resting_at`` — what the kino-mode handoff hands to the Robot Hand), where
the action next picks up (``next_active_ms`` — where a jump-to-the-action
lands), plus loop-boundary snapping for A-B loops.
"""
from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from app_support.funscript import read_actions

from .max_intensity import depth
from .robot_hand import FULL_INTENSITY, toward_the_park

__all__ = [
    "PARK_TOUCH_WAIT_CAP_MS",
    "Funscript",
    "snap_loop",
]

_BASE_THRESHOLD = 95
_MIN_LOOP_MS = 500

# How far a marked loop boundary may travel to land on a cycle base.  Snapping
# exists so the seam falls at the foot of a cycle rather than mid-cycle, and a
# cycle runs a few hundred milliseconds to about a second — so a base further
# out than this belongs to some other action, not to the cycle the mark landed
# in, and honoring the mark beats looping something nobody marked.
_SNAP_TOLERANCE_MS = 1000

# A funscript whose sustained action does not begin until at least this far in
# has a long enough quiet lead-in that the OSR2 should rest at its parked
# position rather than drift toward a still-distant action.  The same value
# doubles as the gap that marks a leading action as an isolated stray blip:
# real action is densely sampled, so the first action closely followed by
# another (gap below this) is where it truly begins.
QUIET_LEAD_IN_MS = 5000

# How long the device takes to rise from its parked rest to a cluster's opening
# action: long enough to read as a deliberate approach rather than a twitch,
# short enough that it rests through nearly all of a long quiet stretch.
_RISE_MS = 1000

# How long the device takes to settle onto its park when whoever was driving
# lets go — the interval the waypoint driver's park command carries, and the one
# the broker's own park matches.  Public because the drive trace draws the walk
# down over it rather than dropping to park in one sample.
PARK_SETTLE_MS = 500

# How long the device takes to walk between one driver's last position and the
# next one's first, at a kino-mode handoff.  A couple of seconds: long enough to
# read as a hand-over rather than a jump, short enough to leave the device
# resting for most of the buffer.  Both directions use it — down onto the park
# when the script takes over, up to the motion's floor when the hand does — so the
# two ramps are the same shape mirrored, which is what the buffer looks like.
HANDOFF_RAMP_MS = 2000

# How long the arbiter will wait, past a turn boundary, for a motion whose
# floor rests ON the park to come down and touch it — the one case where the
# handoff needs no ramp at all: the blue swings on to its touch-down and the
# grey runs flat from there, so the device is set down exactly where the line
# ends.  Long enough for a slow motion's whole cycle, short enough that a
# motion that never comes down cannot stall the script.  Shared with the trace,
# which scans the same span for the same touch it draws the blue ending on.
PARK_TOUCH_WAIT_CAP_MS = 2500

# When the script gives the device back, relative to its cluster's last action.
# Not the same as the lead-in: the lead-in is long because the device needs a
# run-up to the opening action, while at this end the script is done and only
# has to be out of the way in time for the other driver's climb.  Sized so the
# climb lands exactly at the far end of the quiet, where the motion has always
# resumed — the buffer keeps its shape (glide down, rest, climb) instead of
# either being spent on nothing or eaten whole by the ramp.
QUIET_LEAD_OUT_MS = QUIET_LEAD_IN_MS - HANDOFF_RAMP_MS

# The quickest run of the OSR2's linear axis from its floor to its ceiling.
# The axis is driven by a pair of hobby servos -- the build's MG996R is rated
# 0.13 seconds per 60 degrees unloaded, and a full run is more than two of
# those sweeps, under load -- so a quarter second is as fast as it goes.
FASTEST_FULL_TRAVEL_MS = 250

# The same figure as a rate: position units a second, the axis running 0-100.
_MAX_TRAVEL_PER_SECOND = 100_000 / FASTEST_FULL_TRAVEL_MS

# How far either side of a moment its fastest move still governs the depth.
# The look ahead is short, so the shrink arrives just before the burst that
# needs it; the look back is long, so the depth walks up again over several
# cycles rather than pumping between one cycle and the next.
_DEPTH_LOOKAHEAD_MS = 500
_DEPTH_RECOVERY_MS = 3000

_LOOP_REACH_MS = 300_000

# Past any real playhead, so a turn's start alone orders it against a position
# in :meth:`Funscript.turn_bounds_at`'s bisect.
_MS_MAX = 1 << 62


@dataclass
class Funscript:
    actions: list[tuple[int, int]]

    def __post_init__(self) -> None:
        self._times = [a[0] for a in self.actions]
        self._dense_times = self._compute_dense_times()
        self._onsets = self._compute_onsets()
        self._turns = self._compute_turns()
        self._demand = self._compute_demand()
        # The device's plan sampled on a fixed grid, for
        # :meth:`planned_trace_window` to take windows of.
        self._planned_grid_key: tuple[float, float, int] | None = None
        self._planned_grid_values: tuple[float, ...] = ()
        self._looped_key: tuple[int, int] | None = None
        self._looped_value: Funscript = self

    @property
    def first_real_event_ms(self) -> int | None:
        """Onset of sustained action past a long quiet lead-in, else None.

        Returns the time of the first action that is closely followed by
        another (i.e. where dense action begins), skipping any isolated stray
        blips at the very start.  Returns None when action begins promptly, so
        callers drive from the top; otherwise the OSR2 rests at its parked
        position until this time.
        """
        if not self._onsets:
            return None
        onset = self._onsets[0]
        return onset if onset >= QUIET_LEAD_IN_MS else None

    def is_parked_at(self, position_ms: int) -> bool:
        """Whether the device's plan at *position_ms* is its parked position.

        The neutral pose through every stretch the script is not actively
        driving — the quiet lead-in, interior gaps, the tail past the last
        action — is the park, not wherever the last action happened to leave
        the device: it drops to park as a cluster ends and rises again
        ``_RISE_MS`` ahead of the next one, timed to meet its opening action.
        Inside a cluster it is never parked, and isolated stray blips out in
        the quiet stretches are noise the device sits out.
        """
        if not self._dense_times:
            return True
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if nxt is not None and nxt - position_ms <= _RISE_MS:
            return False
        # Between two dense actions of one cluster the device is mid-cycle;
        # between clusters (or past the last) it rests.
        return not (
            prv is not None and nxt is not None and nxt - prv < QUIET_LEAD_IN_MS
        )

    def planned_position_at(self, position_ms: int, speed: float = 1.0, *,
                            max_intensity: int = FULL_INTENSITY) -> float:
        """Where the device is *planned* to be at *position_ms*, 0-100.

        The script's own motion through each dense cluster, the parked position
        through the quiet stretches, and a straight climb between them — from
        park at the foot of the rise to the cluster's opening action as it
        fires.  This is the line the waypoint driver walks, so a trace drawn
        from it is the device's coming motion rather than a picture the device
        contradicts (:meth:`position_at` holds the last position across gaps
        the device spends parked).
        """
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if self.is_parked_at(position_ms):
            if prv is not None and position_ms - prv < PARK_SETTLE_MS:
                # The drop out of a cluster is the driver's own park glide,
                # drawn: a straight descent from the last action onto the rest.
                return (self.paced_position_at(prv, speed, max_intensity=max_intensity)
                        * (1 - (position_ms - prv) / PARK_SETTLE_MS))
            return 0.0
        rising = (
            nxt is not None and position_ms < nxt
            and (prv is None or nxt - prv >= QUIET_LEAD_IN_MS)
        )
        if rising:
            return (self.paced_position_at(nxt, speed, max_intensity=max_intensity)
                    * (1 - (nxt - position_ms) / _RISE_MS))
        return self.paced_position_at(position_ms, speed, max_intensity=max_intensity)

    def planned_trace_window(self, start_ms: int, span_ms: int, count: int,
                             speed: float = 1.0, *, max_intensity: int = FULL_INTENSITY,
                             ) -> tuple[tuple[float, ...], float]:
        """The device's plan as a picture: *count* + 1 knot samples covering
        *span_ms* from the knot at or before *start_ms*, as 0-1 heights, and how
        far past that knot *start_ms* sits as a fraction of one.

        The plan rather than the script's own interpolated line — parked through
        the quiet stretches, rising to meet each cluster, the script's shape
        inside one — so a trace drawn from it is the device's coming motion
        rather than a picture the device contradicts.

        The values are the fixed grid's own, never resampled and never blended:
        the script does not change while it plays, so its picture is computed
        once and reread, and the fraction goes to the drawer, which shifts the
        whole polyline left by it.  Reading the grid *at* the shifted positions
        instead morphed the heights at fixed columns every frame, so the shape
        changed while it moved.  The extra trailing sample is the knot just past
        the span's far edge, so the shifted line still reaches the border.  Past
        the end of the script the device rests at its park, so the picture does
        too."""
        if count <= 0 or not self.actions:
            return (), 0.0
        step = span_ms / max(1, count - 1)
        samples = count + 1
        if step <= 0:
            return (0.0,) * samples, 0.0
        grid = self._planned_grid(step, speed, max_intensity)
        whole, frac = divmod(start_ms / step, 1)
        first = int(whole)
        return tuple(
            grid[first + i] if 0 <= first + i < len(grid) else 0.0
            for i in range(samples)
        ), frac

    def _planned_grid(self, step_ms: float, speed: float, max_intensity: int) -> tuple[float, ...]:
        """The whole plan at one sample every *step_ms*, from zero, memoized --
        by the rate and the max intensity as well, the plan's depth being theirs too."""
        if self._planned_grid_key != (step_ms, speed, max_intensity):
            last = self.actions[-1][0]
            count = int(last / step_ms) + 2 if step_ms > 0 else 1
            self._planned_grid_key = (step_ms, speed, max_intensity)
            self._planned_grid_values = tuple(
                self.planned_position_at(round(i * step_ms), speed, max_intensity=max_intensity) / 100
                for i in range(count))
        return self._planned_grid_values

    def looped(self, start_ms: int, end_ms: int) -> Funscript:
        period = end_ms - start_ms
        if period <= 0:
            return self
        if self._looped_key != (start_ms, end_ms):
            one_pass = [(t, p) for t, p in self.actions if start_ms <= t < end_ms]
            passes = range(-1, _LOOP_REACH_MS // period + 2)
            laid_out_until = end_ms + _LOOP_REACH_MS
            self._looped_key = (start_ms, end_ms)
            self._looped_value = Funscript(actions=[
                (t + k * period, p) for k in passes for t, p in one_pass
                if t + k * period < laid_out_until])
        return self._looped_value

    def position_at(self, position_ms: int) -> float:
        """Where the script has the device at *position_ms*, 0-100.

        Interpolated between the surrounding actions and held flat outside them,
        the same motion the waypoint driver asks the OSR2 for.
        """
        if not self.actions:
            return 0.0
        index = bisect.bisect_right(self._times, position_ms) - 1
        if index < 0:
            return float(self.actions[0][1])
        if index >= len(self.actions) - 1:
            return float(self.actions[-1][1])
        (t0, p0), (t1, p1) = self.actions[index], self.actions[index + 1]
        if t1 <= t0:
            return float(p1)
        return p0 + (p1 - p0) * (position_ms - t0) / (t1 - t0)

    def paced_position_at(self, position_ms: int, speed: float, *,
                          max_intensity: int = FULL_INTENSITY) -> float:
        """Where the script has the device at *position_ms* with the video
        playing at *speed*, 0-100 -- its own shape until the rate asks the
        device to travel faster than it can, or than *max_intensity* lets it, and
        from there the same shape scaled toward the park.
        """
        return toward_the_park(self.position_at(position_ms),
                               self._depth_scale(position_ms, speed, max_intensity))

    def _depth_scale(self, position_ms: int, speed: float, max_intensity: int) -> float:
        """What fraction of its depth the script keeps at playback rate *speed*.

        The device's own allowance is never below what this stretch already
        asks for at 1x, which is what makes normal speed and every slowed one a
        no-op rather than something the caller has to remember to skip.
        """
        if not self._demand:
            return 1.0
        demand = self._demand_at(position_ms)
        if demand <= 0:
            return 1.0
        reachable = 1.0 if speed <= 1.0 else min(
            1.0, max(_MAX_TRAVEL_PER_SECOND / demand, 1.0) / speed)
        return min(reachable, depth(demand * speed, max_intensity))

    def _demand_at(self, position_ms: int) -> float:
        """The neighborhood's fastest travel at *position_ms*, interpolated
        because the envelope only steps at an action and the depth would jump
        mid-cycle by the whole size of the step."""
        i = bisect.bisect_left(self._times, position_ms)
        if i <= 0:
            return self._demand[0]
        if i >= len(self._demand):
            return self._demand[-1]
        t0, t1 = self._times[i - 1], self._times[i]
        d0, d1 = self._demand[i - 1], self._demand[i]
        if t1 <= t0:
            return d1
        return d0 + (d1 - d0) * (position_ms - t0) / (t1 - t0)

    def _compute_demand(self) -> list[float]:
        """The fastest travel the script asks for around each action, in
        position units a second."""
        travel = [0.0] * len(self.actions)
        for k in range(1, len(self.actions)):
            (t0, p0), (t1, p1) = self.actions[k - 1], self.actions[k]
            if t1 > t0:
                travel[k] = abs(p1 - p0) * 1000 / (t1 - t0)
        fastest: deque[int] = deque()
        out: list[float] = []
        ahead = 0
        for t in self._times:
            while ahead < len(self._times) and self._times[ahead] <= t + _DEPTH_LOOKAHEAD_MS:
                while fastest and travel[fastest[-1]] <= travel[ahead]:
                    fastest.pop()
                fastest.append(ahead)
                ahead += 1
            while fastest and self._times[fastest[0]] < t - _DEPTH_RECOVERY_MS:
                fastest.popleft()
            out.append(travel[fastest[0]] if fastest else 0.0)
        return out

    def next_active_ms(self, position_ms: int) -> int | None:
        """Where scripted action next starts up after *position_ms*, else None.

        The answer is the first cycle of the next dense cluster, not the buffer
        :meth:`is_resting_at` allows ahead of it: this is where a seek asking for
        the action lands, and landing in the buffer would leave several seconds
        of nothing on the near side of it.  A position inside a cluster is
        carried past that cluster to the one after — "next" is always forward,
        never the run already playing — and None means nothing scripted remains.
        """
        i = bisect.bisect_right(self._onsets, position_ms)
        return self._onsets[i] if i < len(self._onsets) else None

    def _compute_onsets(self) -> list[int]:
        """The start of each dense cluster: a dense time with no dense
        predecessor inside QUIET_LEAD_IN_MS, i.e. the far side of a quiet
        stretch.  The first is where the script begins in earnest, which is what
        first_real_event_ms reports once it is far enough in to be worth parking
        for; the rest are where it resumes after each interior gap.
        """
        onsets: list[int] = []
        previous: int | None = None
        for t in self._dense_times:
            if previous is None or t - previous >= QUIET_LEAD_IN_MS:
                onsets.append(t)
            previous = t
        return onsets

    def _compute_dense_times(self) -> list[int]:
        """Times of actions that belong to a dense cluster — those with a
        neighbor within QUIET_LEAD_IN_MS.  Isolated stray blips are excluded,
        the same standard first_real_event_ms uses to find where action begins.
        """
        dense: list[int] = []
        for k, (t, _p) in enumerate(self.actions):
            prev_close = k > 0 and t - self.actions[k - 1][0] < QUIET_LEAD_IN_MS
            next_close = (
                k + 1 < len(self.actions)
                and self.actions[k + 1][0] - t < QUIET_LEAD_IN_MS
            )
            if prev_close or next_close:
                dense.append(t)
        return dense

    def _compute_turns(self) -> list[tuple[int, int]]:
        """The stretches the script holds the device for, in order.

        One per dense cluster, opened QUIET_LEAD_IN_MS before its first action
        and closed QUIET_LEAD_OUT_MS after its last — early enough that the next
        driver's climb out of the park lands where the motion has always
        resumed.

        Two clusters merge when their QUIET_LEAD_IN_MS neighborhoods overlap:
        whether the script gives the device back between two is about whether
        there is room for the other driver to do anything, which is the long
        lead-in and not the short lead-out.  Measured on the lead-out, a
        six-second gap would open a turn of a few hundred milliseconds — a
        handoff there and back before anything could happen.
        """
        turns: list[list[int]] = []
        for t in self._dense_times:
            low, high = t - QUIET_LEAD_IN_MS, t + QUIET_LEAD_OUT_MS
            if turns and low <= turns[-1][1] + (QUIET_LEAD_IN_MS - QUIET_LEAD_OUT_MS):
                turns[-1][1] = high
            else:
                turns.append([low, high])
        return [(low, high) for low, high in turns]

    def turn_bounds_at(self, position_ms: int) -> tuple[int | None, int | None]:
        """When the stretch holding *position_ms* begins and ends, in ms.

        Whose stretch it is, is :meth:`is_resting_at` — this says only where it
        starts and stops, and None at either end means it runs past the edge of
        the video.  Whoever draws the handoff needs the *boundary*, not the
        classification: a ramp that walks the device between the park and a
        motion has to be anchored to the moment the device changed hands, and
        anchored to anything recomputed per frame it slides around under its
        own picture.
        """
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        if index >= 0 and position_ms <= self._turns[index][1]:
            return self._turns[index]
        before = self._turns[index][1] if index >= 0 else None
        after = self._turns[index + 1][0] if index + 1 < len(self._turns) else None
        return (before, after)

    def is_resting_at(self, position_ms: int) -> bool:
        """True when position_ms sits outside every stretch the script holds the
        device for — a funscript's lead-in, an interior gap, the tail.

        In kino mode the orchestrator hands these stretches to the Robot Hand;
        inside a turn the funscript drives.  Read straight off :meth:`turn_bounds_at`'s own
        turns rather than measured again here, because the two answers have to
        be the same answer: the arbiter flips the device on this, and the trace
        anchors its ramps to those bounds, so a rule stated twice is a seam that
        can disagree with the handoff it is drawing.
        """
        if not self._turns:
            return True
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        return not (index >= 0 and position_ms <= self._turns[index][1])


def snap_loop(fs: Funscript | None, in_ms: int, out_ms: int) -> tuple[int, int]:
    """The marked range as a loop: ordered, at least _MIN_LOOP_MS long, and each
    end pulled outward onto a nearby cycle base so the seam is not mid-cycle.

    A boundary with no base within _SNAP_TOLERANCE_MS keeps the time it was
    marked at: unbounded, a snap walks to whatever base comes next, and on a
    script that rarely reaches _BASE_THRESHOLD that turns a five-second mark into
    a range too long to play as a loop at all.
    """
    lo, hi = min(in_ms, out_ms), max(in_ms, out_ms)
    # Widen before snapping: both snaps only ever move a boundary outward, so a
    # mark shorter than a loop is lengthened here and stays long afterwards.
    hi = max(hi, lo + _MIN_LOOP_MS)
    # No funscript is simply nothing to snap to — a plain clip loop keeps its mark.
    actions = fs.actions if fs is not None else []
    bases = [t for t, p in actions if p >= _BASE_THRESHOLD]
    return _snap_back(bases, lo), _snap_forward(bases, hi)


def _snap_back(bases: list[int], boundary_ms: int) -> int:
    """*boundary_ms* pulled back to the latest base close enough before it."""
    i = bisect.bisect_right(bases, boundary_ms)
    if i and boundary_ms - bases[i - 1] <= _SNAP_TOLERANCE_MS:
        return bases[i - 1]
    return boundary_ms


def _snap_forward(bases: list[int], boundary_ms: int) -> int:
    """*boundary_ms* pushed on to the earliest base close enough ahead of it."""
    i = bisect.bisect_left(bases, boundary_ms)
    if i < len(bases) and bases[i] - boundary_ms <= _SNAP_TOLERANCE_MS:
        return bases[i]
    return boundary_ms


def load(path: Path) -> Funscript:
    """The script at *path*, as the pairs the timing questions are asked of.

    What a funscript is lives in :mod:`app_support.funscript`, which is where
    the four repos that read one agree -- including what a document listing no
    actions means, which is none rather than an error.
    """
    return Funscript(
        actions=sorted((a["at"], a["pos"]) for a in read_actions(path))
    )

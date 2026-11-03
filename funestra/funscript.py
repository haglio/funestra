from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from app_support.funscript import read_actions

from .max_intensity import depth
from .robot_hand import FULL_INTENSITY, toward_the_park

_BASE_THRESHOLD = 95
_MIN_LOOP_MS = 500

_SNAP_TOLERANCE_MS = 1000

QUIET_LEAD_IN_MS = 5000

_RISE_MS = 1000

PARK_SETTLE_MS = 500

HANDOFF_RAMP_MS = 2000

PARK_TOUCH_WAIT_CAP_MS = 2500

QUIET_LEAD_OUT_MS = QUIET_LEAD_IN_MS - HANDOFF_RAMP_MS

FASTEST_FULL_TRAVEL_MS = 250

_MAX_TRAVEL_PER_SECOND = 100_000 / FASTEST_FULL_TRAVEL_MS

_DEPTH_LOOKAHEAD_MS = 500
_DEPTH_RECOVERY_MS = 3000

_LOOP_REACH_MS = 300_000

_MS_MAX = 1 << 62


@dataclass
class Funscript:
    actions: list[tuple[int, int]]

    def __post_init__(self) -> None:
        self._times = [a[0] for a in self.actions]
        self._dense_times = self._compute_dense_times()
        self._clusters = self._compute_clusters()
        self._onsets = [first for first, _last in self._clusters]
        self._turns = self._compute_turns()
        self._demand = self._compute_demand()
        self._planned_grid_key: tuple[float, float, int] | None = None
        self._planned_grid_values: tuple[float, ...] = ()
        self._looped_key: tuple[int, int] | None = None
        self._looped_value: Funscript = self

    @property
    def first_real_event_ms(self) -> int | None:
        if not self._onsets:
            return None
        onset = self._onsets[0]
        return onset if onset >= QUIET_LEAD_IN_MS else None

    def is_parked_at(self, position_ms: int) -> bool:
        if not self._dense_times:
            return True
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if nxt is not None and nxt - position_ms <= _RISE_MS:
            return False
        return not (
            prv is not None and nxt is not None and nxt - prv < QUIET_LEAD_IN_MS
        )

    def planned_position_at(self, position_ms: int, speed: float = 1.0, *,
                            max_intensity: int = FULL_INTENSITY) -> float:
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if self.is_parked_at(position_ms):
            if prv is not None and position_ms - prv < PARK_SETTLE_MS:
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
        return toward_the_park(self.position_at(position_ms),
                               self._depth_scale(position_ms, speed, max_intensity))

    def _depth_scale(self, position_ms: int, speed: float, max_intensity: int) -> float:
        if not self._demand:
            return 1.0
        demand = self._demand_at(position_ms)
        if demand <= 0:
            return 1.0
        reachable = 1.0 if speed <= 1.0 else min(
            1.0, max(_MAX_TRAVEL_PER_SECOND / demand, 1.0) / speed)
        return min(reachable, depth(demand * speed, max_intensity))

    def _demand_at(self, position_ms: int) -> float:
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
        i = bisect.bisect_right(self._onsets, position_ms)
        return self._onsets[i] if i < len(self._onsets) else None

    def active_ms(self, running_ms: int) -> int:
        return sum(max(0, min(last, running_ms) - first) for first, last in self._clusters)

    def _compute_clusters(self) -> list[tuple[int, int]]:
        clusters: list[list[int]] = []
        for t in self._dense_times:
            if clusters and t - clusters[-1][1] < QUIET_LEAD_IN_MS:
                clusters[-1][1] = t
            else:
                clusters.append([t, t])
        return [(first, last) for first, last in clusters]

    def _compute_dense_times(self) -> list[int]:
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
        turns: list[list[int]] = []
        for t in self._dense_times:
            low, high = t - QUIET_LEAD_IN_MS, t + QUIET_LEAD_OUT_MS
            if turns and low <= turns[-1][1] + (QUIET_LEAD_IN_MS - QUIET_LEAD_OUT_MS):
                turns[-1][1] = high
            else:
                turns.append([low, high])
        return [(low, high) for low, high in turns]

    def turn_bounds_at(self, position_ms: int) -> tuple[int | None, int | None]:
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        if index >= 0 and position_ms <= self._turns[index][1]:
            return self._turns[index]
        before = self._turns[index][1] if index >= 0 else None
        after = self._turns[index + 1][0] if index + 1 < len(self._turns) else None
        return (before, after)

    def is_resting_at(self, position_ms: int) -> bool:
        if not self._turns:
            return True
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        return not (index >= 0 and position_ms <= self._turns[index][1])


def snap_loop(fs: Funscript | None, in_ms: int, out_ms: int) -> tuple[int, int]:
    lo, hi = min(in_ms, out_ms), max(in_ms, out_ms)
    hi = max(hi, lo + _MIN_LOOP_MS)
    actions = fs.actions if fs is not None else []
    bases = [t for t, p in actions if p >= _BASE_THRESHOLD]
    return _snap_back(bases, lo), _snap_forward(bases, hi)


def _snap_back(bases: list[int], boundary_ms: int) -> int:
    i = bisect.bisect_right(bases, boundary_ms)
    if i and boundary_ms - bases[i - 1] <= _SNAP_TOLERANCE_MS:
        return bases[i - 1]
    return boundary_ms


def _snap_forward(bases: list[int], boundary_ms: int) -> int:
    i = bisect.bisect_left(bases, boundary_ms)
    if i < len(bases) and bases[i] - boundary_ms <= _SNAP_TOLERANCE_MS:
        return bases[i]
    return boundary_ms


def load(path: Path) -> Funscript:
    return Funscript(
        actions=sorted((a["at"], a["pos"]) for a in read_actions(path))
    )

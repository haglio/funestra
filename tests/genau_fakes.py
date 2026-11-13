from __future__ import annotations

from pathlib import Path


class FakeLoader:
    def __init__(self, *, loading: bool = False):
        self.load_state = type("LoadState", (), {"loading": loading})()
        self.loaded_adopt_calls = 0
        self.prefetch_adopt_calls = 0

    def adopt_loaded_flick_if_ready(self) -> None:
        self.loaded_adopt_calls += 1

    def adopt_prefetch_if_ready(self) -> None:
        self.prefetch_adopt_calls += 1


class FakeNotifier:
    def __init__(self):
        self.visible_updates: list[bool] = []

    def notify_visible(self, is_visible: bool) -> None:
        self.visible_updates.append(is_visible)


class FakeRenderer:
    def __init__(self, *, path: Path | None = None, entry=None, current_frame_index: int | None = None):
        self.current_flick_path = path
        self._entry = entry
        self.current_frame_index = current_frame_index
        self.display_calls: list[int] = []
        self.portrait: bool | None = None

    def current_flick_entry(self):
        return self._entry

    def show_frame_at(self, index: int) -> None:
        self.display_calls.append(index)
        self.current_frame_index = index


class FakeSelection:
    def __init__(self, *, current_number: int = 2, count: int = 5, pending_flick_name: str | None = None):
        self.current_number = current_number
        self.count = count
        self.step_calls: list[int] = []
        self.discard_calls = 0
        self.prefetch_calls = 0
        self.adopt_calls = 0
        self.pending_flick_name = pending_flick_name

    def step(self, delta: int) -> None:
        self.step_calls.append(delta)

    def condemn_current(self) -> bool:
        self.discard_calls += 1
        return True

    def adopt_pending_flick(self) -> bool:
        self.adopt_calls += 1
        return False

    def request_nearby_prefetch(self) -> None:
        self.prefetch_calls += 1


class FakeTCodeSender:
    def __init__(self):
        self.sends: list[tuple[float, float]] = []
        self.take_overs = 0
        self.rests = 0
        self.hand_overs = 0
        self.let_go_position: int | None = None
        self.closed = False
        self.wanted: bool | None = None
        self._position = 5000
        self._motion_phase = 0.0

    def want(self, wanted: bool) -> None:
        self.wanted = wanted

    def maybe_send(self, phase: float, now: float, *, output: bool = True) -> None:
        if output:
            self.sends.append((phase, now))
        self._motion_phase = phase

    def take_over(self) -> None:
        self.take_overs += 1
        self.let_go_position = None

    def rest_at_floor(self) -> None:
        self.rests += 1
        self._motion_phase = 0.0

    def set_motion_phase(self, phase: float) -> None:
        self._motion_phase = phase

    def hand_over(self) -> None:
        self.hand_overs += 1
        self.let_go_position = self._position
        self.rest_at_floor()

    def current_position(self) -> int:
        return self._position

    @property
    def motion_phase(self) -> float:
        return self._motion_phase

    def close(self) -> None:
        self.closed = True

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from . import learned_motion
from .flick_flip import HALF_A_LOOP
from .genau_controls import GenauControls
from .osr2_visualizer import TRACE_SAMPLES, DriveHud, DrivePublisher
from .robot_hand import (
    MIN_BPM,
    POSITION_MAX,
    WaveformShape,
    control_limits,
    position_fraction,
    trace_window,
)

_AUTO_AMPLITUDE = 100
_AUTO_CENTER = 50


@dataclass(frozen=True)
class AutoMotion:
    phase: float
    bpm: float

    @property
    def height(self) -> float:
        return position_fraction(self.phase, amplitude=_AUTO_AMPLITUDE,
                                 center=_AUTO_CENTER)

    def trace(self, seconds: float, beats_per_loop: float,
              ) -> tuple[list[float], float, float]:
        heights, slide = trace_window(
            WaveformShape.SINE, _AUTO_AMPLITUDE, _AUTO_CENTER, phase=self.phase,
            bpm=self.bpm / beats_per_loop if self.bpm > 0 else 0.0,
            samples=TRACE_SAMPLES, span_s=seconds)
        return heights[:TRACE_SAMPLES], slide, heights[TRACE_SAMPLES]


class GenauVisualizer:
    def __init__(
        self,
        *,
        controls: GenauControls,
        beats_per_loop: float,
        tcode_sender=None,
        drive_file: Path | None = None,
    ):
        self.robot_hand = controls.robot_hand
        self.learned = controls.learned_motion_state
        self.flick_advance = controls.flick_advance_state
        self.beats_per_loop = beats_per_loop
        self.tcode_sender = tcode_sender
        self._drive_publisher = None if drive_file is None else DrivePublisher(drive_file)
        self.drive: DriveHud | None = None
        self._auto_turns = 0
        self._auto_phase: float | None = None

    def update(self, now: float, auto: AutoMotion | None = None) -> None:
        self.drive = self._build_drive_hud(self._counted_up(auto))
        self._publish_drive(self.drive, now)

    def _counted_up(self, auto: AutoMotion | None) -> AutoMotion | None:
        if auto is None:
            return None
        if self._auto_phase is not None and auto.phase < self._auto_phase - HALF_A_LOOP:
            self._auto_turns += 1
        self._auto_phase = auto.phase
        return replace(auto, phase=self._auto_turns + auto.phase)

    def _build_drive_hud(self, auto: AutoMotion | None = None) -> DriveHud:
        ds = self.robot_hand
        display_seconds = 60.0 * self.beats_per_loop / MIN_BPM
        if auto is not None:
            position, let_go = round(auto.height * POSITION_MAX), None
            waveform, slide, edge = auto.trace(display_seconds, self.beats_per_loop)
        else:
            position, let_go, start_phase = 0, None, 0.0
            if self.tcode_sender is not None:
                position = self.tcode_sender.current_position()
                start_phase = self.tcode_sender.motion_phase
                if self.tcode_sender.let_go_position is not None:
                    let_go = self.tcode_sender.let_go_position / POSITION_MAX
            waveform, slide, edge = self._trace(
                display_seconds, start_phase,
                ds.bpm / 60.0 / self.beats_per_loop if ds.bpm > 0 else 1.0)

        limits = control_limits(ds)
        return DriveHud(
            speed=ds.speed,
            amplitude=ds.amplitude,
            center=ds.center,
            shape=ds.shape.value,
            position=position,
            advance_interval=(
                self.flick_advance.interval if self.flick_advance else 0
            ),
            spd_at_max=limits.spd_at_max,
            spd_at_min=limits.spd_at_min,
            amp_at_max=limits.amp_at_max,
            amp_at_min=limits.amp_at_min,
            ctr_at_max=limits.ctr_at_max,
            ctr_at_min=limits.ctr_at_min,
            trace_seconds=display_seconds,
            let_go=let_go,
            waveform=tuple(waveform),
            slide=slide,
            edge=edge,
            max_intensity=ds.max_intensity,
        )

    def _trace(self, display_seconds: float, start_phase: float,
               phase_per_second: float) -> tuple[list[float], float, float | None]:
        if self.learned is not None and self.learned.active:
            heights, slide = learned_motion.trace_window(
                self.learned, self.robot_hand, TRACE_SAMPLES, display_seconds)
        else:
            ds = self.robot_hand
            heights, slide = trace_window(
                ds.shape, ds.amplitude, ds.center, phase=start_phase,
                bpm=phase_per_second * 60.0, samples=TRACE_SAMPLES, span_s=display_seconds)
        return heights[:TRACE_SAMPLES], slide, heights[TRACE_SAMPLES]

    def _publish_drive(self, hud: DriveHud, now: float) -> None:
        if self._drive_publisher is not None:
            self._drive_publisher.publish(hud, now)

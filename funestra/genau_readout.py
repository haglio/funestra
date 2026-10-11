"""What Genau says for the console to draw: the drive readout."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from . import learned_motion, wave_stack
from .drive_readout import TRACE_SAMPLES, DriveHud, publish_drive
from .genau_controls import GenauControls
from .renamed import answers_to_old_names
from .robot_hand import (
    MIN_BPM,
    POSITION_MAX,
    WaveformShape,
    control_limits,
    position_fraction,
    trace_window,
)

__all__: list[str] = []  # package-internal: no sibling reaches anything here

# How often the drive readout goes out for the console to draw.  Its trace
# scrolls, so it cannot wait on a change the way the status file does -- 25/s is
# well under Genau's refresh rate and well over what reads as smooth.
_DRIVE_PUBLISH_INTERVAL_S = 0.04

# The travel the device uses when it runs itself: the whole axis, centered.  Its
# free mode is firmware, and the only things it says over serial are its tempo
# and its downbeat -- nothing about how far it swings -- so a picture of it is a
# plain swing end to end.
_AUTO_AMPLITUDE = 100
_AUTO_CENTER = 50


@dataclass(frozen=True)
class AutoMotion:
    """The motion the OSR2 makes for itself, as much of it as the PC can see.

    ``phase`` is where the broker's beat has reached and ``bpm`` how fast it is
    going round -- the same beat the flick's own frames are scrubbed by while the
    device has the room, so the line and the picture move together.
    """

    phase: float
    bpm: float

    @property
    def height(self) -> float:
        """Where the swing is now, 0-1 of the device's travel."""
        return position_fraction(self.phase, amplitude=_AUTO_AMPLITUDE,
                                 center=_AUTO_CENTER)

    def trace(self, seconds: float, beats_per_loop: float,
              ) -> tuple[list[float], float, float]:
        """The swing over *seconds* as the readout draws every trace: the
        heights on knots, how far the line is shifted, and the knot past the
        border."""
        heights, slide = trace_window(
            WaveformShape.SINE, _AUTO_AMPLITUDE, _AUTO_CENTER, phase=self.phase,
            bpm=self.bpm / beats_per_loop if self.bpm > 0 else 0.0,
            samples=TRACE_SAMPLES, span_s=seconds)
        return heights[:TRACE_SAMPLES], slide, heights[TRACE_SAMPLES]


@answers_to_old_names({"clip_advance": "flick_advance"})
class GenauReadout:
    def __init__(
        self,
        *,
        controls: GenauControls,
        beats_per_loop: float,
        tcode_sender=None,
        drive_file: Path | None = None,
    ):
        self.robot_hand = controls.robot_hand
        self.cruise_control = controls.cruise_control_state
        self.learned = controls.learned_motion_state
        self.flick_advance = controls.flick_advance_state
        self.beats_per_loop = beats_per_loop
        self.tcode_sender = tcode_sender
        self.drive_file = drive_file
        self.drive: DriveHud | None = None
        self._last_drive_publish = 0.0
        # The broker's beat, counted up across its wraps: the auto trace's
        # knots stay put only on a phase that never starts round again.
        self._auto_turns = 0
        self._auto_phase: float | None = None

    def update(self, now: float, auto: AutoMotion | None = None) -> None:
        """Build the drive readout and publish it for the console.

        *auto* is the device running itself, and None while the Robot Hand
        drives.  Either way there is a line: a picture of whatever is actually
        reaching the device.  The numbers beside it stay the hand's -- what its
        controls will move when it takes the device back -- and whoever draws
        them dims them, exactly as while a funscript drives.
        """
        self.drive = self._build_drive_hud(self._counted_up(auto))
        self._publish_drive(self.drive, now)

    def _counted_up(self, auto: AutoMotion | None) -> AutoMotion | None:
        if auto is None:
            return None
        if self._auto_phase is not None and auto.phase < self._auto_phase - 0.5:
            self._auto_turns += 1
        self._auto_phase = auto.phase
        return replace(auto, phase=self._auto_turns + auto.phase)

    def _build_drive_hud(self, auto: AutoMotion | None = None) -> DriveHud:
        ds = self.robot_hand
        # Show enough time that one whole cycle is visible at the slowest speed.
        # Published with the readout, because a funscript drawn on this same trace
        # has to be sampled over the same stretch and the console has nowhere
        # else to learn it — two spans would make a handoff look like a jump.
        display_seconds = 60.0 * self.beats_per_loop / MIN_BPM
        # Under the broker the sender's position and its let-go height are both
        # stale: the device is where the broker's beat puts it, and a handoff
        # Genau made before the device took itself away describes nothing here.
        if auto is not None:
            position, let_go = round(auto.height * POSITION_MAX), None
            waveform, slide, edge = auto.trace(display_seconds, self.beats_per_loop)
        else:
            position, let_go, start_phase = 0, None, 0.0
            if self.tcode_sender is not None:
                position = self.tcode_sender.current_position()
                start_phase = self.tcode_sender.motion_phase
                if self.tcode_sender.let_go_position is not None:
                    # The height the device was handed over at, 0-1 — the one
                    # number the trace cannot recompute once the phase has rested.
                    let_go = self.tcode_sender.let_go_position / POSITION_MAX
            waveform, slide, edge = self._trace(
                display_seconds, start_phase,
                ds.bpm / 60.0 / self.beats_per_loop if ds.bpm > 0 else 1.0)

        # Which arrow would do nothing — the readout dims those.  The same six
        # the status file publishes, from the same answer.
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
        """The motion sampled forward as the readout draws it — and as the
        console draws a funscript over it, which is why both are the same span
        — as the samples, how far the line is shifted, and the knot past the
        border.

        Every source is read on knots a fixed stretch of its own clock apart,
        so the picture holds still between knots and slides by the fraction,
        rather than being redrawn at fixed columns every frame: the wave on its
        phase, cruise control's sum on the stack's clock (its waves each run at
        their own speed, so it is walked in time), the learned motion on its
        script.
        """
        if self.learned is not None and self.learned.active:
            heights, slide = learned_motion.trace_window(
                self.learned, self.robot_hand, TRACE_SAMPLES, display_seconds)
        elif self.cruise_control is not None and self.cruise_control.stack:
            heights, slide = wave_stack.trace_window(
                self.cruise_control.stack, self.cruise_control.clock,
                TRACE_SAMPLES, display_seconds, max_intensity=self.robot_hand.max_intensity)
        else:
            ds = self.robot_hand
            heights, slide = trace_window(
                ds.shape, ds.amplitude, ds.center, phase=start_phase,
                bpm=phase_per_second * 60.0, samples=TRACE_SAMPLES, span_s=display_seconds)
        return heights[:TRACE_SAMPLES], slide, heights[TRACE_SAMPLES]

    def _publish_drive(self, hud: DriveHud, now: float) -> None:
        """Say the readout for the console to draw, at a fraction of the refresh
        rate: the trace scrolls, so this cannot wait for a change the way the
        status file does, and is throttled instead, well under the refresh rate
        and well over what the eye reads as smooth.
        """
        if self.drive_file is None:
            return
        if now - self._last_drive_publish < _DRIVE_PUBLISH_INTERVAL_S:
            return
        self._last_drive_publish = now
        publish_drive(self.drive_file, hud)

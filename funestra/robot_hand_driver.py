"""The Robot Hand put on the wire, and the device changing hands.

The wire format and the UDP sink live in :mod:`funestra.tcode`, beneath every
OSR2 driver in the family; :class:`RobotHandTCodeDriver` is the one that turns
the beat engine's continuous phase into rate-limited position commands, shaped
by the hand's state -- the mirror of :class:`funestra.tcode_driver.FunscriptTCodeDriver`,
which turns a script's waypoints into the same commands.

The hand does not hold the device the whole time.  In kino mode a funscript
takes it for every scripted stretch, and an orchestrator's pause takes it too,
so the driver is told on that edge -- :class:`DeviceHandoff` watches for it --
and climbs out of the park when it gets the device back, or latches where the
device was when it loses it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import learned_motion
from .flick_flip import HALF_A_LOOP
from .funscript import HANDOFF_RAMP_MS
from .robot_hand import POSITION_MAX, phase_to_position
from .tcode import HandoffGlide, TCodeSink, format_tcode_command

if TYPE_CHECKING:
    from .robot_hand import RobotHandState

# The rise only exists when there is a gap to climb: at full amplitude the
# motion's floor IS the park, and holding the swing there would delay a resume
# that already starts from where the device sits.  Two percent of the travel,
# the trace's own park epsilon.
_RISE_SKIP_BELOW = 200


class RobotHandTCodeDriver:
    def __init__(
        self,
        sink: TCodeSink,
        *,
        robot_hand: RobotHandState | None = None,
        learned=None,
        min_interval: float = 1.0 / 30.0,
    ) -> None:
        self._sink = sink
        self._robot_hand = robot_hand
        # The learned motion's, when it has the hand: phrases of real scripting
        # with no phase at all, asked where they are on their own clock.
        self._learned = learned
        self._min_interval = min_interval
        self._last_send_time: float = 0.0
        self._last_phase: float = 0.0
        self._motion_phase: float = 0.0
        # The hand does not drive the device the whole time — in kino mode a
        # funscript takes it for every scripted stretch — so it comes back to a
        # device parked wherever the script left it.  Armed here and on every
        # takeover.
        self._glide = HandoffGlide()
        self._glide.begin()
        # The rise out of the park: 1.0 is the motion at its own full size;
        # anything lower scales the held phase-0 position, so the device climbs
        # from the park to the motion's floor before the swing begins — the mirror of
        # the glide down that ends the hand's turn.  A takeover zeroes it; the
        # clock starts on the first send after that.
        self._rise = 1.0
        self._rise_started: float | None = None
        # Where the device was when this driver last handed it over, in T-Code
        # units; None while it holds the device.  Published with the readout —
        # see :meth:`hand_over`.
        self._let_go_position: int | None = None
        self._output_was_off = False

    def take_over(self) -> None:
        """The hand has the device again: resume the motion from the foot of its
        swing, and ease onto it.

        The funscript's turn leaves the device at its park and the frozen phase
        could be anywhere in the cycle, so the motion resumes from the floor
        rather than from wherever it froze.  The motion's floor can sit well
        above the park (amplitude under 100, a raised center), so the swing
        holds while the device climbs park-to-floor over
        :data:`~funestra.funscript.HANDOFF_RAMP_MS`, then begins.  A floor
        already on the park skips the climb and the motion starts at once.
        """
        self.rest_at_floor()
        if self._compute_position() > _RISE_SKIP_BELOW:
            self._rise = 0.0
            self._rise_started = None
            # let_go stays published through the climb: it means "my published
            # wave is the frozen phase-0 one, not yet running", and through the
            # rise that is still true.  Cleared when the climb completes and
            # the wave actually starts — the readers that re-anchor on that
            # edge (the trace's descent top after an OmniPause realign) need
            # the edge to land when the realigned wave is finally live.
        else:
            # No gap to climb — the motion starts at once, so the publish is
            # live from this tick — and a climb this takeover interrupted must
            # not leave its fraction scaling every position from here on.
            self._rise = 1.0
            self._let_go_position = None
        self._glide.begin()

    def hand_over(self) -> None:
        """The hand is losing the device: remember where, and let go.

        The height the swing was at is latched BEFORE the phase rests, because
        resting destroys it — a paused driver publishes the motion it will
        resume with, not the position it stopped at — and it is the one number
        the trace cannot recompute when it draws the descent.  Nothing is sent:
        the driver taking the device owns walking it down (its first park is
        the handoff ramp).
        """
        self._let_go_position = self.current_position()
        self.rest_at_floor()

    def rest_at_floor(self) -> None:
        """Put the motion at the foot of its swing — phase 0, where every
        waveform shape's raw value is 0: the lowest point the current center
        and amplitude reach, and the nearest the motion comes to the park.

        Called when the hand loses the device as well as when it takes it back
        (:meth:`take_over`), so the readout published through a funscript's
        turn shows the motion that will actually resume, not wherever the
        swing froze.
        """
        self._motion_phase = 0.0
        if self._learned is not None:
            learned_motion.rest_at_floor(self._learned)

    def set_motion_phase(self, phase: float) -> None:
        self._motion_phase = phase

    def _compute_position(self) -> int:
        if self._learned is not None and self._learned.active:
            return round(POSITION_MAX * learned_motion.position(
                self._learned, self._robot_hand) / 100)
        if self._robot_hand is not None:
            return phase_to_position(
                self._motion_phase,
                shape=self._robot_hand.shape,
                amplitude=self._robot_hand.amplitude,
                center=self._robot_hand.center,
            )
        return phase_to_position(self._motion_phase)

    def current_position(self) -> int:
        """Where the device is being sent right now — scaled by the rise while
        it is still climbing out of the park, so the published readout and the
        dot riding it follow the climb rather than sitting on the floor."""
        return round(self._compute_position() * self._rise)

    @property
    def motion_phase(self) -> float:
        return self._motion_phase

    @property
    def let_go_position(self) -> int | None:
        """Where the device was handed over, in T-Code units — None while this
        driver still has it."""
        return self._let_go_position

    def maybe_send(self, phase: float, now: float, *, output: bool = True) -> None:
        if self._rise < 1.0:
            # Climbing out of the park: the swing holds at the floor (phase 0)
            # while the device rises to it, so the phase is tracked but not
            # advanced, and the sent position is the floor scaled by how far
            # the climb has come.
            if self._rise_started is None:
                self._rise_started = now
            self._rise = min(1.0, (now - self._rise_started) / (HANDOFF_RAMP_MS / 1000))
            if self._rise >= 1.0:
                # The climb is done and the wave runs from here: the publish is
                # live again, which is what clearing let_go announces.
                self._let_go_position = None
            self._last_phase = phase
        else:
            # Accumulate continuous motion phase, detecting wraps.
            delta = phase - self._last_phase
            if delta < -HALF_A_LOOP:
                delta += 1.0
            self._motion_phase += max(0.0, delta)
            self._last_phase = phase

        if not output:
            self._output_was_off = True
            return
        if self._output_was_off:
            self._output_was_off = False
            self._glide.begin()
        elapsed = now - self._last_send_time
        if elapsed < self._min_interval:
            return
        interval_ms = max(1, min(9999, round(elapsed * 1000)))
        position = round(self._compute_position() * self._rise)
        # A motion tick asks the device to be at the next phase position in the
        # time one tick takes, which is right while the hand has been driving
        # all along and is a slam the moment it has just taken the device back:
        # the device is where a funscript left it, and the phase has run on
        # without it.  The glide floors the interval for its own length, so
        # these ticks re-aim at a target the device is always given long enough
        # to reach.
        self._sink.send(format_tcode_command(
            "L0", position, self._glide.interval_ms(interval_ms, now)))
        self._last_send_time = now

    def want(self, wanted: bool) -> None:
        self._sink.want(wanted)

    def close(self) -> None:
        self._sink.close()


class DeviceHandoff:
    """The device changing hands, both directions.

    The hand drives the device while it is playing and lets go of it when it is
    not, and the driver is told on that edge, so it can climb out of the park or
    walk the motion down and rest it -- deliberately asymmetric: letting go
    latches where the device was, which is the one number the drive readout's
    trace cannot recompute afterwards.  The broker is the orchestrator's to park
    and resume.

    It is an edge rather than a state.  Told the same thing twice the second
    says nothing: a second walk-down would move the latch.
    """

    def __init__(self, *, playing: bool, tcode_sender=None):
        self.tcode_sender = tcode_sender
        # Seeded from the state itself, so a PAUSE queued before the first tick
        # reads as a real falling edge against the state this was built in.
        self._playing = playing

    def watch(self, playing: bool) -> None:
        was, self._playing = self._playing, playing
        if playing == was:
            return
        if self.tcode_sender is not None:
            if playing:
                self.tcode_sender.take_over()
            else:
                self.tcode_sender.hand_over()

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .broker_feed import BrokerFeed, snapshot
from .file_channel import publish_whole
from .flick_advance import set_elapsed
from .flick_under_the_device import FlickUnderTheDevice
from .flicks_on_screen import FlicksOnScreen
from .genau_controls import GenauControls, apply_runtime_command
from .genau_files import GenauFiles
from .genau_status import FlickOnScreen, StatusFile, build_status_text
from .genau_visualizer import AutoMotion, GenauVisualizer
from .hands_device import HandsDevice
from .robot_hand_beat import Beat, BeatTuning, advance_beat, advance_phase
from .send_clock import SendClock
from .tick_failures import TickFailures

SEND_THREAD = "genau-osr2-send"


def _what_is_read_beside_the_frames(controls: GenauControls) -> Callable[[Path], None]:
    def read(flick: Path) -> None:
        controls.flick_flip.read_ahead(flick)
        controls.flick_frame_rates.read_ahead(flick)
    return read


class FlickOnItsOwn:
    def __init__(self) -> None:
        self._flick: Path | None = None
        self._since = 0.0

    def frame_at(self, flick: Path | None, now: float, frame_count: int,
                 frames_per_second: float) -> int:
        if flick != self._flick:
            self._flick, self._since = flick, now
        return int((now - self._since) * frames_per_second) % frame_count


class GenauRefreshController:
    def __init__(self, controls: GenauControls, flicks: FlicksOnScreen, *, broker: BrokerFeed,
                 files: GenauFiles, tuning: BeatTuning, tcode_sender=None,
                 logger: logging.Logger, now_source: Callable[[], float] = time.monotonic,
                 start_thread: Callable | None = None,
                 publish: Callable[[Path, str], bool] = publish_whole):
        if controls.robot_hand is None:
            raise ValueError("Genau runs with the hand's state and no hand-less mode")
        self.controls = controls
        self.flicks = flicks
        flicks.read_on_the_decode_thread(_what_is_read_beside_the_frames(controls))
        self.broker = broker
        self.files = files
        self._status = StatusFile(files.status_file)
        self.tuning = tuning
        self.logger = logger
        self.failures = TickFailures(logger)
        self.now_source = now_source
        self._up: tuple[object, float | None] = (None, None)
        self._on_its_own = FlickOnItsOwn()
        self.motion = controls.hand_motion
        self._the_motion_s_turn = threading.RLock()
        self._hand_driving: Beat | None = None
        self.device = HandsDevice(controls.robot_hand, controls.tcode_enabled, tcode_sender,
                                  sent_between_passes=start_thread is not None)
        self.under_the_device = FlickUnderTheDevice(controls, self.device)
        self.visualizer = GenauVisualizer(
            controls=controls,
            beats_per_loop=tuning.beats_per_loop,
            tcode_sender=tcode_sender,
            drive_file=files.drive,
            publish=publish,
        )
        if start_thread is not None:
            stop = controls.stop_event
            start_thread(
                target=SendClock(
                    self.send_between_passes, TickFailures(logger, "send"),
                    stopped=(lambda: False) if stop is None else stop.is_set, clock=now_source).run,
                name=SEND_THREAD)

    def send_between_passes(self, now: float) -> None:
        with self._the_motion_s_turn:
            beat = self._hand_driving
            if beat is None:
                return
            self.motion.tick(now, start_fraction=self.device.where_in_its_travel)
            advance_phase(self.controls.engine, beat, self.tuning, now=now)
            self.device.send(self.controls.engine.phase, now)

    def refresh(self) -> None:
        try:
            self._refresh_once()
        except Exception as exc:
            self.failures.failed(exc)
            return
        self.failures.worked()

    def _refresh_once(self) -> None:
        now = self.now_source()
        engine = self.controls.engine
        if self._over_a_video:
            self.flicks.adopt_the_flick_asked_for()
        else:
            self.flicks.adopt_whatever_finished_decoding()
            self.controls.flick_flip.follow(self.flicks.path)
        self._drain_commands()

        beat = self._who_is_driving(now)

        self.flicks.heard(not self._over_a_video)

        with self._the_motion_s_turn:
            advance_beat(engine, beat, self.tuning, now=now)
            self.device.drive(engine.phase, now, the_hand_has_it=beat.robot_hand_active)
            self._hand_driving = beat if beat.robot_hand_active else None

        if beat.robot_hand_active:
            self.visualizer.update(now)
        else:
            self.visualizer.update(now, AutoMotion(
                phase=engine.phase, bpm=engine.estimated_bpm or 0.0))

        self.under_the_device.follow_the_room_hold(now)
        if not self._over_a_video:
            self._show_the_frame(beat, now)
            self.flicks.say_what_is_loading()
            self.flicks.fetch_the_ones_nearby()
        self._publish_status(now)

    def _drain_commands(self) -> None:
        commands = self.files.commands(self.logger)
        with self._the_motion_s_turn:
            for cmd in commands:
                apply_runtime_command(cmd, self.controls)

    def _who_is_driving(self, now: float) -> Beat:
        hand = self.controls.robot_hand
        shared = snapshot(self.broker)
        if shared.auto_active:
            self.controls.paused.on = self.files.room_is_paused()
            return Beat(
                robot_hand_active=False,
                auto_active=shared.auto_active,
                raw_bpm=shared.raw_bpm,
                paused=self.controls.paused.on,
                sync_pulse_id=shared.sync_pulse_id,
            )
        self._tick_the_hand(now)
        return Beat(
            robot_hand_active=True,
            auto_active=hand.playing,
            raw_bpm=hand.bpm,
            paused=not hand.playing,
            sync_pulse_id=0,
        )

    def _tick_the_hand(self, now: float) -> None:
        with self._the_motion_s_turn:
            self.motion.tick(now, start_fraction=self.device.where_in_its_travel)
        advance = self.controls.flick_advance_state
        if advance is not None and not self._over_a_video:
            self.flicks.advance(advance, now, playing=self._the_flick_plays)

    @property
    def _the_flick_plays(self) -> bool:
        return self.controls.robot_hand.playing or self.controls.plays_without_the_osr2.on

    def _show_the_frame(self, beat: Beat, now: float) -> None:
        frame_count = self.flicks.frame_count
        if not frame_count:
            return
        if self.controls.plays_without_the_osr2.on:
            path = self.flicks.path
            self.flicks.show_frame(self._on_its_own.frame_at(
                path, now, frame_count, self.controls.flick_frame_rates.of(path)))
            return
        phase = self.controls.engine.phase
        if beat.robot_hand_active:
            if self.under_the_device.stands_still and self.flicks.has_a_frame_up:
                return
            phase = self.under_the_device.phase(frame_count, now, with_no_device=phase)
        self.flicks.show_the_frame_at(self.controls.flick_flip.applied_to(phase))

    @property
    def _over_a_video(self) -> bool:
        return self.controls.hud is not None and self.controls.hud.on

    def _went_up_at(self, now: float) -> float | None:
        path = self.flicks.path
        if path != self._up[0]:
            self._up = (path, None if path is None else now)
        return self._up[1]

    def _publish_status(self, now: float) -> None:
        self._status.write(build_status_text(
            self.controls.robot_hand,
            learned=self.controls.learned_motion_state,
            flick_advance=self.controls.flick_advance_state,
            on_screen=FlickOnScreen(
                self.flicks.path, self.controls.flick_flip.on, self.flicks.portrait,
                self._went_up_at(now), whole=bool(self.flicks.frame_count),
                unreadable=self.flicks.unreadable),
        ))

    def seek_the_time_on_screen(self, seconds: float) -> None:
        if self.controls.flick_advance_state is not None:
            set_elapsed(self.controls.flick_advance_state, seconds)

    def seek_the_flick(self, fraction: float) -> None:
        if self.device.height is None or not self.flicks.frame_count:
            return
        self.under_the_device.stand_at(
            self.controls.flick_flip.applied_to(min(1.0, max(0.0, fraction))))

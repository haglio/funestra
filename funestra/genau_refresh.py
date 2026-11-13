from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .broker_feed import BrokerFeed, snapshot
from .flick_advance import set_elapsed
from .flick_under_the_device import FlickUnderTheDevice
from .flicks_on_screen import FlicksOnScreen
from .genau_controls import GenauControls, apply_runtime_command
from .genau_files import GenauFiles
from .genau_status import FlickOnScreen, build_status_text, write_status_file
from .genau_visualizer import AutoMotion, GenauVisualizer
from .hands_device import HandsDevice
from .robot_hand_beat import Beat, BeatTuning, advance_beat
from .tick_failures import TickFailures


class GenauRefreshController:
    def __init__(self, controls: GenauControls, flicks: FlicksOnScreen, *, broker: BrokerFeed,
                 files: GenauFiles, tuning: BeatTuning, tcode_sender=None,
                 logger: logging.Logger, now_source: Callable[[], float] = time.monotonic):
        if controls.robot_hand is None:
            raise ValueError("Genau runs with the hand's state and no hand-less mode")
        self.controls = controls
        self.flicks = flicks
        self.broker = broker
        self.files = files
        self.tuning = tuning
        self.logger = logger
        self.failures = TickFailures(logger)
        self.now_source = now_source
        self.motion = controls.hand_motion
        self.device = HandsDevice(controls.robot_hand, controls.tcode_enabled, tcode_sender)
        self.under_the_device = FlickUnderTheDevice(controls, self.device)
        self.visualizer = GenauVisualizer(
            controls=controls,
            beats_per_loop=tuning.beats_per_loop,
            tcode_sender=tcode_sender,
            drive_file=files.drive,
        )

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
        self.flicks.adopt_whatever_finished_decoding()
        self.controls.flick_flip.follow(self.flicks.path)
        self._drain_commands()

        beat = self._who_is_driving(now)

        self.flicks.heard(not self._over_a_video)

        advance_beat(engine, beat, self.tuning, now=now)

        self.device.drive(engine.phase, now, the_hand_has_it=beat.robot_hand_active)

        if beat.robot_hand_active:
            self.visualizer.update(now)
        else:
            self.visualizer.update(now, AutoMotion(
                phase=engine.phase, bpm=engine.estimated_bpm or 0.0))

        self.under_the_device.follow_the_room_hold(now)
        self._show_the_frame(beat, now)

        self.flicks.say_what_is_loading()
        self.flicks.fetch_the_ones_nearby()
        self._publish_status()

    def _drain_commands(self) -> None:
        for cmd in self.files.commands(self.logger):
            apply_runtime_command(cmd, self.controls)

    def _who_is_driving(self, now: float) -> Beat:
        hand = self.controls.robot_hand
        shared = snapshot(self.broker)
        if shared.auto_active:
            self.controls.paused.on = self.files.room_is_paused(self.logger)
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
        self.motion.tick(now, start_fraction=self.device.where_in_its_travel)
        advance = self.controls.flick_advance_state
        if advance is not None:
            self.flicks.advance(advance, now, playing=self.controls.robot_hand.playing)

    def _show_the_frame(self, beat: Beat, now: float) -> None:
        frame_count = self.flicks.frame_count
        if not frame_count:
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

    def _publish_status(self) -> None:
        write_status_file(self.files.status_file, build_status_text(
            self.controls.robot_hand,
            learned=self.controls.learned_motion_state,
            flick_advance=self.controls.flick_advance_state,
            on_screen=FlickOnScreen(
                self.flicks.path, self.controls.flick_flip.on, self.flicks.portrait),
        ))

    def seek_the_time_on_screen(self, seconds: float) -> None:
        if self.controls.flick_advance_state is not None:
            set_elapsed(self.controls.flick_advance_state, seconds)

    def seek_the_flick(self, fraction: float) -> None:
        if self.device.height is None or not self.flicks.frame_count:
            return
        self.under_the_device.stand_at(
            self.controls.flick_flip.applied_to(min(1.0, max(0.0, fraction))))

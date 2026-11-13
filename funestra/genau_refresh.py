from __future__ import annotations

from .broker_feed import snapshot
from .device_walk import Walk, the_broker_holding, the_hand_taking_back
from .flick_advance import set_elapsed, tick_flick_advance
from .flick_flip import HALF_A_LOOP
from .flick_renderer import display_index_for_phase
from .flick_scrub import FlickScrub, scrub_flick
from .genau_controls import apply_runtime_command
from .genau_refresh_parts import GenauRefreshParts
from .genau_status import GENAU_STATUS_FILENAME, FlickOnScreen, build_status_text, write_status_file
from .genau_visualizer import AutoMotion, GenauVisualizer
from .main_hud import HELD_HEIGHT, HOLD_VERB
from .robot_hand import POSITION_MAX, phase_for_position_fraction
from .robot_hand_beat import Beat, BeatTuning, advance_beat
from .robot_hand_driver import DeviceHandoff
from .tick_failures import TickFailures


class GenauRefreshController:
    def __init__(self, parts: GenauRefreshParts):
        (controls, broker, loader, notifier, renderer, selection, command_file, paused_file,
         beats_per_loop, bpm_smoothing, sync_strength, set_loading_text, logger, now_source,
         consume_command, read_paused_state, tcode_sender, status_file,
         drive_file) = parts
        self.controls = controls
        self.engine = controls.engine
        self.paused = controls.paused
        self.robot_hand = controls.robot_hand
        if self.robot_hand is None:
            raise ValueError("Genau runs with the hand's state and no hand-less mode")
        self.learned = controls.learned_motion_state
        self.motion = controls.hand_motion
        self.flick_advance = controls.flick_advance_state
        self.hud = controls.hud
        self.tcode_enabled = controls.tcode_enabled
        self.flip = controls.flick_flip
        self.app_hold = controls.app_hold
        self.broker = broker
        self.loader = loader
        self.notifier = notifier
        self.renderer = renderer
        self.selection = selection
        self.command_file = command_file
        self.paused_file = paused_file
        self.beats_per_loop = beats_per_loop
        self.bpm_smoothing = bpm_smoothing
        self.sync_strength = sync_strength
        self.set_loading_text = set_loading_text
        self.logger = logger
        self.failures = TickFailures(logger)
        self.now_source = now_source
        self.consume_command = consume_command
        self.read_paused_state = read_paused_state or (lambda _path, logger=None: False)
        self.tcode_sender = tcode_sender
        self.status_file = status_file or command_file.parent / GENAU_STATUS_FILENAME
        self.handoff = DeviceHandoff(
            playing=self.robot_hand.playing,
            tcode_sender=tcode_sender,
        )
        self.visualizer = GenauVisualizer(
            controls=controls,
            beats_per_loop=beats_per_loop,
            tcode_sender=tcode_sender,
            drive_file=drive_file,
        )
        self._scrub = FlickScrub()
        self._walk: Walk | None = None
        self._held: str | None = None
        self._following = self.robot_hand.playing

    def refresh(self) -> None:
        try:
            self._refresh_once()
        except Exception as exc:
            self.failures.failed(exc)
            return
        self.failures.worked()

    def _refresh_once(self) -> None:
        now = self.now_source()
        self._adopt_whatever_finished_decoding()
        self.flip.follow(self.renderer.current_flick_path)
        self._drain_commands()

        beat = self._who_is_driving(now)

        self.notifier.notify_visible(not self._over_a_video)

        advance_beat(
            self.engine, beat,
            BeatTuning(self.beats_per_loop, self.bpm_smoothing, self.sync_strength),
            now=now,
        )

        self.handoff.watch(self.robot_hand.playing)

        if self.tcode_sender is not None:
            self.tcode_sender.want(beat.robot_hand_active and self.robot_hand.playing
                                   and self.tcode_enabled.on)
            if beat.robot_hand_active and self.robot_hand.playing:
                self.tcode_sender.maybe_send(
                    self.engine.phase, now, output=self.tcode_enabled.on)

        if beat.robot_hand_active:
            self.visualizer.update(now)
        else:
            self.visualizer.update(now, AutoMotion(
                phase=self.engine.phase, bpm=self.engine.estimated_bpm or 0.0))

        self._follow_the_room_hold(now)
        self._show_the_frame(beat, now)

        pending = self.selection.pending_flick_name
        self.set_loading_text(f"Loading {pending}" if pending else None)

        self.selection.request_nearby_prefetch()
        self._publish_status()

    def _adopt_whatever_finished_decoding(self) -> None:
        self.loader.adopt_loaded_flick_if_ready()
        self.loader.adopt_prefetch_if_ready()
        self.selection.adopt_pending_flick()

    def _drain_commands(self) -> None:
        for cmd in self.consume_command(self.command_file, logger=self.logger):
            apply_runtime_command(cmd, self.controls)

    def _who_is_driving(self, now: float) -> Beat:
        shared = snapshot(self.broker)
        if shared.auto_active:
            self.paused.on = self.read_paused_state(
                self.paused_file, logger=self.logger)
            return Beat(
                robot_hand_active=False,
                auto_active=shared.auto_active,
                raw_bpm=shared.raw_bpm,
                paused=self.paused.on,
                sync_pulse_id=shared.sync_pulse_id,
            )
        self._tick_the_hand(now)
        return Beat(
            robot_hand_active=True,
            auto_active=self.robot_hand.playing,
            raw_bpm=self.robot_hand.bpm,
            paused=not self.robot_hand.playing,
            sync_pulse_id=0,
        )

    def _tick_the_hand(self, now: float) -> None:
        self.motion.tick(now, start_fraction=self._where_the_device_is())
        if self.flick_advance is not None:
            entry = self.renderer.current_flick_entry()
            on_screen_flick = (
                self.renderer.current_flick_path if entry and entry.get("frames") else None
            )
            tick_flick_advance(
                self.flick_advance,
                now,
                playing=self.robot_hand.playing,
                on_screen_flick=on_screen_flick,
                step_flick=self.selection.step,
            )

    def _where_the_device_is(self) -> float:
        hand = self.robot_hand
        if self.tcode_sender is None or hand.amplitude <= 0:
            return 0.0
        low = max(0.0, hand.center - hand.amplitude / 2)
        span = min(100.0, hand.center + hand.amplitude / 2) - low
        height = 100.0 * self.tcode_sender.current_position() / POSITION_MAX
        return (height - low) / span if span > 0 else 0.0

    def _follow_the_room_hold(self, now: float) -> None:
        if self.robot_hand.playing and self.tcode_enabled.on:
            self.app_hold.held = None
        held = self.app_hold.held
        if held is not None and held != self._held:
            self._walk = the_broker_holding(self._scrub.height, now, HOLD_VERB[held])
        following = held is None and self.robot_hand.playing
        if following and not self._following:
            self._walk = the_hand_taking_back(self._scrub.height, now)
        self._held, self._following = held, following

    def _show_the_frame(self, beat: Beat, now: float) -> None:
        active_entry = self.renderer.current_flick_entry()
        if not (active_entry and active_entry["frames"]):
            return
        if beat.robot_hand_active and self._the_frame_holds_still:
            return
        frame_count = len(active_entry["frames"])
        display_phase = self.flip.applied_to(
            self._scrub_the_flick(frame_count, now) if beat.robot_hand_active
            else self.engine.phase
        )
        self.renderer.show_frame_at(display_index_for_phase(display_phase, frame_count))

    @property
    def _the_frame_holds_still(self) -> bool:
        return (not self.robot_hand.playing and self._held is None
                and self.renderer.current_frame_index is not None)

    @property
    def _over_a_video(self) -> bool:
        return self.hud is not None and self.hud.on

    def _publish_status(self) -> None:
        write_status_file(self.status_file, build_status_text(
            self.robot_hand,
            learned=self.learned,
            flick_advance=self.flick_advance,
            on_screen=FlickOnScreen(
                self.renderer.current_flick_path, self.flip.on, self.renderer.portrait),
        ))

    def seek_the_time_on_screen(self, seconds: float) -> None:
        if self.flick_advance is not None:
            set_elapsed(self.flick_advance, seconds)

    def seek_the_flick(self, fraction: float) -> None:
        entry = self.renderer.current_flick_entry()
        if self.tcode_sender is None or not (entry and entry["frames"]):
            return
        fraction = self.flip.applied_to(min(1.0, max(0.0, fraction)))
        back_half = fraction > HALF_A_LOOP
        height = 2 * (1 - fraction) if back_half else 2 * fraction
        self._scrub.back_half = back_half
        self._scrub.started = False
        self.tcode_sender.set_motion_phase(phase_for_position_fraction(
            height,
            shape=self.robot_hand.shape,
            amplitude=self.robot_hand.amplitude,
            center=self.robot_hand.center,
            rising=not back_half,
        ))

    def _scrub_the_flick(self, frame_count: int, now: float) -> float:
        if self.tcode_sender is None:
            return self.engine.phase
        return scrub_flick(self._scrub, self._height_of_the_device(now), frame_count)

    def _height_of_the_device(self, now: float) -> float:
        live = self.tcode_sender.current_position() / POSITION_MAX
        if self._walk is None:
            return live
        return self._walk.height_at(now, live if self._held is None else HELD_HEIGHT[self._held])

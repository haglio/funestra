"""The verbs a Funestra answers, driven through its registry one at a time."""
from __future__ import annotations

import threading
from pathlib import Path

from funestra_fakes import FakeTCode, make_playback

from funestra import funestra_verbs
from funestra.funestra_controls import VERBS, FunestraControls, apply_command
from funestra.funestra_verbs import (
    CLEAR_FRAME,
    LOCK_OFF,
    LOCK_ON,
    NEXT,
    NEXT_VERSION,
    PLAY_FILE,
    PLAY_NEXT,
    PREV,
    PREV_VERSION,
    QUIT,
    RELOAD_PLAYLIST,
    SEEK_BACK,
    SEEK_FWD,
    SET_MAX_INTENSITY,
    SET_PACE,
    SET_SPEED,
    SET_TCODE_ENABLED,
    SET_VOLUME,
    SHOW,
    SHOW_FRAME,
    SPEED_DOWN,
    SPEED_UP,
    TOGGLE_LOCK,
    TRASH,
    play_next,
    step_version,
)
from funestra.playlist import PlaylistItem
from funestra.volume import VolumeHud
from funestra.volume_control import RoomVolume, VolumeControl


def _never_reloads() -> None:
    """The reload hook, for the verbs that must not reach it."""
    raise AssertionError("RELOAD_PLAYLIST was not the command under test")


def _controls(tmp_path, *, entries=3, **wired) -> FunestraControls:
    playback, _engine = make_playback(tmp_path, entries=entries)
    return FunestraControls(playback, **{"reload_playlist": _never_reloads, **wired})


class TestApplyCommand:
    def test_a_frame_goes_up_in_place_of_the_picture_until_it_is_cleared(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{SHOW_FRAME} C:/frames/run one-3.png", controls) is True
        assert apply_command(CLEAR_FRAME, controls) is True
        assert engine.swapped == [Path("C:/frames/run one-3.png"), playback.showing]

    def test_a_frame_verb_naming_no_file_is_refused(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{SHOW_FRAME}  ", controls) is False
        assert engine.swapped == []

    def test_set_pace_is_how_long_a_picture_holds_the_screen(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{SET_PACE} 2.5", controls) is True
        assert engine.pace_s == 2.5

    def test_next_and_prev_navigate(self, tmp_path):
        controls = _controls(tmp_path)
        assert apply_command(NEXT, controls) is True
        assert controls.playback.current_video.name == "v1.mp4"
        assert apply_command(PREV, controls) is True
        assert controls.playback.current_video.name == "v0.mp4"

    def test_the_hold_is_named_absolutely_as_every_funestra_names_it(self, tmp_path):
        controls = _controls(tmp_path)
        assert apply_command(LOCK_ON, controls) is True
        assert controls.playback.is_locked is True
        assert apply_command(LOCK_OFF, controls) is True
        assert controls.playback.is_locked is False

    def test_trash_discards_the_current_clip(self, tmp_path):
        controls = _controls(tmp_path)
        assert apply_command(TRASH, controls) is True
        assert [p.name for p in controls.playback.playlist] == ["v1.mp4", "v2.mp4"]

    def test_play_file_plays_the_item_the_line_names(self, tmp_path):
        controls = _controls(tmp_path)
        assert apply_command(f"{PLAY_FILE} {tmp_path / 'v2.mp4'}", controls) is True
        assert controls.playback.current_video == tmp_path / "v2.mp4"

    def test_play_file_takes_the_funscript_column_as_the_clips_script(self, tmp_path):
        controls = _controls(tmp_path)
        script = tmp_path / "v2.funscript"
        script.write_text('{"actions": [{"at": 0, "pos": 20}, {"at": 250, "pos": 80}]}',
                          encoding="utf-8")

        assert apply_command(f"{PLAY_FILE} {tmp_path / 'v2.mp4'}\t{script}", controls) is True

        assert controls.playback.current_video == tmp_path / "v2.mp4"
        assert controls.playback.current_funscript.actions == [(0, 20), (250, 80)]

    def test_play_next_puts_the_item_the_line_names_after_the_one_on_screen(self, tmp_path):
        controls = _controls(tmp_path)
        newcomer, script = tmp_path / "newcomer.mp4", tmp_path / "newcomer.funscript"

        assert apply_command(play_next(PlaylistItem(newcomer, script)), controls) is True

        assert controls.playback.current_video == tmp_path / "v0.mp4"
        assert controls.playback.playlist[1] == newcomer
        assert controls.playback.funscript_of(newcomer) == script

    def test_play_file_takes_the_places_column_as_the_pictures_places(self, tmp_path):
        playback, engine = make_playback(tmp_path, entries=2)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{PLAY_FILE} C:/out/level two.png\t\t0.5,0.5,0.75,0.75",
                             controls) is True

        assert engine.points_told == [((0.5, 0.5, 0.75, 0.75),)]

    def test_play_next_keeps_the_places_its_line_names_for_when_the_item_comes_up(self, tmp_path):
        playback, engine = make_playback(tmp_path, entries=2)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{PLAY_NEXT} C:/out/level two.png\t\t0.5,0.5,0.75,0.75",
                             controls) is True
        playback.step(1)

        assert engine.points_told[-1] == ((0.5, 0.5, 0.75, 0.75),)

    def test_a_version_step_plays_the_rendition_the_family_names_next(self, tmp_path):
        controls = _controls(tmp_path)
        clip = controls.playback.current_video
        other = tmp_path / "v0_sorted.mp4"
        other.write_text("fake")

        assert apply_command(step_version(1, [clip, other]), controls) is True
        assert controls.playback.showing == other

        assert apply_command(step_version(-1, [clip, other]), controls) is True
        assert controls.playback.showing == clip

    def test_two_quick_steps_carrying_one_family_both_land(self, tmp_path):
        """Fun Time reads the file on screen off a status file that lags the
        Funestra, so it sends the family rather than a target: two presses read
        the same status, and a target would have put the same file up twice."""
        controls = _controls(tmp_path)
        clip = controls.playback.current_video
        family = [clip, tmp_path / "v0_sorted.mp4", tmp_path / "v0_small.mp4"]
        for path in family[1:]:
            path.write_text("fake")

        for _ in range(2):
            apply_command(step_version(1, family), controls)

        assert controls.playback.showing == family[2]

    def test_keyword_is_case_insensitive(self, tmp_path):
        controls = _controls(tmp_path)
        assert apply_command("next", controls) is True
        assert controls.playback.current_video.name == "v1.mp4"

    def test_reload_playlist_invokes_the_callback(self, tmp_path):
        calls = []
        controls = _controls(tmp_path, reload_playlist=lambda: calls.append(1))
        assert apply_command(RELOAD_PLAYLIST, controls) is True
        assert calls == [1]

    def test_quit_sets_the_stop_event(self, tmp_path):
        stop = threading.Event()
        assert apply_command(QUIT, _controls(tmp_path, stop_event=stop)) is True
        assert stop.is_set()

    def test_a_build_with_no_stop_event_refuses_quit(self, tmp_path):
        """The headset's Funestras end with the session, never on their own."""
        controls = _controls(tmp_path, stop_event=None)
        assert apply_command(QUIT, controls) is False

    def test_an_unknown_verb_is_refused_and_named_on_the_log(self, tmp_path, caplog):
        controls = _controls(tmp_path)
        with caplog.at_level("WARNING", logger="funestra.funestra_controls"):
            assert apply_command("FLOOP", controls) is False
            assert apply_command("", controls) is False
        assert "FLOOP" in caplog.text

    def test_a_value_on_a_verb_that_takes_none_is_refused(self, tmp_path):
        """Half a command is not a command, and neither is one and a half — the
        same rule the Main Funestra and Genau already keep."""
        controls = _controls(tmp_path)
        assert apply_command(f"{NEXT} 5", controls) is False
        assert controls.playback.current_video.name == "v0.mp4"

    def test_seek_fwd_and_back_move_ten_seconds_through_the_clip_on_screen(self, tmp_path):
        playback, engine = make_playback(tmp_path, entries=2, duration_ms=60_000.0)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)
        engine.position_ms = 20_000.0

        assert apply_command(SEEK_FWD, controls) is True
        assert engine.position_ms == 30_000.0
        assert apply_command(SEEK_BACK, controls) is True
        assert engine.position_ms == 20_000.0
        assert playback.current_video.name == "v0.mp4"

    def test_speed_up_and_down_move_the_rate_a_step_at_a_time(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(SPEED_UP, controls) is True
        assert controls.playback.speed == 1.25
        assert apply_command(SPEED_DOWN, controls) is True
        assert controls.playback.speed == 1.0

    def test_set_speed_takes_either_end_of_the_range_or_a_multiplier(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(f"{SET_SPEED} max", controls) is True
        assert controls.playback.speed == 2.0
        assert apply_command(f"{SET_SPEED} min", controls) is True
        assert controls.playback.speed == 0.25
        assert apply_command(f"{SET_SPEED} 1.5", controls) is True
        assert controls.playback.speed == 1.5

    def test_a_set_speed_naming_no_rate_is_refused_and_leaves_the_rate_alone(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(f"{SET_SPEED} fast", controls) is False
        assert apply_command(SET_SPEED, controls) is False
        assert controls.playback.speed == 1.0

    def test_the_room_switches_its_line_to_the_osr2_on_and_off(self, tmp_path):
        tcode = FakeTCode()
        playback, _engine = make_playback(
            tmp_path, funscripts={0: _one_stroke(tmp_path / "v0.funscript")}, tcode=tcode)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{SET_TCODE_ENABLED} 1", controls) is True
        playback.advance()
        assert apply_command(f"{SET_TCODE_ENABLED} 0", controls) is True
        playback.advance()

        assert len(tcode.updates) == 1

    def test_the_room_holds_its_script_under_the_max_intensity(self, tmp_path):
        tcode = FakeTCode()
        playback, _engine = make_playback(
            tmp_path, funscripts={0: _one_stroke(tmp_path / "v0.funscript")}, tcode=tcode)
        controls = FunestraControls(playback, reload_playlist=_never_reloads)

        assert apply_command(f"{SET_MAX_INTENSITY} 30", controls) is True
        apply_command(f"{SET_TCODE_ENABLED} 1", controls)
        playback.advance()

        assert (tcode.max_intensities, playback.max_intensity) == ([30], 30)

    def test_a_max_intensity_that_is_not_a_number_is_refused_and_moves_nothing(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(f"{SET_MAX_INTENSITY} loud", controls) is False
        assert controls.playback.max_intensity == 100


def _one_stroke(path):
    path.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 500, "pos": 90}]}',
                    encoding="utf-8")
    return path


class TestTheLock:
    def test_the_toggle_flips_it_both_ways(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(TOGGLE_LOCK, controls) is True
        assert controls.playback.is_locked is True
        assert apply_command(TOGGLE_LOCK, controls) is True
        assert controls.playback.is_locked is False


class TestTheRoomsLevel:
    def _controls(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        volume = RoomVolume(engine, dashboard_cmd_file=None, live=True)
        return FunestraControls(playback, reload_playlist=_never_reloads, volume=volume), engine, volume

    def test_set_volume_plays_and_shows_the_level(self, tmp_path):
        controls, engine, volume = self._controls(tmp_path)

        assert apply_command(f"{SET_VOLUME} 70 0", controls) is True

        assert (engine.volume, volume.hud.volume, volume.hud.muted) == (70, 70, False)

    def test_a_mute_plays_silent_but_the_chip_still_shows_where_it_was_set(self, tmp_path):
        controls, engine, volume = self._controls(tmp_path)

        assert apply_command(f"{SET_VOLUME} 70 1", controls) is True

        assert (engine.volume, volume.hud.volume, volume.hud.muted) == (0, 70, True)

    def test_without_a_mute_flag_the_level_is_not_muted(self, tmp_path):
        controls, engine, volume = self._controls(tmp_path)

        assert apply_command(f"{SET_VOLUME} 40", controls) is True

        assert (engine.volume, volume.hud.muted) == (40, False)

    def test_a_level_it_cannot_read_leaves_the_sound_alone(self, tmp_path):
        controls, engine, _volume = self._controls(tmp_path)

        assert apply_command(f"{SET_VOLUME} loud", controls) is False
        assert apply_command(SET_VOLUME, controls) is False
        assert engine.volume == 100

    def test_a_build_with_no_volume_of_its_own_refuses_a_level(self, tmp_path):
        controls = _controls(tmp_path)

        assert apply_command(f"{SET_VOLUME} 40", controls) is False

    def test_a_funestra_whose_sound_is_its_own_takes_the_level_and_mute_it_is_handed(
            self, tmp_path):
        playback, engine = make_playback(tmp_path)
        volume = VolumeControl(engine)
        controls = FunestraControls(playback, reload_playlist=_never_reloads, volume=volume)

        assert apply_command(f"{SET_VOLUME} 40 0", controls) is True

        assert (engine.volume, engine.muted, volume.hud) == (40, False, VolumeHud(volume=40))


class TestWhoHasTheWindow:
    def test_show_names_which_user_has_the_window_in_the_rooms_own_spelling(self, tmp_path):
        shown = []
        controls = _controls(tmp_path, show=lambda name: shown.append(name) or name == "genau")

        assert apply_command(f"{SHOW} Genau", controls) is True
        assert apply_command(f"{SHOW} slideshow", controls) is False
        assert shown == ["genau", "slideshow"]

    def test_a_build_with_nobody_to_show_refuses_it(self, tmp_path):
        assert apply_command(f"{SHOW} genau", _controls(tmp_path)) is False


def test_every_verb_a_funestra_answers_is_spelled_in_the_familys_vocabulary():
    assert set(VERBS) == {
        NEXT, PREV, LOCK_ON, LOCK_OFF, TOGGLE_LOCK, TRASH, NEXT_VERSION, PREV_VERSION,
        SEEK_FWD, SEEK_BACK, SPEED_UP, SPEED_DOWN, SET_SPEED, PLAY_FILE, PLAY_NEXT,
        RELOAD_PLAYLIST, SET_PACE, SHOW_FRAME, CLEAR_FRAME, QUIT, SET_TCODE_ENABLED,
        SET_MAX_INTENSITY, SET_VOLUME, SHOW,
    }
    assert all(getattr(funestra_verbs, verb) == verb for verb in VERBS)

from __future__ import annotations

import json

from funestra_fakes import FakeTCode
from funestra_fakes import make_playback as _make_playback

from funestra.play_points import PlayPoints
from funestra.playback_rate import MAX_RATE, MIN_RATE
from funestra.seeking import GIVE_UP_AFTER


class TestLoadAndPlay:
    def test_init_loads_first_entry_and_plays(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        assert engine.opened == [tmp_path / "v0.mp4"]
        assert engine.paused is False
        assert playback.current_video == tmp_path / "v0.mp4"

    def test_init_start_paused_tells_engine_to_pause(self, tmp_path):
        playback, engine = _make_playback(tmp_path, start_paused=True)

        assert playback.is_paused
        assert engine.paused is True


class TestNavigation:
    def test_step_advances_and_wraps(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.step(1)
        assert engine.opened[-1] == tmp_path / "v1.mp4"
        assert playback.current_video == tmp_path / "v1.mp4"

        playback.step(1)
        assert engine.opened[-1] == tmp_path / "v0.mp4"
        assert playback.current_video == tmp_path / "v0.mp4"

        playback.step(-1)
        assert engine.opened[-1] == tmp_path / "v1.mp4"


class TestSeeking:
    def test_seek_to_reaches_the_engine(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        playback.seek_to(1_500.0)

        assert engine.seeks == [1_500.0]

    def test_a_step_through_the_clip_stops_at_either_end_of_it(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=30_000.0)

        engine.position_ms = 4_000.0
        playback.seek_by(-10_000)
        engine.position_ms = 26_000.0
        playback.seek_by(10_000)

        assert engine.seeks == [0.0, 30_000.0]

    def test_a_seek_leaves_the_playlist_and_the_prefetch_where_they_are(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)

        playback.seek_to(2_000.0)

        assert playback.current_video == tmp_path / "v0.mp4"
        assert engine.staged_next == tmp_path / "v1.mp4"
        assert engine.opened == [tmp_path / "v0.mp4"]


class TestPause:
    def test_set_paused_drives_the_engine(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        playback.set_paused(True)
        assert playback.is_paused
        assert engine.paused is True

        playback.set_paused(False)
        assert not playback.is_paused
        assert engine.paused is False


class TestPrefetch:
    def test_init_stages_the_next_clip(self, tmp_path):
        _session, engine = _make_playback(tmp_path, entries=3)

        assert engine.staged_next == tmp_path / "v1.mp4"

    def test_single_clip_stages_itself(self, tmp_path):
        _session, engine = _make_playback(tmp_path, entries=1)

        assert engine.staged_next == tmp_path / "v0.mp4"

    def test_step_restages_the_new_next(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)

        playback.step(1)

        assert engine.staged_next == tmp_path / "v2.mp4"

    def test_auto_advance_is_seamless_and_does_not_reload(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.current_video == tmp_path / "v1.mp4"
        assert engine.opened == [tmp_path / "v0.mp4"]
        assert engine.staged_next == tmp_path / "v2.mp4"


class TestAdvance:
    def test_advance_after_eof_steps_to_next(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        engine.simulate_eof_advance()

        playback.advance()

        assert playback.current_video == tmp_path / "v1.mp4"

    def test_advance_before_eof_is_a_noop(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)

        playback.advance()

        assert playback.current_video == tmp_path / "v0.mp4"

    def test_advance_while_paused_never_steps(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_paused(True)
        engine.simulate_eof_advance()

        playback.advance()

        assert playback.current_video == tmp_path / "v0.mp4"

    def test_a_list_of_one_coming_round_has_the_engine_settle_on_it_again(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=1)
        engine.simulate_eof_advance()

        playback.advance()

        assert engine.settled == 1


class TestLock:
    def test_a_locked_playback_repeats_the_same_clip_at_eof(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_locked(True)
        assert playback.is_locked

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.current_video == tmp_path / "v0.mp4"

    def test_lock_engages_native_loop_and_clears_the_prefetch(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.set_locked(True)
        assert engine.loop_file is True
        assert engine.staged_next is None

        playback.set_locked(False)
        assert engine.loop_file is False
        assert engine.staged_next == tmp_path / "v1.mp4"

    def test_an_unlocked_playback_advances_again(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_locked(True)
        playback.set_locked(False)

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.current_video == tmp_path / "v1.mp4"


class TestAPaceOfNought:
    def test_a_pace_of_nought_holds_a_clip_that_finishes_on_screen_without_locking_it(
            self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_pace(0)

        engine.simulate_eof_advance()
        playback.advance()

        assert (playback.current_video, playback.is_locked) == (tmp_path / "v0.mp4", False)

    def test_a_pace_put_back_lets_the_clip_roll_on_again(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_pace(0)
        playback.set_pace(6)

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.current_video == tmp_path / "v1.mp4"

    def test_a_lock_outlasts_a_pace_put_back(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_locked(True)
        playback.set_pace(0)
        playback.set_pace(6)

        assert (engine.loop_file, engine.staged_next) == (True, None)

    def test_the_pace_put_back_under_no_lock_stages_the_next_item(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.set_pace(0)
        assert (engine.loop_file, engine.staged_next) == (True, None)

        playback.set_pace(6)

        assert (engine.loop_file, engine.staged_next) == (False, tmp_path / "v1.mp4")


class TestDiscard:
    def test_discard_removes_current_and_plays_next(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)

        playback.discard()

        assert playback.current_video == tmp_path / "v1.mp4"
        assert [p.name for p in playback.playlist] == ["v1.mp4", "v2.mp4"]
        assert engine.opened[-1] == tmp_path / "v1.mp4"

    def test_discard_on_the_last_entry_wraps_to_the_first(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=3)
        playback.step(2)

        playback.discard()

        assert playback.current_video == tmp_path / "v0.mp4"
        assert [p.name for p in playback.playlist] == ["v0.mp4", "v1.mp4"]

    def test_discard_of_the_only_clip_is_a_noop(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=1)
        opened_before = list(engine.opened)

        playback.discard()

        assert len(playback.playlist) == 1
        assert engine.opened == opened_before


class TestVersions:
    """Another rendition of the clip on screen, put up in the clip's own place:
    the list, and everything Fun Time knows the clip by, stay as they are."""

    @staticmethod
    def _other_version(tmp_path, playback):
        other = tmp_path / f"{playback.current_video.stem}_sorted.mp4"
        other.write_text("fake")
        return other

    def test_a_step_plays_the_other_version_in_the_clips_own_place(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        clip = playback.current_video
        other = self._other_version(tmp_path, playback)

        playback.step_version([clip, other], 1)

        assert engine.opened[-1] == other
        assert (playback.current_video, playback.showing) == (clip, other)
        assert playback.playlist == [clip, tmp_path / "v1.mp4"]

    def test_a_step_back_from_the_clips_own_file_wraps_to_the_last_version(self, tmp_path):
        playback, engine = _make_playback(tmp_path)
        clip = playback.current_video
        other = self._other_version(tmp_path, playback)

        playback.step_version([clip, other], -1)

        assert playback.showing == other

    def test_the_hud_names_the_clip_and_the_file_from_the_first_step(self, tmp_path):
        playback, _engine = _make_playback(tmp_path)
        clip = playback.current_video
        other = self._other_version(tmp_path, playback)
        named = [playback.name_on_screen]

        for _ in range(2):
            playback.step_version([clip, other], 1)
            named.append(playback.name_on_screen)

        assert named == ["v0", f"v0 ({other.name})", f"v0 ({clip.name})"]

    def test_a_clip_come_back_to_names_its_file_only_off_its_own(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        clip = playback.current_video
        other = self._other_version(tmp_path, playback)
        named = []

        for _ in range(2):
            playback.step_version([clip, other], 1)
            playback.step(1)
            playback.step(-1)
            named.append(playback.name_on_screen)

        assert named == [f"v0 ({other.name})", "v0"]

    def test_a_rebuilt_playlist_leaves_every_clip_but_the_one_playing_on_its_own_file(
            self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        first, second = playback.playlist
        other_first = tmp_path / "v0_sorted.mp4"
        other_second = tmp_path / "v1_sorted.mp4"
        for path in (other_first, other_second):
            path.write_text("fake")
        playback.step_version([first, other_first], 1)
        playback.step(1)
        playback.step_version([second, other_second], 1)

        playback.replace_playlist([first, second])

        assert playback.showing == other_second
        playback.step(1)
        assert playback.showing == first

    def test_a_discarded_clip_takes_its_version_with_it(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        clip = playback.current_video
        other = self._other_version(tmp_path, playback)
        playback.step_version([clip, other], 1)

        playback.discard()
        playback.play_file(clip)

        assert playback.showing == clip

    def test_a_family_the_file_on_screen_is_not_in_is_left_alone(self, tmp_path):
        """The step carries the versions of the item the source last saw playing,
        which a playback left to roll on may have moved past."""
        playback, engine = _make_playback(tmp_path, entries=2)
        opened = len(engine.opened)
        stale = tmp_path / "somebody else.mp4"

        playback.step_version([stale, tmp_path / "somebody else_sorted.mp4"], 1)

        assert len(engine.opened) == opened
        assert playback.showing == playback.current_video


def _script(path, *actions):
    path.write_text(json.dumps({"actions": [{"at": at, "pos": pos} for at, pos in actions]}),
                    encoding="utf-8")
    return path


class TestTheScriptOfTheClipOnScreen:
    def test_a_clip_brings_the_funscript_its_playlist_line_named(self, tmp_path):
        script = _script(tmp_path / "v1.funscript", (0, 0), (400, 90))
        playback, _engine = _make_playback(tmp_path, entries=2, funscripts={1: script})

        assert playback.current_funscript is None
        playback.step(1)
        assert playback.current_funscript.actions == [(0, 0), (400, 90)]

    def test_a_clip_played_from_outside_the_playlist_brings_its_script(self, tmp_path):
        playback, _engine = _make_playback(tmp_path)
        newcomer = tmp_path / "brought_back.mp4"
        newcomer.write_text("fake")
        script = _script(tmp_path / "brought_back.funscript", (0, 10), (300, 70))

        playback.play_file(newcomer, script)

        assert playback.current_funscript.actions == [(0, 10), (300, 70)]

    def test_a_rebuilt_playlist_brings_the_scripts_it_was_written_with(self, tmp_path):
        playback, _engine = _make_playback(
            tmp_path, entries=2, funscripts={0: _script(tmp_path / "v0.funscript", (0, 0), (100, 99))})
        clip = tmp_path / "v0.mp4"
        rescripted = _script(tmp_path / "v0 again.funscript", (0, 50), (200, 60))

        playback.replace_playlist([clip, tmp_path / "v1.mp4"], {clip: rescripted})

        assert playback.current_funscript.actions == [(0, 50), (200, 60)]


FACE = ((0.4, 0.1, 0.6, 0.3),)
HANDS = ((0.1, 0.6, 0.3, 0.8), (0.7, 0.6, 0.9, 0.8))


class TestThePlacesOfThePictureOnScreen:
    def test_a_picture_brings_the_places_its_playlist_line_named(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, points_of_interest={1: FACE})

        playback.step(1)

        assert engine.points_told == [FACE]

    def test_a_picture_with_none_takes_the_places_of_the_one_before_away(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, points_of_interest={0: FACE})

        playback.step(1)

        assert engine.points_told == [FACE, ()]

    def test_no_place_is_ever_spoken_of_where_no_picture_has_one(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.step(1)
        playback.show_frame(tmp_path / "frame.png")

        assert engine.points_told == []

    def test_a_picture_played_from_outside_the_playlist_brings_its_places(self, tmp_path):
        playback, engine = _make_playback(tmp_path)
        newcomer = tmp_path / "brought back.png"

        playback.play_file(newcomer, points_of_interest=HANDS)

        assert engine.points_told == [HANDS]

    def test_a_rebuilt_playlist_brings_the_places_it_was_written_with(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.replace_playlist([tmp_path / "v0.mp4", tmp_path / "v1.mp4"],
                                  points_of_interest={tmp_path / "v0.mp4": FACE})

        assert engine.points_told == [FACE]

    def test_a_frame_put_up_over_a_picture_has_none_of_the_pictures_places(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, points_of_interest={0: FACE})

        playback.show_frame(tmp_path / "frame.png")

        assert engine.points_told == [FACE, ()]

    def test_a_finished_picture_put_up_brings_its_places_once_the_list_names_them(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        finished = tmp_path / "v0 finished.png"
        playback.show_frame(finished)

        playback.replace_playlist([finished, tmp_path / "v1.mp4"],
                                  points_of_interest={finished: HANDS})

        assert engine.points_told == [HANDS]

    def test_a_picture_rolled_onto_by_itself_brings_its_places(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, points_of_interest={1: FACE})

        engine.simulate_eof_advance()
        playback.advance()

        assert engine.points_told == [FACE]


def _driving(tmp_path, *, entries=2, scripted=(0, 1), locked=False):
    tcode = FakeTCode()
    scripts = {index: _script(tmp_path / f"v{index}.funscript", (0, 0), (1000, 90), (2000, 0))
               for index in scripted}
    playback, engine = _make_playback(tmp_path, entries=entries, funscripts=scripts, tcode=tcode)
    if locked:
        playback.set_locked(True)
    return playback, engine, tcode


class TestTheOsr2:
    def test_sends_nothing_until_it_is_told_to_drive(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path)
        engine.position_ms = 1500

        playback.advance()

        assert tcode.updates == [] and tcode.parks == 0

    def test_told_to_drive_it_follows_its_clips_funscript_at_its_own_rate(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path)
        playback.set_speed(1.5)
        playback.set_tcode_enabled(True)
        engine.position_ms = 1500

        playback.advance()

        assert tcode.updates == [(1500, playback.current_funscript, 1.5)]

    def test_a_clip_with_no_funscript_rests_the_device(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path, scripted=())
        playback.set_tcode_enabled(True)

        playback.advance()

        assert tcode.updates == [] and tcode.parks == 1

    def test_told_to_stop_it_sends_nothing_more(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path)
        playback.set_tcode_enabled(True)
        playback.set_tcode_enabled(False)

        playback.advance()

        assert tcode.updates == []

    def test_a_paused_playback_drives_nothing(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path)
        playback.set_tcode_enabled(True)
        playback.set_paused(True)

        playback.advance()

        assert tcode.updates == []

    def test_taking_the_device_starts_from_wherever_it_is(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path)
        before = tcode.resets

        playback.set_tcode_enabled(True)

        assert tcode.resets == before + 1

    def test_every_jump_of_the_clock_starts_it_from_wherever_it_is(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path, entries=3)
        jumps = (lambda: playback.step(1), lambda: playback.seek_to(2500),
                 lambda: playback.set_speed(2.0))
        for jump in jumps:
            before = tcode.resets
            jump()
            assert tcode.resets == before + 1

    def test_a_clip_it_rolls_onto_by_itself_starts_it_from_wherever_it_is(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path)
        before = tcode.resets

        engine.simulate_eof_advance()
        playback.advance()

        assert tcode.resets == before + 1

    def test_a_locked_clip_coming_round_again_starts_it_from_wherever_it_is(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path, locked=True)
        playback.set_tcode_enabled(True)
        engine.position_ms = 4900
        playback.advance()
        before = tcode.resets

        engine.position_ms = 30
        playback.advance()

        assert tcode.resets == before + 1

    def test_resuming_starts_it_from_wherever_it_is(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path)
        playback.set_paused(True)
        before = tcode.resets

        playback.set_paused(False)

        assert tcode.resets == before + 1

    def test_resuming_holds_the_device_until_the_picture_moves(self, tmp_path):
        """Un-pausing is a request, not a picture: mpv takes frames to start
        presenting, and the device led the picture by that much on every reveal
        -- which is what he felt as the OSR2 starting before the video."""
        playback, engine, tcode = _driving(tmp_path)
        playback.set_tcode_enabled(True)
        playback.set_paused(True)
        playback.set_paused(False)

        playback.advance()
        assert tcode.updates == [] and tcode.parks == 0

        engine.position_ms = 40
        playback.advance()
        assert tcode.updates or tcode.parks

    def test_resuming_on_a_still_drives_the_device_at_once(self, tmp_path):
        """A still never moves: mpv reports its position as 0 for as long as
        it is shown, so it is on screen the moment it is unpaused."""
        playback, engine, tcode = _driving(tmp_path, scripted=())
        playback.set_tcode_enabled(True)
        engine.showing_picture = True
        playback.set_paused(True)
        playback.set_paused(False)

        playback.advance()

        assert tcode.parks == 1

    def test_a_picture_that_has_moved_once_is_not_asked_again(self, tmp_path):
        """The gate is the resume's own edge, not a per-tick liveness check: a
        video legitimately still between frames must not stop the device."""
        playback, engine, tcode = _driving(tmp_path)
        playback.set_tcode_enabled(True)
        playback.set_paused(True)
        playback.set_paused(False)
        engine.position_ms = 40
        playback.advance()
        drove = len(tcode.updates) + tcode.parks

        playback.advance()  # the same position, one pass later

        assert len(tcode.updates) + tcode.parks > drove

    def test_it_says_whether_its_clip_is_scripted_and_resting_where_it_is(self, tmp_path):
        playback, engine, _tcode = _driving(tmp_path, scripted=(1,))

        assert (playback.has_funscript, playback.funscript_resting) == (False, False)
        playback.step(1)
        engine.position_ms = 1000
        assert playback.has_funscript is True
        assert playback.funscript_resting is playback.current_funscript.is_resting_at(1000)

    def test_closing_closes_its_line_to_the_device(self, tmp_path):
        playback, _engine, tcode = _driving(tmp_path)

        playback.close()

        assert tcode.closed is True


class TestALockedClipsScript:
    def test_comes_round_again_with_the_clip(self, tmp_path):
        playback, _engine, _tcode = _driving(tmp_path, locked=True)

        assert playback.funscript_as_played.position_at(6_000) == 90

    def test_comes_round_again_with_a_clip_a_pace_of_nought_holds(self, tmp_path):
        playback, _engine, _tcode = _driving(tmp_path)

        playback.set_pace(0)

        assert playback.funscript_as_played.position_at(6_000) == 90

    def test_drives_the_device_as_it_comes_round(self, tmp_path):
        playback, engine, tcode = _driving(tmp_path, locked=True)
        playback.set_tcode_enabled(True)
        engine.position_ms = 4_900

        playback.advance()

        assert tcode.updates[-1][1] is playback.funscript_as_played

    def test_keeps_a_gap_too_short_to_hand_over_before_it_comes_round(self, tmp_path):
        script = _script(tmp_path / "v0.funscript", (0, 0), (1000, 90), (2000, 0))
        playback, engine = _make_playback(tmp_path, duration_ms=10_000.0, funscripts={0: script})
        playback.set_locked(True)
        engine.position_ms = 8_000

        assert playback.current_funscript.is_resting_at(8_000) is True
        assert playback.funscript_resting is False


class TestPlayFile:
    def test_play_file_jumps_to_a_playlist_item(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)

        playback.play_file(tmp_path / "v2.mp4")

        assert playback.current_video == tmp_path / "v2.mp4"
        assert engine.opened[-1] == tmp_path / "v2.mp4"
        assert len(playback.playlist) == 3

    def test_play_file_inserts_a_newcomer_after_current_and_plays_it(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        newcomer = tmp_path / "brought_back.mp4"
        newcomer.write_text("fake")

        playback.play_file(newcomer)

        assert playback.current_video == newcomer
        assert [p.name for p in playback.playlist] == ["v0.mp4", "brought_back.mp4", "v1.mp4"]
        assert engine.opened[-1] == newcomer


class TestPlayNext:
    def test_a_newcomer_comes_up_after_the_item_on_screen(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)
        newcomer = tmp_path / "newcomer.mp4"

        playback.play_next(newcomer)

        assert playback.current_video == tmp_path / "v0.mp4"
        assert engine.opened == [tmp_path / "v0.mp4"]
        assert engine.staged_next == newcomer
        assert [p.name for p in playback.playlist] == ["v0.mp4", "newcomer.mp4", "v1.mp4", "v2.mp4"]

    def test_an_item_further_down_the_list_moves_up_rather_than_coming_twice(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=4)

        playback.play_next(tmp_path / "v3.mp4")

        assert [p.name for p in playback.playlist] == ["v0.mp4", "v3.mp4", "v1.mp4", "v2.mp4"]
        assert engine.staged_next == tmp_path / "v3.mp4"

    def test_an_item_already_played_comes_round_again_after_the_one_on_screen(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=4)
        playback.step(2)

        playback.play_next(tmp_path / "v0.mp4")

        assert playback.current_video == tmp_path / "v2.mp4"
        assert [p.name for p in playback.playlist] == ["v1.mp4", "v2.mp4", "v0.mp4", "v3.mp4"]
        assert engine.staged_next == tmp_path / "v0.mp4"

    def test_the_item_on_screen_stays_where_it_is(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)
        playback.step(1)

        playback.play_next(tmp_path / "v1.mp4")

        assert playback.current_video == tmp_path / "v1.mp4"
        assert [p.name for p in playback.playlist] == ["v0.mp4", "v1.mp4", "v2.mp4"]
        assert engine.staged_next == tmp_path / "v2.mp4"

    def test_the_list_rolls_onto_it_with_its_script(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        newcomer, script = tmp_path / "newcomer.mp4", tmp_path / "newcomer.funscript"

        playback.play_next(newcomer, script)
        engine.simulate_eof_advance()
        playback.advance()

        assert playback.current_video == newcomer
        assert playback.funscript_of(newcomer) == script

    def test_a_held_item_keeps_it_waiting_until_the_hold_is_let_go(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, locked=True)
        newcomer = tmp_path / "newcomer.mp4"

        playback.play_next(newcomer)
        staged_while_held = engine.staged_next
        playback.set_locked(False)

        assert staged_while_held is None
        assert engine.staged_next == newcomer


class TestPlaylistReplacement:
    def test_replace_playlist_keeps_the_current_clip_when_it_survives(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)
        playback.step(1)
        opened_before = list(engine.opened)
        x = tmp_path / "x.mp4"
        x.write_text("fake")
        y = tmp_path / "y.mp4"
        y.write_text("fake")

        playback.replace_playlist([x, tmp_path / "v1.mp4", y])

        assert playback.current_video == tmp_path / "v1.mp4"
        assert engine.opened == opened_before
        assert engine.staged_next == y

    def test_replace_playlist_restarts_when_the_current_clip_is_gone(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=3)
        playback.step(1)
        x = tmp_path / "x.mp4"
        x.write_text("fake")
        y = tmp_path / "y.mp4"
        y.write_text("fake")

        playback.replace_playlist([x, y])

        assert playback.current_video == x
        assert engine.opened[-1] == x


class TestPlaybackClock:
    def test_position_and_duration_delegate_to_the_engine(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=8_000.0)
        engine.position_ms = 3_200.0

        assert playback.position_ms == 3_200.0
        assert playback.duration_ms == 8_000.0


class TestSpeed:
    def test_opens_at_normal_speed(self, tmp_path):
        playback, _engine = _make_playback(tmp_path)

        assert playback.speed == 1.0

    def test_a_rate_set_on_it_reaches_its_engine(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        playback.set_speed(1.5)

        assert playback.speed == engine.speed == 1.5

    def test_a_rate_past_either_end_is_held_at_that_end(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        playback.set_speed(9.0)
        assert playback.speed == engine.speed == MAX_RATE

        playback.set_speed(0.01)
        assert playback.speed == engine.speed == MIN_RATE


class TestClose:
    def test_close_tears_down_the_engine(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        playback.close()

        assert engine.closed is True


def _watch_to(playback, engine, position_ms):
    """Two ticks at *position_ms*: the jump onto it, then playing on from it."""
    engine.position_ms = position_ms
    playback.advance()
    playback.advance()


class TestWhereAClipWasLeft:
    def test_a_clip_left_in_the_middle_opens_there_again(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        _watch_to(playback, engine, 2_000)

        playback.step(1)
        playback.step(-1)
        playback.advance()

        assert engine.seeks[-1] == 2_000

    def test_a_spot_mpv_will_not_take_yet_is_asked_for_again(self, tmp_path):
        """mpv refuses a seek until the clip it is opening plays, which a known
        duration does not prove -- and the refusal used to end the engine."""
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        _watch_to(playback, engine, 2_000)
        playback.step(1)
        playback.step(-1)
        engine.refuse_seeks(1)

        playback.advance()
        playback.advance()

        assert engine.seeks[-1] == 2_000

    def test_a_spot_mpv_never_takes_is_let_go_of(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        _watch_to(playback, engine, 2_000)
        playback.step(1)
        playback.step(-1)
        engine.refuse_seeks(10 * GIVE_UP_AFTER)

        for _ in range(2 * GIVE_UP_AFTER):
            playback.advance()

        assert engine.refused == GIVE_UP_AFTER

    def test_leaving_a_clip_writes_down_the_very_spot(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        _watch_to(playback, engine, 2_000)
        engine.position_ms = 2_048
        playback.advance()

        playback.step(1)

        assert PlayPoints(file).point_for(tmp_path / "v0.mp4") == 2_048

    def test_a_clip_that_played_itself_out_is_not_remembered_at_its_end(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        _watch_to(playback, engine, 4_960)

        engine.simulate_eof_advance()
        playback.advance()

        assert PlayPoints(file).point_for(tmp_path / "v0.mp4") == 0

    def test_a_clip_rolled_onto_is_opened_where_it_was_left(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, entries=2, play_points=PlayPoints(file))
        playback.step(1)
        _watch_to(playback, engine, 2_000)
        playback.step(-1)

        engine.simulate_eof_advance()
        playback.advance()
        playback.advance()

        assert engine.seeks[-1] == 2_000

    def test_closing_the_engine_writes_down_the_very_spot(self, tmp_path):
        file = tmp_path / "points.json"
        playback, engine = _make_playback(tmp_path, play_points=PlayPoints(file))
        _watch_to(playback, engine, 2_000)
        engine.position_ms = 2_048
        playback.advance()

        playback.close()

        assert PlayPoints(file).point_for(tmp_path / "v0.mp4") == 2_048


class TestAFrameInThePicturesPlace:
    def test_a_frame_goes_up_on_the_engine_in_place_of_the_picture(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.show_frame(tmp_path / "frame one.png")

        assert engine.swapped == [tmp_path / "frame one.png"]

    def test_clearing_the_frame_puts_the_picture_itself_back(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame one.png")

        playback.clear_frame()

        assert engine.swapped == [tmp_path / "frame one.png", tmp_path / "v0.mp4"]

    def test_clearing_with_no_frame_up_leaves_the_picture_alone(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        playback.clear_frame()

        assert engine.swapped == []

    def test_a_frame_is_over_once_the_engine_is_stepped_to_another_item(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame.png")

        playback.step(1)
        playback.clear_frame()

        assert engine.swapped == [tmp_path / "frame.png"]

    def test_a_frame_is_over_once_the_picture_has_run_out_onto_the_next(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame.png")

        engine.simulate_eof_advance()
        playback.advance()
        playback.clear_frame()

        assert engine.swapped == [tmp_path / "frame.png"]

    def test_a_frame_going_up_is_a_picture_while_the_engine_opens_it(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        engine.showing_picture = True

        playback.show_frame(tmp_path / "frame.png")
        engine.showing_picture = False

        assert playback.showing_picture is True

    def test_the_picture_put_back_from_under_a_frame_is_a_picture_while_the_engine_opens_it(
            self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame.png")

        playback.clear_frame()
        engine.showing_picture = False

        assert playback.showing_picture is True

    def test_a_clip_the_picture_runs_out_onto_after_a_frame_is_what_the_engine_says(
            self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame.png")

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.showing_picture is False

    def test_a_clip_stepped_to_after_a_frame_is_what_the_engine_says(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        playback.show_frame(tmp_path / "frame.png")

        playback.step(1)

        assert playback.showing_picture is False

    def test_a_reloaded_list_naming_the_picture_put_up_keeps_it_on_its_move(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        finished = tmp_path / "v0 finished.png"
        playback.show_frame(finished)
        opened_before = list(engine.opened)

        playback.replace_playlist([finished, tmp_path / "v1.mp4"])

        assert playback.current_video == finished
        assert engine.opened == opened_before


class TestOpeningLocked:
    """The Main Funestra opens holding its item, as it always has; a satellite
    opens letting the list move on."""

    def test_a_playback_opened_locked_holds_its_item_from_the_first_frame(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, locked=True)

        assert playback.is_locked is True
        assert engine.loop_file is True
        assert engine.staged_next is None

    def test_a_playback_opened_unlocked_stages_the_next_item(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)

        assert playback.is_locked is False
        assert engine.staged_next == tmp_path / "v1.mp4"


class TestWhereInTheListItIs:
    def test_the_index_follows_the_item_on_screen(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=3)

        assert playback.index == 0
        playback.step(2)
        assert playback.index == 2

    def test_a_version_step_is_said_until_the_next_item_opens(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        clip = playback.current_video
        other = tmp_path / "v0_sorted.mp4"
        other.write_text("fake")

        assert playback.switching_versions is False
        playback.step_version([clip, other], 1)
        assert playback.switching_versions is True
        playback.step(1)
        assert playback.switching_versions is False


class TestShape:
    def test_an_item_taller_than_it_is_wide_is_portrait(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        engine.source_dims = (1080, 1920)

        assert playback.portrait is True

    def test_an_item_wider_than_it_is_tall_is_not(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        engine.source_dims = (1920, 1080)

        assert playback.portrait is False

    def test_a_square_item_is_landscape_as_the_family_files_one(self, tmp_path):
        playback, engine = _make_playback(tmp_path)

        engine.source_dims = (1080, 1080)

        assert playback.portrait is False

    def test_an_item_not_measured_yet_has_no_shape(self, tmp_path):
        playback, _engine = _make_playback(tmp_path)

        assert playback.portrait is None


class TestTheScriptNamedForEachItem:
    def test_it_says_which_file_scripts_an_item_in_the_list(self, tmp_path):
        script = _script(tmp_path / "v1.funscript", (0, 0), (400, 90))
        playback, _engine = _make_playback(tmp_path, entries=2, funscripts={1: script})

        assert playback.funscript_of(tmp_path / "v0.mp4") is None
        assert playback.funscript_of(tmp_path / "v1.mp4") == script


class TestASeekOverAFileOpen:
    """mpv opens a file asynchronously and reports no duration for a tick or two,
    and refuses a seek until the file plays.  A seek asked for in that window is
    owed rather than dropped or clamped against a zero-length item."""

    def test_a_seek_before_the_duration_is_known_waits(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=0.0)

        playback.seek_to(60_000)

        assert engine.seeks == []

    def test_it_lands_on_the_first_pass_the_duration_is_known(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=0.0)
        playback.seek_to(60_000)
        playback.advance()
        assert engine.seeks == []

        engine.duration_ms = 90_000.0
        playback.advance()

        assert engine.seeks == [60_000]

    def test_it_lands_even_while_paused(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=0.0, start_paused=True)
        playback.seek_to(60_000)
        engine.duration_ms = 90_000.0

        playback.advance()

        assert engine.seeks == [60_000]

    def test_it_lands_only_once(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=0.0)
        playback.seek_to(60_000)
        engine.duration_ms = 90_000.0

        playback.advance()
        playback.advance()

        assert engine.seeks == [60_000]

    def test_a_seek_mpv_refused_is_asked_for_again(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=90_000.0)
        engine.refuse_seeks(1)

        playback.seek_to(2_000)
        playback.advance()

        assert engine.seeks == [2_000]

    def test_navigating_away_drops_a_seek_the_old_item_never_took(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, duration_ms=0.0)
        playback.seek_to(60_000)

        playback.step(1)
        engine.duration_ms = 90_000.0
        playback.advance()

        assert engine.seeks == []


class TestAStretchBeingMarked:
    """A mark is where a stretch of the item starts to be marked out; nothing may
    rewind the playhead before it until the mark is closed or dropped."""

    def test_a_mark_is_a_floor_under_every_seek(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=60_000.0)
        engine.position_ms = 5_000.0

        playback.set_mark(5_000)
        playback.seek_by(-3_000)
        playback.seek_to(1_000)

        assert engine.seeks == [5_000.0, 5_000.0]
        assert playback.mark == 5_000

    def test_dropping_the_mark_lifts_the_floor(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=60_000.0)
        playback.set_mark(5_000)

        playback.set_mark(None)
        playback.seek_to(1_000)

        assert engine.seeks == [1_000.0]
        assert playback.mark is None

    def test_opening_another_item_drops_the_mark(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        playback.set_mark(5_000)

        playback.step(1)

        assert playback.mark is None


class TestAStretchRepeated:
    """An A/B range mpv goes round: the script of the item comes round with it,
    and the range belongs to the item, so opening another item ends it."""

    def test_the_range_reaches_the_engine_and_closes_the_mark(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=60_000.0)
        playback.set_mark(2_000)

        playback.set_ab_loop(2_000, 4_000)

        assert engine.ab_loop == (2_000, 4_000)
        assert (playback.ab_loop, playback.mark) == ((2_000, 4_000), None)

    def test_clearing_it_clears_the_engines_range(self, tmp_path):
        playback, engine = _make_playback(tmp_path, duration_ms=60_000.0)
        playback.set_ab_loop(2_000, 4_000)

        playback.clear_ab_loop()

        assert (engine.ab_loop, playback.ab_loop) == (None, None)

    def test_a_running_range_plays_its_stretch_of_the_script_again_and_again(self, tmp_path):
        script = _script(tmp_path / "v0.funscript", (0, 100), (1_000, 0), (2_000, 100),
                         (3_000, 0), (4_000, 100))
        playback, _engine = _make_playback(tmp_path, duration_ms=60_000.0, funscripts={0: script})

        playback.set_ab_loop(2_000, 4_000)

        assert playback.funscript_as_played.position_at(5_000) == 0

    def test_opening_another_item_clears_a_range_the_last_one_left(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2, duration_ms=60_000.0)
        playback.set_ab_loop(2_000, 4_000)

        playback.step(1)

        assert (engine.ab_loop, playback.ab_loop) == (None, None)

    def test_the_device_can_be_taken_over_by_whoever_moves_the_clock(self, tmp_path):
        tcode = FakeTCode()
        playback, _engine = _make_playback(tmp_path, tcode=tcode)
        before = tcode.resets

        playback.take_the_device_over()

        assert tcode.resets == before + 1


class TestCountingTheItemsOpened:
    """How many times an item has been opened on the engine, so whatever runs on
    a Funestra can tell a reopened item from the one it was already looking at."""

    def test_every_open_counts_including_the_same_item_again(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        opened = playback.loads

        playback.step(1)
        playback.play_file(playback.current_video)

        assert playback.loads == opened + 2

    def test_an_item_rolled_onto_counts_as_opened(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        opened = playback.loads

        engine.simulate_eof_advance()
        playback.advance()

        assert playback.loads == opened + 1


class TestTakingUpAListFromItsTop:
    def test_it_plays_the_new_lists_first_item(self, tmp_path):
        playback, engine = _make_playback(tmp_path, entries=2)
        a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
        for path in (a, b):
            path.write_text("fake")

        playback.load_playlist([a, b])

        assert (playback.index, playback.current_video) == (0, a)
        assert engine.opened[-1] == a
        assert playback.playlist == [a, b]

    def test_it_brings_the_lists_scripts(self, tmp_path):
        playback, _engine = _make_playback(tmp_path, entries=2)
        a = tmp_path / "a.mp4"
        a.write_text("fake")
        script = _script(tmp_path / "a.funscript", (0, 0), (100, 99))

        playback.load_playlist([a], {a: script})

        assert playback.current_funscript.actions == [(0, 0), (100, 99)]


def test_letting_go_of_the_item_leaves_the_engine_holding_nothing(tmp_path):
    """A host about to move or delete what it was showing lets go first: the
    engine holds an open handle on it, and Windows refuses to move a file out
    from under one."""
    playback, engine = _make_playback(tmp_path, entries=2)

    playback.let_go()

    assert engine.stopped is True
    assert playback.idle is True


def test_an_item_the_engine_would_not_open_reads_as_idle(tmp_path):
    playback, engine = _make_playback(tmp_path, entries=2)
    assert playback.idle is False

    engine.idle = True

    assert playback.idle is True

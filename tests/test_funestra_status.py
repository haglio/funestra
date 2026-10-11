from __future__ import annotations

from funestra_fakes import make_playback

from funestra.funestra_status import status_fields
from funestra.status import FunestraStatus, parse_status


class TestStatusFields:
    def test_publishes_every_key_the_dispatch_loop_reads(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        engine.position_ms = 1_500.0
        playback.set_locked(True)

        fields = status_fields(playback, None)

        assert fields["video"] == str(tmp_path / "v0.mp4")
        assert fields["position_ms"] == "1500"
        assert fields["duration_ms"] == "5000"
        assert fields["paused"] == "0"
        assert fields["locked"] == "1"

    def test_a_funestra_showing_a_picture_says_so(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        engine.showing_picture = True

        assert status_fields(playback, None)["picture"] == "1"

    def test_publishes_how_many_clips_a_discard_left_in_the_playlist(self, tmp_path):
        playback, _engine = make_playback(tmp_path, entries=2)

        playback.discard()

        assert status_fields(playback, None)["playlist_length"] == "1"

    def test_a_version_stepped_to_is_published_as_the_clip_it_stands_in_for(self, tmp_path):
        """The map, the star and the trash are all keyed on the clip, so the
        file a version step put up is never what the status names."""
        playback, _engine = make_playback(tmp_path)
        other = tmp_path / "v0_sorted.mp4"
        other.write_text("fake")
        playback.step_version([playback.current_video, other], 1)

        assert status_fields(playback, None)["video"] == str(tmp_path / "v0.mp4")

    def test_key_order_is_the_published_file_order(self):
        class Stub:
            current_video = "v0.mp4"
            position_ms = 0.0
            duration_ms = 0.0
            is_paused = False
            is_locked = False
            showing_picture = False
            playlist_length = 1
            speed = 1.0
            has_funscript = False
            funscript_resting = False
            portrait = None

        assert list(status_fields(Stub(), None)) == [
            "video", "position_ms", "duration_ms", "paused", "locked",
            "speed", "picture", "read_at", "playlist_length",
            "has_funscript", "funscript_resting", "handoff_touch_ms", "portrait",
        ]

    def test_the_shape_of_the_item_is_published_once_the_funestra_has_measured_it(self, tmp_path):
        playback, engine = make_playback(tmp_path)

        assert status_fields(playback, None)["portrait"] == ""
        engine.source_dims = (1080, 1920)
        assert status_fields(playback, None)["portrait"] == "1"
        engine.source_dims = (1920, 1080)
        assert status_fields(playback, None)["portrait"] == "0"

    def test_publishes_its_clips_script_and_where_its_trace_hands_the_device_over(self, tmp_path):
        script = tmp_path / "v0.funscript"
        script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 500, "pos": 90}]}',
                          encoding="utf-8")
        playback, _engine = make_playback(tmp_path, funscripts={0: script})

        fields = status_fields(playback, 1_234)

        assert fields["has_funscript"] == "1"
        assert fields["funscript_resting"] == ("1" if playback.funscript_resting else "0")
        assert fields["handoff_touch_ms"] == "1234"
        assert status_fields(playback, None)["handoff_touch_ms"] == ""

    def test_the_rate_it_plays_at_is_published(self, tmp_path):
        playback, _engine = make_playback(tmp_path)
        playback.set_speed(1.5)

        assert status_fields(playback, None)["speed"] == "1.5"

    def test_the_seven_every_funestra_leads_with_read_back_as_the_familys_record(self, tmp_path):
        playback, engine = make_playback(tmp_path)
        engine.position_ms = 1_500.0

        assert parse_status(status_fields(playback, None)) == FunestraStatus(
            video=str(tmp_path / "v0.mp4"), position_ms=1500, duration_ms=5000)

    def test_flags_follow_the_playback(self, tmp_path):
        playback, _engine = make_playback(tmp_path)
        playback.set_paused(True)

        fields = status_fields(playback, None)

        assert fields["paused"] == "1"
        assert fields["locked"] == "0"

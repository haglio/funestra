"""A Funestra's own volume chip: what it opens showing, and what the two verbs set.

Where on the chip a press landed is the row's to work out
(:class:`funestra.hud_row.RowPress`, covered in tests/test_hud_row.py); what
reaches a control is the mute or the level it asks for.
"""
from __future__ import annotations

from funestra.testing import FakeEngine
from funestra.volume import VolumeHud
from funestra.volume_control import RoomVolume, VolumeControl


def _volume(*, live: bool = True):
    engine = FakeEngine()
    return VolumeControl(engine, live=live), engine


class TestWhatItOpensAt:
    def test_a_live_chip_opens_muted_at_full(self):
        volume, _engine = _volume()

        assert volume.hud.muted is True
        assert volume.hud.volume == 100

    def test_a_silent_chip_opens_empty(self):
        volume, _engine = _volume(live=False)

        assert volume.hud.muted is True
        assert volume.hud.volume == 0


class TestWhatTheTwoVerbsSet:
    def test_the_mute_unmutes_the_engine_and_mutes_it_again(self):
        volume, engine = _volume()

        volume.toggle_mute()
        assert volume.hud.muted is False
        assert engine.muted is False

        volume.toggle_mute()
        assert volume.hud.muted is True
        assert engine.muted is True

    def test_a_level_is_set_on_the_engine_and_lifts_the_mute(self):
        volume, engine = _volume()

        volume.set_level(50)

        assert volume.hud == VolumeHud(volume=50, muted=False)
        assert (engine.volume, engine.muted) == (50, False)

    def test_a_silent_chip_acts_on_neither(self):
        volume, engine = _volume(live=False)

        volume.toggle_mute()
        volume.set_level(50)

        assert volume.hud.muted is True
        assert engine.muted is True

    def test_a_silent_chip_takes_no_level_it_is_handed_either(self):
        volume, engine = _volume(live=False)

        volume.set(60, False)

        assert (volume.hud.muted, engine.muted) == (True, True)

    def test_a_level_it_is_handed_is_held_within_the_chips_range(self):
        volume, engine = _volume()

        volume.set(140, False)

        assert (volume.hud.volume, engine.volume) == (100, 100)


class TestTheRoomsVolume:
    """The Main Funestra's sound is the room's to decide: the chip shows the level
    the room publishes, a press asks the room for a new one and shows it at once,
    and the room's answer overwrites it either way."""

    def _control(self, tmp_path, *, live: bool = True):
        engine = FakeEngine()
        return RoomVolume(engine, dashboard_cmd_file=tmp_path / "dashboard_cmd.txt", live=live), engine

    def _asks(self, tmp_path) -> list[str]:
        path = tmp_path / "dashboard_cmd.txt"
        return path.read_text(encoding="utf-8").split() if path.exists() else []

    def test_it_starts_at_full_and_unmuted_until_the_room_says_otherwise(self, tmp_path):
        control, _engine = self._control(tmp_path)

        assert (control.hud.volume, control.hud.muted) == (100, False)

    def test_a_live_build_unmutes_its_engine_so_the_rooms_level_can_be_heard(self, tmp_path):
        _control, engine = self._control(tmp_path, live=True)

        assert engine.muted is False

    def test_a_silent_build_leaves_its_engine_muted(self, tmp_path):
        _control, engine = self._control(tmp_path, live=False)

        assert engine.muted is True

    def test_the_rooms_answer_is_what_the_chip_shows_and_what_the_engine_plays(self, tmp_path):
        control, engine = self._control(tmp_path)

        control.set(40, muted=False)

        assert (control.hud.volume, control.hud.muted) == (40, False)
        assert engine.volume == 40

    def test_a_mute_from_the_room_plays_silent_but_keeps_the_level_drawn(self, tmp_path):
        control, engine = self._control(tmp_path)

        control.set(70, muted=True)

        assert (control.hud.volume, control.hud.muted) == (70, True)
        assert engine.volume == 0

    def test_a_level_from_the_room_is_held_within_the_chips_range(self, tmp_path):
        control, engine = self._control(tmp_path)

        control.set(400, muted=False)
        assert engine.volume == 100
        control.set(-10, muted=False)
        assert engine.volume == 0

    def test_the_mute_shows_at_once_and_asks_the_room_for_it(self, tmp_path):
        control, engine = self._control(tmp_path)

        control.toggle_mute()

        assert control.hud.muted is True
        assert self._asks(tmp_path) == ["audio_mute"]
        assert engine.volume == 100, "the room answers; the chip does not set the engine itself"

    def test_muting_again_asks_for_the_unmute(self, tmp_path):
        control, _engine = self._control(tmp_path)
        control.toggle_mute()

        control.toggle_mute()

        assert control.hud.muted is False
        assert self._asks(tmp_path) == ["audio_mute", "audio_unmute"]

    def test_the_level_underneath_a_mute_is_left_where_it_was(self, tmp_path):
        control, _engine = self._control(tmp_path)
        control.set(40, muted=False)

        control.toggle_mute()

        assert (control.hud.volume, control.hud.muted) == (40, True)

    def test_a_level_is_asked_of_the_room_and_shown_at_once(self, tmp_path):
        control, _engine = self._control(tmp_path)

        control.set_level(50)

        assert control.hud.volume == 50
        assert self._asks(tmp_path) == ["audio_set_volume|50"]

    def test_asking_for_a_level_is_asking_to_hear_it(self, tmp_path):
        control, _engine = self._control(tmp_path)
        control.toggle_mute()

        control.set_level(50)

        assert control.hud.muted is False

    def test_a_level_asked_for_over_and_over_keeps_asking(self, tmp_path):
        control, _engine = self._control(tmp_path)

        control.set_level(0)
        control.set_level(50)

        assert control.hud.volume == 50
        assert self._asks(tmp_path) == ["audio_set_volume|0", "audio_set_volume|50"]

    def test_an_ignored_ask_corrects_itself_when_the_room_answers(self, tmp_path):
        control, _engine = self._control(tmp_path)
        control.toggle_mute()

        control.set(60, muted=False)

        assert control.hud.muted is False

    def test_with_no_room_to_ask_the_level_is_still_shown(self, tmp_path):
        engine = FakeEngine()
        control = RoomVolume(engine, dashboard_cmd_file=None, live=True)

        control.set_level(50)

        assert control.hud.volume == 50

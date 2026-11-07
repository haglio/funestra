from __future__ import annotations

from typing import ClassVar

import numpy as np
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY

from funestra import volume
from funestra.scrubber_bar import SCRUBBER_HEIGHT
from funestra.volume import (
    PAD,
    PLACE_W,
    ROW_H,
    SPEAKER_W,
    TRACK_GAP,
    VOLUME_CONTROL_H,
    VOLUME_CONTROL_W,
    VolumeHud,
    VolumeHudPainter,
    hit_part,
    volume_at,
    volume_control_local,
    volume_control_xy,
)


class TestPlacement:
    def test_the_volume_control_sits_in_the_timeline_row_at_its_right_end(self):
        tl = 40
        x, y = volume_control_xy(viewport_w=1200, viewport_h=900, timeline_h=tl)

        assert x + VOLUME_CONTROL_W == 1200
        assert 900 - tl <= y
        assert y + VOLUME_CONTROL_H <= 900

    def test_the_slot_it_reserves_covers_the_volume_control_and_its_margins(self):
        assert PLACE_W == VOLUME_CONTROL_W + TRACK_GAP

    def test_it_is_as_narrow_as_a_mute_and_a_slider_need(self):
        assert VOLUME_CONTROL_W <= 64
        assert VOLUME_CONTROL_W - SPEAKER_W - PAD >= 32

    def test_a_window_narrower_than_the_volume_control_still_places_it(self):
        x, _y = volume_control_xy(viewport_w=80, viewport_h=200, timeline_h=40)

        assert x >= 0

    def test_a_funestra_with_no_scrubber_puts_the_volume_control_where_one_with_a_scrubber_does(self):
        assert volume_control_xy(viewport_w=1200, viewport_h=900, timeline_h=0) == volume_control_xy(
            viewport_w=1200, viewport_h=900, timeline_h=ROW_H)

    def test_the_row_it_falls_back_to_is_the_one_the_scrubber_draws_restated_here_since_the_scrubber_imports_this_module(self):
        assert ROW_H == SCRUBBER_HEIGHT

    def test_a_window_shorter_than_the_volume_control_still_places_it(self):
        _x, y = volume_control_xy(viewport_w=1200, viewport_h=10, timeline_h=0)

        assert y >= 0


class TestWindowPoints:
    GEOMETRY: ClassVar[dict[str, int]] = {"viewport_w": 1200, "viewport_h": 900, "timeline_h": 40}

    def test_the_chips_own_corner_reads_as_its_origin_undone_beside_the_placement(self):
        assert volume_control_local(*volume_control_xy(**self.GEOMETRY), **self.GEOMETRY) == (0, 0)

    def test_a_window_point_over_the_speaker_lands_on_the_mute(self):
        vx, vy = volume_control_xy(**self.GEOMETRY)

        local = volume_control_local(vx + 2, vy + VOLUME_CONTROL_H // 2, **self.GEOMETRY)

        assert hit_part(*local) == "mute"

    def test_a_window_point_over_the_slider_lands_on_the_track(self):
        vx, vy = volume_control_xy(**self.GEOMETRY)

        local = volume_control_local(vx + VOLUME_CONTROL_W - 4, vy + VOLUME_CONTROL_H // 2, **self.GEOMETRY)

        assert hit_part(*local) == "track"

    def test_a_window_point_away_from_the_volume_control_lands_on_nothing(self):
        assert hit_part(*volume_control_local(20, 20, **self.GEOMETRY)) == ""


class TestHitTesting:
    def test_the_speaker_takes_the_left_end_and_the_track_the_rest(self):
        assert hit_part(2, VOLUME_CONTROL_H // 2) == "mute"
        assert hit_part(VOLUME_CONTROL_W - 4, VOLUME_CONTROL_H // 2) == "track"

    def test_a_press_outside_the_volume_control_hits_nothing(self):
        assert hit_part(-1, VOLUME_CONTROL_H // 2) == ""
        assert hit_part(VOLUME_CONTROL_W + 1, VOLUME_CONTROL_H // 2) == ""
        assert hit_part(2, VOLUME_CONTROL_H + 5) == ""

    def test_the_track_reads_left_to_right_as_silent_to_full(self):
        assert volume_at(-999) == 0
        assert volume_at(999) == 100

    def test_the_track_is_linear_between_its_ends(self):
        step = (VOLUME_CONTROL_W - SPEAKER_W) // 4
        low, mid, high = (volume_at(SPEAKER_W + n * step) for n in (0, 1, 2))

        assert low < mid < high
        assert abs((mid - low) - (high - mid)) <= 1


class TestPainter:
    def _volume_control(self, **kw) -> np.ndarray:
        return VolumeHudPainter().bgra(VolumeHud(**kw))

    def test_the_filled_part_of_the_track_grows_with_the_level_counted_above_the_mid_gray_of_the_track_and_its_border(self):
        def filled(volume: int) -> int:
            volume_control = self._volume_control(volume=volume)
            return int((volume_control[:, SPEAKER_W:, :3].sum(axis=2) > 600).sum())

        assert filled(20) < filled(60) < filled(100)

    def test_a_muted_control_still_shows_the_level_underneath_it(self):
        loud = self._volume_control(volume=80, muted=False)
        silenced = self._volume_control(volume=80, muted=True)

        assert not np.array_equal(loud, silenced), "a mute has to look different"
        track = slice(SPEAKER_W, VOLUME_CONTROL_W)
        assert np.array_equal(loud[:, track], silenced[:, track]), "the level is unchanged"

    def test_the_speaker_is_the_familys_and_crossed_out_while_muted(self, monkeypatch):
        drawn = []
        real = volume.paste_icon

        def spy(image, name, frame, color):
            drawn.append((name, color))
            real(image, name, frame, color)

        monkeypatch.setattr(volume, "paste_icon", spy)
        self._volume_control(muted=False)
        self._volume_control(muted=True)

        assert drawn == [("speaker", TEXT_PRIMARY), ("speaker_off", TEXT_MUTED)]

    def test_an_unchanged_control_is_not_repainted(self):
        painter = VolumeHudPainter()

        assert painter.bgra(VolumeHud(volume=50)) is painter.bgra(VolumeHud(volume=50))

    def test_a_changed_level_is_repainted_changed_by_several_steps_since_neighboring_levels_share_a_pixel_on_a_slider_this_narrow(self):
        painter = VolumeHudPainter()

        assert not np.array_equal(
            painter.bgra(VolumeHud(volume=50)), painter.bgra(VolumeHud(volume=55)))

    def test_the_pygame_shape_is_the_same_volume_control_the_mpv_one_is(self):
        painter = VolumeHudPainter()
        hud = VolumeHud(volume=40, muted=True)

        rgba, size = painter.rgba(hud)
        bgra = painter.bgra(hud)

        assert size == (VOLUME_CONTROL_W, VOLUME_CONTROL_H)
        assert len(rgba) == VOLUME_CONTROL_W * VOLUME_CONTROL_H * 4
        from_rgba = np.frombuffer(rgba, dtype=np.uint8).reshape(VOLUME_CONTROL_H, VOLUME_CONTROL_W, 4)
        assert np.array_equal(from_rgba[:, :, [2, 1, 0, 3]], bgra)

    def test_an_unchanged_control_is_not_repainted_for_pygame_either(self):
        painter = VolumeHudPainter()

        assert painter.rgba(VolumeHud(volume=50)) == painter.rgba(VolumeHud(volume=50))
        assert painter.rgba(VolumeHud(volume=50))[0] != painter.rgba(VolumeHud(volume=90))[0]

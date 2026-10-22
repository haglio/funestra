"""The shared volume chip: what it shows, and where a click on it lands."""
from __future__ import annotations

import numpy as np
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY

from funestra import volume
from funestra.timeline import TIMELINE_HEIGHT
from funestra.volume import (
    CHIP_H,
    CHIP_W,
    PAD,
    ROW_H,
    SLOT_W,
    SPEAKER_W,
    TRACK_GAP,
    VolumeHud,
    VolumeHudPainter,
    chip_local,
    chip_xy,
    hit_part,
    volume_at,
)


class TestPlacement:
    def test_the_chip_sits_in_the_timeline_row_at_its_right_end(self):
        """VLC put the volume beside the seek bar, not above it — so the chip drops
        into the timeline row, hard against the right, and the scrubber's track
        makes room for it (timeline.bar_track_x reserves SLOT_W there)."""
        tl = 40
        x, y = chip_xy(win_w=1200, win_h=900, timeline_h=tl)

        assert x + CHIP_W == 1200                    # flush with the right edge
        assert 900 - tl <= y and y + CHIP_H <= 900   # within the timeline row's band

    def test_the_slot_it_reserves_covers_the_chip_and_its_margins(self):
        """The scrubber subtracts SLOT_W to clear the chip, so the slot has to be
        at least the chip plus the gap it sits in — otherwise the track runs under
        it."""
        assert SLOT_W == CHIP_W + TRACK_GAP

    def test_it_is_as_narrow_as_a_mute_and_a_slider_need(self):
        """The row's track is what needs the room, so the chip takes little of
        it: a speaker to press, and a slider still wide enough to set the
        level by a few per pixel."""
        assert CHIP_W <= 64
        assert CHIP_W - SPEAKER_W - PAD >= 32

    def test_a_window_narrower_than_the_chip_still_places_it(self):
        """Clamped rather than pushed off the left edge, so it stays clickable."""
        x, _y = chip_xy(win_w=80, win_h=200, timeline_h=40)

        assert x >= 0

    def test_a_funestra_with_no_scrubber_puts_the_chip_where_one_with_a_scrubber_does(self):
        """Genau draws no timeline, but its window IS the primary display in genau
        mode — so reaching for the sound must not find the control somewhere other
        than where the same session shows it in kino mode, which is the row
        The Main Funestra draws.  Measuring its own margin off the lower edge instead put it
        nine pixels above that."""
        assert chip_xy(win_w=1200, win_h=900, timeline_h=0) == chip_xy(
            win_w=1200, win_h=900, timeline_h=ROW_H)

    def test_the_row_it_falls_back_to_is_the_one_the_scrubber_draws(self):
        """ROW_H is restated rather than imported — timeline reads SLOT_W from
        volume, so the dependency cannot run both ways — and a fallback row of a
        different height would leave the chip off-centre in the real one."""
        assert ROW_H == TIMELINE_HEIGHT

    def test_a_window_shorter_than_the_chip_still_places_it(self):
        """Clamped at the top for the reason the left edge is: still on screen,
        still clickable."""
        _x, y = chip_xy(win_w=1200, win_h=10, timeline_h=0)

        assert y >= 0


class TestWindowPoints:
    """Presses arrive in the window's coordinates; every hit test here takes the
    chip's.  The chip is placed from the window's lower-right corner, so its
    origin moves with the window and with the timeline beneath it — which is why
    undoing `chip_xy` belongs beside `chip_xy` and not at each call site."""

    GEOMETRY = {"win_w": 1200, "win_h": 900, "timeline_h": 40}

    def test_the_chips_own_corner_reads_as_its_origin(self):
        assert chip_local(*chip_xy(**self.GEOMETRY), **self.GEOMETRY) == (0, 0)

    def test_a_window_point_over_the_speaker_lands_on_the_mute(self):
        vx, vy = chip_xy(**self.GEOMETRY)

        local = chip_local(vx + 2, vy + CHIP_H // 2, **self.GEOMETRY)

        assert hit_part(*local) == "mute"

    def test_a_window_point_over_the_slider_lands_on_the_track(self):
        vx, vy = chip_xy(**self.GEOMETRY)

        local = chip_local(vx + CHIP_W - 4, vy + CHIP_H // 2, **self.GEOMETRY)

        assert hit_part(*local) == "track"

    def test_a_window_point_away_from_the_chip_lands_on_nothing(self):
        """A press on the video is not a press on the control floating over it."""
        assert hit_part(*chip_local(20, 20, **self.GEOMETRY)) == ""


class TestHitTesting:
    def test_the_speaker_takes_the_left_end_and_the_track_the_rest(self):
        assert hit_part(2, CHIP_H // 2) == "mute"
        assert hit_part(CHIP_W - 4, CHIP_H // 2) == "track"

    def test_a_press_outside_the_chip_hits_nothing(self):
        assert hit_part(-1, CHIP_H // 2) == ""
        assert hit_part(CHIP_W + 1, CHIP_H // 2) == ""
        assert hit_part(2, CHIP_H + 5) == ""

    def test_the_track_reads_left_to_right_as_silent_to_full(self):
        assert volume_at(-999) == 0
        assert volume_at(999) == 100

    def test_the_track_is_linear_between_its_ends(self):
        """Equal steps along the track are equal steps in level, so the handle
        lands where it was put rather than somewhere near it."""
        step = (CHIP_W - SPEAKER_W) // 4
        low, mid, high = (volume_at(SPEAKER_W + n * step) for n in (0, 1, 2))

        assert low < mid < high
        assert abs((mid - low) - (high - mid)) <= 1


class TestPainter:
    def _chip(self, **kw) -> np.ndarray:
        return VolumeHudPainter().bgra(VolumeHud(**kw))

    def test_the_filled_part_of_the_track_grows_with_the_level(self):
        # Only the fill is near-white; the empty track and the chip's border are
        # both mid-gray, so a high threshold counts the fill and nothing else.
        def filled(volume: int) -> int:
            chip = self._chip(volume=volume)
            return int((chip[:, SPEAKER_W:, :3].sum(axis=2) > 600).sum())

        assert filled(20) < filled(60) < filled(100)

    def test_a_muted_control_still_shows_the_level_underneath_it(self):
        """The level survives a mute — it is what unmuting returns to — so the
        track keeps its fill and the speaker alone says silent."""
        loud = self._chip(volume=80, muted=False)
        silenced = self._chip(volume=80, muted=True)

        assert not np.array_equal(loud, silenced), "a mute has to look different"
        track = slice(SPEAKER_W, CHIP_W)
        assert np.array_equal(loud[:, track], silenced[:, track]), "the level is unchanged"

    def test_the_speaker_is_the_familys_and_crossed_out_while_muted(self, monkeypatch):
        drawn = []
        real = volume.paste_glyph

        def spy(image, name, frame, color):
            drawn.append((name, color))
            real(image, name, frame, color)

        monkeypatch.setattr(volume, "paste_glyph", spy)
        self._chip(muted=False)
        self._chip(muted=True)

        assert drawn == [("speaker", TEXT_PRIMARY), ("speaker_off", TEXT_MUTED)]

    def test_an_unchanged_control_is_not_repainted(self):
        """Asked for every frame at 60fps; Pillow is nowhere near that cheap."""
        painter = VolumeHudPainter()

        assert painter.bgra(VolumeHud(volume=50)) is painter.bgra(VolumeHud(volume=50))

    def test_a_changed_level_is_repainted(self):
        """A slider this narrow draws a few levels on one pixel, so the fill
        is seen to move over a handful of them."""
        painter = VolumeHudPainter()

        assert not np.array_equal(
            painter.bgra(VolumeHud(volume=50)), painter.bgra(VolumeHud(volume=55)))

    def test_the_pygame_shape_is_the_same_chip_the_mpv_one_is(self):
        """The Main Funestra composites an mpv overlay and Genau blits a pygame surface, so the
        chip is handed out in both shapes — off one painting, or the two Funestras
        would be free to show different chips."""
        painter = VolumeHudPainter()
        hud = VolumeHud(volume=40, muted=True)

        rgba, size = painter.rgba(hud)
        bgra = painter.bgra(hud)

        assert size == (CHIP_W, CHIP_H)
        assert len(rgba) == CHIP_W * CHIP_H * 4
        # Same pixels, in each renderer's channel order.
        from_rgba = np.frombuffer(rgba, dtype=np.uint8).reshape(CHIP_H, CHIP_W, 4)
        assert np.array_equal(from_rgba[:, :, [2, 1, 0, 3]], bgra)

    def test_an_unchanged_control_is_not_repainted_for_pygame_either(self):
        painter = VolumeHudPainter()

        assert painter.rgba(VolumeHud(volume=50)) == painter.rgba(VolumeHud(volume=50))
        assert painter.rgba(VolumeHud(volume=50))[0] != painter.rgba(VolumeHud(volume=90))[0]

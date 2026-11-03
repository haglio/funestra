from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from shared_ui.icons_pil import paste_icon
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY
from shared_ui.spacing import GAP_MEDIUM, GAP_SMALL

from funestra.hud import KeptBitmap, draw_track, pill

VOLUME_CONTROL_W = 64
VOLUME_CONTROL_H = 22
TRACK_GAP = GAP_MEDIUM
SPEAKER_W = 26
PAD = GAP_SMALL

MIN_VOLUME = 0
MAX_VOLUME = 100

PLACE_W = TRACK_GAP + VOLUME_CONTROL_W

ROW_H = 24


def volume_control_xy(*, viewport_w: int, viewport_h: int, timeline_h: int) -> tuple[int, int]:
    row_h = timeline_h if timeline_h > 0 else ROW_H
    return (
        max(0, viewport_w - VOLUME_CONTROL_W),
        max(0, viewport_h - row_h + max(0, (row_h - VOLUME_CONTROL_H) // 2)),
    )


_TRACK_X0 = SPEAKER_W
_TRACK_X1 = VOLUME_CONTROL_W - PAD


def volume_control_local(mx: int, my: int, *, viewport_w: int, viewport_h: int,
               timeline_h: int) -> tuple[int, int]:
    vx, vy = volume_control_xy(viewport_w=viewport_w, viewport_h=viewport_h, timeline_h=timeline_h)
    return mx - vx, my - vy


def hit_part(x: int, y: int) -> str:
    if not (0 <= x < VOLUME_CONTROL_W and 0 <= y < VOLUME_CONTROL_H):
        return ""
    return "mute" if x < SPEAKER_W else "track"


def volume_at(x: int) -> int:
    span = max(1, _TRACK_X1 - _TRACK_X0)
    fraction = (x - _TRACK_X0) / span
    return round(min(1.0, max(0.0, fraction)) * MAX_VOLUME)


@dataclass(frozen=True)
class VolumeHud:
    volume: int = MAX_VOLUME
    muted: bool = False


_SPEAKER_MARK = (PAD // 2, 1, VOLUME_CONTROL_H - 2, VOLUME_CONTROL_H - 2)


def _draw_speaker(image: Image.Image, muted: bool) -> None:
    paste_icon(image, "speaker_off" if muted else "speaker", _SPEAKER_MARK,
               TEXT_MUTED if muted else TEXT_PRIMARY)


class VolumeHudPainter(KeptBitmap):
    def _paint(self, hud: VolumeHud) -> Image.Image:
        image, draw = pill(VOLUME_CONTROL_W, VOLUME_CONTROL_H)
        _draw_speaker(image, hud.muted)
        level = min(MAX_VOLUME, max(MIN_VOLUME, hud.volume))
        filled = _TRACK_X0 + round((_TRACK_X1 - _TRACK_X0) * level / MAX_VOLUME)
        draw_track(draw, _TRACK_X0, _TRACK_X1, VOLUME_CONTROL_H // 2,
                   filled_to=filled if filled > _TRACK_X0 else None)
        return image

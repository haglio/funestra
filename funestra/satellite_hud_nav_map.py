from __future__ import annotations

from dataclasses import replace

from PIL import ImageDraw
from shared_ui.icons_pil import paste_icon
from shared_ui.palette import TEXT_PRIMARY

from .geometry import Rect
from .satellite_hud import HudModel, NavMapRects, NavMapWindow, ellipsis_rects, nav_map_window


def dashed_rect(draw: ImageDraw.ImageDraw, rect: Rect, color, dash: int = 4) -> None:
    # Pillow draws only solid lines.
    x, y, w, h = rect
    for start in range(x, x + w, dash * 2):
        end = min(start + dash, x + w)
        draw.line([(start, y), (end, y)], fill=color)
        draw.line([(start, y + h - 1), (end, y + h - 1)], fill=color)
    for start in range(y, y + h, dash * 2):
        end = min(start + dash, y + h)
        draw.line([(x, start), (x, end)], fill=color)
        draw.line([(x + w - 1, start), (x + w - 1, end)], fill=color)


def count_lines(model: HudModel) -> tuple[str, ...]:
    if not (model.seed_count or model.action_count):
        return ()
    return (f"Seeds: {model.seed_count}", f"Actions: {model.action_count}")


def narrowed_to_window(model: HudModel) -> tuple[HudModel, NavMapWindow | None, NavMapWindow | None]:
    if model.corner is None:
        return model, None, None
    bucket, index = model.playing
    seed_strip = [model.corner, *model.seeds]
    action_strip = [model.corner, *model.actions]
    seed_at = index + 1 if bucket == "seed" else 0
    action_at = index + 1 if bucket == "action" else 0
    seed_win = nav_map_window(len(seed_strip), seed_at)
    action_win = nav_map_window(len(action_strip), action_at)
    window = action_win if bucket == "action" else seed_win
    strip = action_strip if bucket == "action" else seed_strip
    corner = strip[window.start]
    lit = (action_at if bucket == "action" else seed_at) - window.start
    narrowed = replace(
        model,
        corner=corner,
        seeds=tuple(seed_strip[seed_win.start + 1:seed_win.start + seed_win.count]),
        actions=tuple(action_strip[action_win.start + 1:action_win.start + action_win.count]),
        playing=("corner", 0) if lit <= 0 else (bucket, lit - 1),
    )
    if bucket == "action":
        narrowed = replace(narrowed, current_action=corner.label or model.current_action)
    return narrowed, seed_win, action_win


def draw_ellipses(image, rects: NavMapRects, axis: str, window) -> None:
    before, after = ellipsis_rects(rects, axis)
    for rect, show in ((before, window.more_before), (after, window.more_after)):
        if not show:
            continue
        paste_icon(image, "more" if axis == "seed" else "more_vertical", rect,
                   TEXT_PRIMARY)

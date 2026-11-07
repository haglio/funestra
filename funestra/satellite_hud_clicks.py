from __future__ import annotations

from shared_ui.icon_geometry import tooltip_for

from .geometry import Rect, contains
from .osr2_visualizer import TrackGrip
from .satellite_hud import (
    EXPAND_ICON,
    FAVORITE_ICON,
    LOOP_ICON,
    WRONG_ACTION_ICON,
    HudTargets,
    button_under,
    hit_test_targets,
)
from .video_families import normalized_text

LOOP_TOOLTIPS = {"action": "Loop this action column", "seed": "Loop this seed row"}
FILTER_TOOLTIP = "Filter to this action"
EXPAND_TOOLTIP = "More seeds — widen the net"
FAVORITE_TOOLTIP = "In the favorites"
WRONG_ACTION_TOOLTIP = "Wrong action — strike it, and it gets asked about again"


def _in(rect: Rect | None, px: int, py: int) -> bool:
    return rect is not None and contains(rect, px, py)


def button_tooltip(targets: HudTargets, px: int, py: int) -> str:
    button = button_under(targets, px, py)
    if button is not None:
        return button.tooltip_on_hover
    loop = hit_test_targets(targets.loop, px, py)
    if loop:
        return tooltip_for(LOOP_ICON, LOOP_TOOLTIPS.get(loop, ""))
    beneath = (
        (_in(targets.wrong_action, px, py), tooltip_for(WRONG_ACTION_ICON, WRONG_ACTION_TOOLTIP)),
        (bool(hit_test_targets(targets.filter, px, py) or hit_test_targets(targets.words, px, py)),
         FILTER_TOOLTIP),
        (_in(targets.expand, px, py), tooltip_for(EXPAND_ICON, EXPAND_TOOLTIP)),
        (_in(targets.favorite, px, py), tooltip_for(FAVORITE_ICON, FAVORITE_TOOLTIP)),
    )
    return next((tooltip for hit, tooltip in beneath if hit), "")


# Windows' default double-click time.
DOUBLE_CLICK_S = 0.5


class HudClicks(TrackGrip):
    def __init__(self, funestra: str, *, double_click_s: float = DOUBLE_CLICK_S) -> None:
        super().__init__()
        self._funestra = funestra
        self._double_click_s = double_click_s
        self._pending_path = ""
        self._pending_at = 0.0
        self.active_loop = ""
        self.active_filter = ""

    def press(self, targets: HudTargets, px: int, py: int, *, now: float) -> str:
        self.release()
        for ask in (self._press_a_button, self._press_a_track, self._press_a_loop,
                    self._press_expand, self._press_wrong_action, self._press_a_filter):
            asked = ask(targets, px, py)
            if asked is not None:
                return asked
        path = hit_test_targets(targets.click, px, py)
        if not path:
            return ""
        if path == self._pending_path and now - self._pending_at <= self._double_click_s:
            self._pending_path = ""
            return f"{self._funestra}_lock_video|{path}"
        self._pending_path = path
        self._pending_at = now
        return ""

    @staticmethod
    def _press_a_button(targets: HudTargets, px: int, py: int) -> str | None:
        button = button_under(targets, px, py)
        if button is None or not button.command:
            return None
        return "" if button.dim else button.command

    def _press_a_track(self, targets: HudTargets, px: int, py: int) -> str | None:
        return self.grab(targets.tracks, px, py) or None

    def _press_a_loop(self, targets: HudTargets, px: int, py: int) -> str | None:
        loop = hit_test_targets(targets.loop, px, py)
        return self._toggle_loop(loop) if loop else None

    def _press_expand(self, targets: HudTargets, px: int, py: int) -> str | None:
        return f"{self._funestra}_more_seeds" if _in(targets.expand, px, py) else None

    def _press_wrong_action(self, targets: HudTargets, px: int, py: int) -> str | None:
        return f"{self._funestra}_wrong_action" if _in(targets.wrong_action, px, py) else None

    def _press_a_filter(self, targets: HudTargets, px: int, py: int) -> str | None:
        action = hit_test_targets(targets.filter, px, py) or hit_test_targets(targets.words, px, py)
        if not action:
            return None
        query = normalized_text(action)
        if query == normalized_text(self.active_filter):
            self.active_filter = ""
            return f"{self._funestra}_no_filter"
        self.active_filter = query
        return f"filter_{self._funestra}_{query.replace(' ', '_')}"

    def due(self, *, now: float) -> str:
        if not self._pending_path or now - self._pending_at <= self._double_click_s:
            return ""
        path, self._pending_path = self._pending_path, ""
        return f"{self._funestra}_play_video|{path}"

    def _toggle_loop(self, kind: str) -> str:
        if self.active_loop == kind:
            self.active_loop = ""
            return f"{self._funestra}_no_loop"
        self.active_loop = kind
        return f"{self._funestra}_{kind}_loop"

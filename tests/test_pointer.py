"""Where a press on a Funestra's window lands: the panel, or the item under it.

The track, the time and the volume are a block of the panel, which places a
press on them itself (test_hud_overlay.py), so nothing over the item takes
one any more.
"""
from __future__ import annotations

from funestra.pointer import Pointer

ON_THE_VIDEO = (300, 200)
LOWER_EDGE = (300, 476)


class _StubHud:
    """The lock HUD's half of the pointer's interface, and nothing else.

    *takes* is whether its slab is under the press — the real HUD answers that
    from the panel it last drew, which is a question about a bitmap's size.
    """

    def __init__(self, *, takes: bool = True) -> None:
        self._takes = takes
        self.presses: list[tuple[int, int]] = []
        self.motions: list[tuple[int, int]] = []
        self.drags: list[tuple[int, int]] = []
        self.wheels: list[tuple[int, int, int]] = []
        self.holding = False

    def press(self, x: int, y: int) -> bool:
        self.presses.append((x, y))
        return self._takes

    def wheel(self, x: int, y: int, steps: int) -> bool:
        self.wheels.append((x, y, steps))
        return self._takes

    def motion(self, x: int, y: int) -> None:
        self.motions.append((x, y))

    def drag_to(self, x: int, y: int) -> str:
        self.drags.append((x, y))
        return ""

    def release(self) -> None:
        self.holding = False


def _pointer(*, hud: bool = True, hud_takes: bool = True):
    stub = _StubHud(takes=hud_takes) if hud else None
    asked: list[str] = []
    return Pointer(hud=stub, item=lambda: asked.append("pause")), stub, asked


class TestTheItem:
    """A press the panel does not take is a press on the item, which asks
    whoever built the window -- the room, or the program running on it -- to
    pause."""

    def test_a_press_the_panel_refused_asks_for_the_pause(self):
        pointer, hud, asked = _pointer(hud_takes=False)

        pointer.press(*ON_THE_VIDEO)

        assert hud.presses == [ON_THE_VIDEO]
        assert asked == ["pause"]

    def test_a_window_with_no_panel_asks_from_the_whole_item(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.press(*ON_THE_VIDEO)

        assert asked == ["pause"]

    def test_a_press_the_panel_took_asks_for_nothing(self):
        pointer, _hud, asked = _pointer()

        pointer.press(*ON_THE_VIDEO)

        assert asked == []

    def test_the_lower_edge_is_the_item_now_that_no_row_is_drawn_there(self):
        """The track used to span it; a press there is a press on the item."""
        pointer, _hud, asked = _pointer(hud_takes=False)

        pointer.press(*LOWER_EDGE)

        assert asked == ["pause"]

    def test_a_window_with_nobody_to_ask_does_nothing(self):
        pointer = Pointer(hud=_StubHud(takes=False))

        pointer.press(*ON_THE_VIDEO)

    def test_the_wheel_is_the_panels_alone(self):
        pointer, hud, asked = _pointer(hud_takes=False)

        pointer.wheel(*ON_THE_VIDEO, 3)

        assert hud.wheels == [(*ON_THE_VIDEO, 3)]
        assert asked == []


class TestDragging:
    """Everything a held pointer can set is on the panel, so this is only about
    telling the panel where the pointer went and letting go of what it took."""

    def test_the_panel_is_told_where_the_pointer_went_either_way(self):
        pointer, hud, _asked = _pointer()

        pointer.motion(*ON_THE_VIDEO, held=False)
        pointer.motion(*LOWER_EDGE, held=True)

        assert hud.motions == [ON_THE_VIDEO, LOWER_EDGE]

    def test_what_the_panel_took_hold_of_keeps_the_drag(self):
        pointer, hud, _asked = _pointer()
        hud.holding = True

        pointer.motion(*LOWER_EDGE, held=True)

        assert hud.drags == [LOWER_EDGE]

    def test_the_button_coming_up_lets_go_of_what_it_took(self):
        pointer, hud, _asked = _pointer()
        hud.holding = True

        pointer.motion(*ON_THE_VIDEO, held=False)

        assert hud.holding is False

    def test_the_pointer_leaving_the_window_leaves_nothing_on_the_panel_lit(self):
        pointer, hud, _asked = _pointer()

        pointer.leave()

        assert hud.motions == [(-1, -1)]

    def test_a_window_with_no_panel_has_nothing_to_tell(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.motion(*LOWER_EDGE, held=True)
        pointer.wheel(*LOWER_EDGE, 1)

        assert asked == []

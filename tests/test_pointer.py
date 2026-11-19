from __future__ import annotations

from funestra.pointer import Pointer

ON_THE_VIDEO = (300, 200)
LOWER_EDGE = (300, 476)


class _StubHud:
    def __init__(self, *, takes: bool = True) -> None:
        self._takes = takes
        self.presses: list[tuple[int, int]] = []
        self.motions: list[tuple[int, int]] = []
        self.drags: list[tuple[int, int]] = []
        self.wheels: list[tuple[int, int, int]] = []
        self.right_presses: list[tuple[int, int]] = []
        self.holding = False

    def press(self, x: int, y: int) -> bool:
        self.presses.append((x, y))
        return self._takes

    def wheel(self, x: int, y: int, steps: int) -> bool:
        self.wheels.append((x, y, steps))
        return self._takes

    def right_press(self, x: int, y: int) -> bool:
        self.right_presses.append((x, y))
        return self._takes

    def motion(self, x: int, y: int) -> None:
        self.motions.append((x, y))

    def drag_to(self, x: int, y: int) -> str:
        self.drags.append((x, y))
        return ""

    def release(self) -> None:
        self.holding = False

    def covers(self, x: int, y: int) -> bool:
        return self._takes


def _pointer(*, hud: bool = True, hud_takes: bool = True):
    stub = _StubHud(takes=hud_takes) if hud else None
    asked: list = []
    return Pointer(hud=stub, item=lambda: asked.append("pause"),
                   zoom=lambda *zoom: asked.append(("zoom", *zoom)),
                   pan=lambda *pan: asked.append(("pan", *pan))), stub, asked


class TestTheItem:
    def test_a_press_the_hud_refused_asks_for_the_pause(self):
        pointer, hud, asked = _pointer(hud_takes=False)

        pointer.press(*ON_THE_VIDEO)

        assert hud.presses == [ON_THE_VIDEO]
        assert asked == ["pause"]

    def test_a_window_with_no_hud_asks_from_the_whole_item(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.press(*ON_THE_VIDEO)

        assert asked == ["pause"]

    def test_a_press_the_hud_took_asks_for_nothing(self):
        pointer, _hud, asked = _pointer()

        pointer.press(*ON_THE_VIDEO)

        assert asked == []

    def test_the_lower_edge_is_the_item_now_that_no_row_is_drawn_there(self):
        pointer, _hud, asked = _pointer(hud_takes=False)

        pointer.press(*LOWER_EDGE)

        assert asked == ["pause"]

    def test_a_window_with_nobody_to_ask_does_nothing(self):
        pointer = Pointer(hud=_StubHud(takes=False))

        pointer.press(*ON_THE_VIDEO)

    def test_the_wheel_the_hud_takes_zooms_nothing(self):
        pointer, hud, asked = _pointer()

        pointer.wheel(*ON_THE_VIDEO, 3)

        assert hud.wheels == [(*ON_THE_VIDEO, 3)]
        assert asked == []

    def test_a_right_click_is_the_huds_alone_and_never_pauses_the_item(self):
        pointer, hud, asked = _pointer(hud_takes=False)

        pointer.right_press(*ON_THE_VIDEO)

        assert hud.right_presses == [ON_THE_VIDEO]
        assert asked == []

    def test_the_wheel_off_the_hud_zooms_at_the_pointer(self):
        pointer, _hud, asked = _pointer(hud_takes=False)

        pointer.wheel(*ON_THE_VIDEO, -2)

        assert asked == [("zoom", *ON_THE_VIDEO, -2)]

    def test_a_window_with_no_hud_zooms_from_the_whole_item(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.wheel(*LOWER_EDGE, 1)

        assert asked == [("zoom", *LOWER_EDGE, 1)]


class TestTheWheelButton:
    def test_a_drag_with_the_wheel_button_down_moves_the_item_as_far_as_the_mouse_went(self):
        pointer, _hud, asked = _pointer(hud_takes=False)

        pointer.wheel_press(300, 200)
        pointer.motion(310, 195, held=False)
        pointer.motion(330, 190, held=False)

        assert asked == [("pan", 10, -5), ("pan", 20, -5)]

    def test_the_wheel_button_coming_up_ends_the_drag(self):
        pointer, _hud, asked = _pointer(hud_takes=False)
        pointer.wheel_press(300, 200)

        pointer.wheel_release()
        pointer.motion(310, 200, held=False)

        assert asked == []

    def test_the_wheel_button_pressed_on_the_hud_moves_nothing(self):
        pointer, _hud, asked = _pointer()

        pointer.wheel_press(300, 200)
        pointer.motion(310, 200, held=False)

        assert asked == []

    def test_a_window_with_no_hud_drags_from_the_whole_item(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.wheel_press(300, 200)
        pointer.motion(300, 230, held=False)

        assert asked == [("pan", 0, 30)]


class TestDragging:
    def test_the_hud_is_told_where_the_pointer_went_either_way(self):
        pointer, hud, _asked = _pointer()

        pointer.motion(*ON_THE_VIDEO, held=False)
        pointer.motion(*LOWER_EDGE, held=True)

        assert hud.motions == [ON_THE_VIDEO, LOWER_EDGE]

    def test_what_the_hud_took_hold_of_keeps_the_drag(self):
        pointer, hud, _asked = _pointer()
        hud.holding = True

        pointer.motion(*LOWER_EDGE, held=True)

        assert hud.drags == [LOWER_EDGE]

    def test_the_button_coming_up_lets_go_of_what_it_took(self):
        pointer, hud, _asked = _pointer()
        hud.holding = True

        pointer.motion(*ON_THE_VIDEO, held=False)

        assert hud.holding is False

    def test_the_pointer_leaving_the_window_leaves_nothing_on_the_hud_lit(self):
        pointer, hud, _asked = _pointer()

        pointer.leave()

        assert hud.motions == [(-1, -1)]

    def test_a_window_with_no_hud_has_nothing_to_tell(self):
        pointer, _hud, asked = _pointer(hud=False)

        pointer.motion(*LOWER_EDGE, held=True)

        assert asked == []

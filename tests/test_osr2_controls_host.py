from __future__ import annotations

from funestra.main_hud_painter import MainHud, hud_xy
from funestra.osr2_controls_host import Osr2ControlsHost

MARGIN_X, MARGIN_Y = hud_xy()


class _Painter:
    def __init__(self, *, press: str = "", drag: str = "", holding: bool = False) -> None:
        self.calls: list[tuple] = []
        self._press, self._drag = press, drag
        self.holding = holding

    def press_at(self, x: int, y: int) -> str:
        self.calls.append(("press_at", x, y))
        return self._press

    def drag_to(self, x: int, y: int) -> str:
        self.calls.append(("drag_to", x, y))
        return self._drag

    def motion(self, x: int, y: int) -> None:
        self.calls.append(("motion", x, y))

    def release(self) -> None:
        self.calls.append(("release",))

    def leave(self) -> None:
        self.calls.append(("leave",))

    def rgba(self, hud: MainHud) -> tuple[bytes, tuple[int, int]]:
        self.calls.append(("rgba", hud))
        return b"\x00" * 16, (2, 2)


def _host(painter: _Painter) -> tuple[Osr2ControlsHost, list[str]]:
    posted: list[str] = []
    return Osr2ControlsHost(post=posted.append, painter=painter), posted


class TestAPress:
    def test_posts_what_the_painter_says_was_pressed_there(self):
        host, posted = _host(_Painter(press="robot_hand_cycle_shape"))

        host.press(5, 7)

        assert posted == ["robot_hand_cycle_shape"]

    def test_is_placed_in_the_hud_s_own_pixels(self):
        painter = _Painter()
        host, _posted = _host(painter)

        host.press(5, 7)

        assert painter.calls == [("press_at", 5 + MARGIN_X, 7 + MARGIN_Y)]

    def test_on_nothing_posts_nothing(self):
        host, posted = _host(_Painter(press=""))

        host.press(5, 7)

        assert posted == []


class TestThePointerMoving:
    def test_over_a_band_it_took_hold_of_posts_the_level_it_drags_to(self):
        host, posted = _host(_Painter(drag="robot_hand_speed_70", holding=True))

        host.move(30, 9)

        assert posted == ["robot_hand_speed_70"]

    def test_over_nothing_held_names_what_is_under_it_and_posts_nothing(self):
        painter = _Painter(drag="robot_hand_speed_70", holding=False)
        host, posted = _host(painter)

        host.move(30, 9)

        assert (posted, painter.calls) == ([], [("motion", 30 + MARGIN_X, 9 + MARGIN_Y)])


class TestLettingGo:
    def test_the_button_coming_up_lets_go_of_a_band(self):
        painter = _Painter()
        host, _posted = _host(painter)

        host.release()

        assert painter.calls == [("release",)]

    def test_the_pointer_leaving_leaves_nothing_named(self):
        painter = _Painter()
        host, _posted = _host(painter)

        host.leave()

        assert painter.calls == [("leave",)]


class TestTheDrawing:
    def test_is_the_painter_s_drawing_of_the_main_hud_it_is_handed(self):
        painter = _Painter()
        host, _posted = _host(painter)
        hud = MainHud()

        drawn = host.drawing(hud)

        assert (drawn, painter.calls) == ((b"\x00" * 16, (2, 2)), [("rgba", hud)])

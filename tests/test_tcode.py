from __future__ import annotations

import pytest
from app_support.osr2_hold import HOLD_MOVE_MS, PARK
from import_checks import assert_imports_without

from funestra.tcode import (
    PARK_COMMAND,
    POSITION_MAX,
    UdpTCodeSink,
    format_tcode_command,
    to_tcode_position,
)


class RaisingSock:
    def __init__(self):
        self.attempts = 0
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.attempts += 1
        raise OSError(10038, "An operation was attempted on something that is not a socket")

    def close(self) -> None:
        self.closed = True


class FakeSock:
    def __init__(self):
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


class TestUdpTCodeSink:
    def test_send_transmits_newline_terminated_ascii_datagram(self):
        sock = FakeSock()
        sink = UdpTCodeSink(host="127.0.0.1", port=50557, sock=sock)
        sink.send("L05000I33")
        assert sock.sent == [(b"L05000I33\n", ("127.0.0.1", 50557))]

    def test_close_closes_socket(self):
        sock = FakeSock()
        sink = UdpTCodeSink(sock=sock)
        sink.close()
        assert sock.closed is True

    def test_defaults(self):
        sock = FakeSock()
        sink = UdpTCodeSink(sock=sock)
        sink.send("L09999I50")
        assert sock.sent == [(b"L09999I50\n", ("127.0.0.1", 50557))]

    def test_a_send_after_close_is_not_even_tried_since_another_thread_often_still_sends_at_shutdown_and_udp_reports_nothing_either_way(self):
        sock = RaisingSock()
        sink = UdpTCodeSink(sock=sock)
        sink.close()
        sink.send("L05000I33")
        assert sock.attempts == 0

    def test_a_close_landing_while_another_thread_s_send_is_in_flight_is_silence_too(self):
        landed = []

        class ClosedMidSend:
            def sendto(self, data, address):
                sink.close()
                landed.append("the close, mid-send")
                raise OSError("not a socket")

            def close(self):
                pass

        sink = UdpTCodeSink(sock=ClosedMidSend())

        sink.send("L05000I33")

        assert landed == ["the close, mid-send"]

    def test_a_send_that_fails_while_the_sink_is_open_still_raises(self):
        sink = UdpTCodeSink(sock=RaisingSock())
        with pytest.raises(OSError, match="not a socket"):
            sink.send("L05000I33")


class TestFormatTcodeCommand:
    def test_max_position(self):
        assert format_tcode_command("L0", 9999, 33) == "L09999I33"

    def test_min_position(self):
        assert format_tcode_command("L0", 0, 100) == "L00000I100"

    def test_center_position(self):
        assert format_tcode_command("L0", 5000, 50) == "L05000I50"

    def test_clamps_position_above_max(self):
        assert format_tcode_command("L0", 10500, 33) == "L09999I33"

    def test_clamps_position_below_zero(self):
        assert format_tcode_command("L0", -5, 33) == "L00000I33"


class TestToTcodePosition:
    def test_the_ends_of_the_range_are_the_ends_of_the_range(self):
        assert to_tcode_position(0) == 0
        assert to_tcode_position(100) == POSITION_MAX

    def test_a_position_between_them_scales(self):
        assert to_tcode_position(50) == 5000
        assert to_tcode_position(1) == 100


def test_it_says_the_wire_format_for_both_drivers_and_imports_neither():
    assert_imports_without("funestra.tcode", "funestra.tcode_driver", "funestra.robot_hand_driver", "funestra.robot_hand")


def test_the_park_command_rests_the_motion_axis_at_the_floor_over_the_hold_move():

    assert format_tcode_command("L0", 0, HOLD_MOVE_MS[PARK]) == PARK_COMMAND

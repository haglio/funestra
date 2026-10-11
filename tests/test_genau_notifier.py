from __future__ import annotations

from pathlib import Path

from funestra.genau_notifier import GenauNotifier


class FakeSocket:
    def __init__(self):
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


def test_notify_flick_sends_flick_stem_and_says_it_again_for_a_companion_from_before_the_rename():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.notify_flick(Path("demo.mp4"))

    assert sock.sent == [(b"FLICK demo", ("127.0.0.1", 9999)), (b"CLIP demo", ("127.0.0.1", 9999))]


def test_notify_visible_deduplicates_repeated_state():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.notify_visible(True)
    notifier.notify_visible(True)
    notifier.notify_visible(False)

    assert sock.sent == [
        (b"VISIBLE 1", ("127.0.0.1", 9999)),
        (b"VISIBLE 0", ("127.0.0.1", 9999)),
    ]


def test_the_notifier_has_only_the_two_things_it_says():
    """FLICK and VISIBLE, each with one caller.

    A third method wrapped them to send both at once, for a first tick that
    had already had its FLICK sent by the flick selection a moment earlier --
    so it put the same datagram on the wire twice at every launch.
    """
    assert not hasattr(GenauNotifier, "announce_visible")


def test_close_closes_socket():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.close()

    assert sock.closed is True


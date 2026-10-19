"""The T-Code wire format and its UDP transport, shared by every OSR2 driver.

T-Code is the one-line command language the OSR2 broker's UDP inlet accepts
(``L0<pos>I<ms>``: move the linear axis to *pos* over *ms* milliseconds).  Both
driver styles in this family speak it — Genau's phase-driven motion sender and
the funscript waypoint driver (:mod:`funestra.tcode_driver`) — so the format
and the datagram sink live here, beneath both.  What to send and when stays
with each driver; this module only says it correctly.
"""
from __future__ import annotations

import socket
from typing import Protocol

from app_support import ports
from app_support.osr2_hold import PARK, hold_tcode

# The ceiling of the linear axis's range; 0 is the floor of it.
POSITION_MAX = 9999

PARK_COMMAND = hold_tcode(PARK)


def to_tcode_position(percent: float) -> int:
    """A 0-100 motion position as the 0-9999 one the wire carries."""
    return round(percent * POSITION_MAX / 100)


# How long the device is given to arrive at the incoming driver's motion when it
# changes hands.
#
# Both drivers in this family send "be at *pos* in *ms*", and the OSR2
# interpolates from wherever it already is — so neither has to know where the
# other left it.  What went wrong was only the *time*: each driver's first
# command after taking over asked for its own position in its own ordinary
# interval — a motion tick, or the gap to the next waypoint — which can be tens
# of milliseconds.  Across a handoff that is most of the travel in a twitch.
# Stretching that first command alone turns the seam into a glide, and every
# command after it is the driver's own again, so nothing else changes.
#
# Long enough to read as a movement rather than a jolt, short enough that a
# funscript is back on its own timing within a beat.
HANDOFF_MS = 300


class HandoffGlide:
    """The stretch of time after a driver takes the device over, during which
    every command it sends is given the glide.

    Not the first command alone: a driver that goes on sending — Genau's motion
    ticks thirty times a second — would have its stretched command superseded a
    frame later by an ordinary one, and the device would cover whatever was left
    of the gap in that frame instead.  Flooring the interval for the whole glide
    instead makes each command re-aim at a moving target it is always given
    :data:`HANDOFF_MS` to reach, so the device eases onto the incoming motion and
    is on it by the time the floor lifts.  A driver that sends sparsely gets the
    same treatment for free.

    One rule in one place: both drivers in this family ask for it the same way,
    so the seam is the same length whichever direction the device changes hands.
    """

    def __init__(self) -> None:
        self._armed = False
        self._until: float | None = None

    def begin(self) -> None:
        """Take the device: glide onto whatever this driver sends next.

        The clock starts on that first command rather than here, because a
        driver can be handed the device well before it has anything to say — the Main Funestra
        is told to drive at a handoff and sends nothing until the playhead
        reaches its next waypoint — and a glide that had already run out by then
        would smooth nothing.
        """
        self._armed, self._until = True, None

    def interval_ms(self, interval_ms: int, now: float) -> int:
        """*interval_ms*, floored at the glide while one is still running."""
        if self._armed:
            self._armed, self._until = False, now + HANDOFF_MS / 1000
        if self._until is None:
            return interval_ms
        if now >= self._until:
            self._until = None
            return interval_ms
        return max(interval_ms, HANDOFF_MS)


def format_tcode_command(axis: str, position: int, interval_ms: int) -> str:
    position = max(0, min(POSITION_MAX, position))
    interval_ms = max(0, interval_ms)
    return f"{axis}{position:04d}I{interval_ms}"


class TCodeSink(Protocol):
    def send(self, command: str) -> None: ...
    def close(self) -> None: ...


class UdpTCodeSink:
    def __init__(
        self, host: str = "127.0.0.1", port: int = ports.TCODE_UDP, *, sock=None,
    ) -> None:
        self._host = host
        self._port = port
        self._closed = False
        self._sock = sock if sock is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, command: str) -> None:
        """Put one command on the wire; a sink that has been closed sends nothing.

        Closing while another thread is still driving is the ordinary shape of
        shutdown here — Fun Time's VR Funestra closes its main role from the
        render thread while the file-channel worker is still ticking it — and a
        raise there kills that worker mid-teardown (WSAENOTSOCK, observed).
        Silence is the honest answer either way: a datagram sent where nobody
        is listening is already indistinguishable, to this sink, from one the
        broker received.  A send that fails while the sink is still OPEN still
        raises, so a misaddressed sink is as loud as it ever was.
        """
        if self._closed:
            return
        try:
            self._sock.sendto((command + "\n").encode("ascii"), (self._host, self._port))
        except OSError:
            if not self._closed:
                raise

    def close(self) -> None:
        self._closed = True
        self._sock.close()

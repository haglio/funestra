"""What the broker feeds Genau: whether it has the room, the beat, the pulse.

The OSR2 broker publishes over UDP.  Three of its verbs are acted on here --
``AUTO`` hands the room to the broker or takes it back, ``BPM`` names the beat
and ``SYNC`` is a downbeat -- and they land in a :class:`BrokerFeed` a reader
thread writes and a frame loop reads, under one lock.  The loop takes a
:func:`snapshot` rather than reading the fields one at a time, so a tick never
sees half of one datagram and half of the next.
"""
from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass, field

__all__ = [
    "BrokerFeed",
    "udp_reader",
]

@dataclass
class BrokerFeed:
    lock: threading.Lock = field(default_factory=threading.Lock)
    auto_active: bool = False
    raw_bpm: float | None = None
    sync_pulse_id: int = 0


@dataclass(frozen=True)
class BrokerSnapshot:
    auto_active: bool
    raw_bpm: float | None
    sync_pulse_id: int


def snapshot(feed: BrokerFeed) -> BrokerSnapshot:
    with feed.lock:
        return BrokerSnapshot(
            auto_active=feed.auto_active,
            raw_bpm=feed.raw_bpm,
            sync_pulse_id=feed.sync_pulse_id,
        )


# How long to wait between bind attempts.  The port is usually held by the
# session that just ended, so the first retry is short and the last is long
# enough to outlast a slow teardown.
_BIND_RETRY_DELAYS = (0.5, 1.0, 2.0)

# How long a read waits before looking at the stop flag again.  Short enough
# that a quit is not felt, long enough that an idle listener is not a spin.
_READ_TIMEOUT_S = 0.2


def apply_udp_line(feed: BrokerFeed, line: str, logger: logging.Logger) -> None:
    """Act on one datagram from the broker.

    Three of the eight verbs the broker sends are acted on.  The other five --
    SHOW, HIDE, BEATS, MOTION, PATTERN -- arrive and fall through exactly as an
    unrecognized line does; whether the broker should stop sending them is the
    broker's call, not this reader's.

    Split out of the socket loop so a verb can be tested without binding a
    port: thirteen of the fifteen slowest tests in the repo this came from used
    to be this parsing, reached through a real socket.
    """
    said = line.split(" ", 1)
    verb = said[0].upper()
    arg = said[1].strip() if len(said) > 1 else ""

    with feed.lock:
        if verb == "AUTO":
            feed.auto_active = arg == "1"
            logger.info("Received AUTO %s", 1 if feed.auto_active else 0)
        elif verb == "BPM":
            try:
                feed.raw_bpm = float(arg)
            except ValueError:
                logger.warning("Invalid BPM payload: %s", line)
        elif verb == "SYNC":
            feed.sync_pulse_id += 1


def bind_with_retry(
    sock: socket.socket,
    host: str,
    port: int,
    stop_event: threading.Event,
    logger: logging.Logger,
    retry_delays: tuple[float, ...] = _BIND_RETRY_DELAYS,
) -> bool:
    """Take the port, waiting for it if something else still has it.

    Returns False only when the wait was cut short by a quit; a port that never
    frees raises on the last attempt, which is the caller's to report.

    retry_delays is a parameter only so a test can ask for a schedule it
    does not have to sit through: the app passes nothing and gets the module's
    own, so what ships is the timing that was always here.
    """
    for attempt, delay in enumerate(retry_delays, 1):
        try:
            sock.bind((host, port))
            return True
        except OSError as exc:
            logger.warning(
                "UDP bind attempt %d failed on %s:%s: %s — retrying in %.1fs",
                attempt, host, port, exc, delay,
            )
            if stop_event.wait(delay):
                return False
    # Out of retries — let this one raise, so the reason reaches the log.
    sock.bind((host, port))
    return True


def udp_reader(host: str, port: int, feed: BrokerFeed, stop_event: threading.Event,
               logger: logging.Logger,
               retry_delays: tuple[float, ...] = _BIND_RETRY_DELAYS) -> None:
    """Bind a UDP listener on ``host:port`` and turn what arrives into ``feed``.

    ``retry_delays`` is the schedule the bind backs off on while the port is
    still held -- by the previous run of this app, usually. It is a parameter
    only so a test can ask for a schedule it does not have to sit through: the
    app passes nothing and gets the module's own, so what ships is the timing
    that was always here.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        if not bind_with_retry(sock, host, port, stop_event, logger, retry_delays):
            return

        sock.settimeout(_READ_TIMEOUT_S)
        logger.info("Broker UDP listener bound on %s:%s", host, port)

        while not stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            apply_udp_line(
                feed, data.decode("utf-8", errors="replace").strip(), logger)
    except Exception:
        logger.exception("UDP reader failed")
    finally:
        sock.close()

from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass, field


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


_BIND_RETRY_DELAYS = (0.5, 1.0, 2.0)

_READ_TIMEOUT_S = 0.2


def apply_udp_line(feed: BrokerFeed, line: str, logger: logging.Logger) -> None:
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
    sock.bind((host, port))
    return True


def udp_reader(host: str, port: int, feed: BrokerFeed, stop_event: threading.Event,
               logger: logging.Logger,
               retry_delays: tuple[float, ...] = _BIND_RETRY_DELAYS) -> None:
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

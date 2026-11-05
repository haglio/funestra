from __future__ import annotations

import threading
from pathlib import Path

from funestra.status import (
    FunestraStatus,
    StatusWriter,
    parse_status,
    status_fields,
)


class StubSession:
    def __init__(self) -> None:
        self.current_video = Path("C:/vids/clip.mp4")
        self.position_ms = 12345.6


def _fields(session):
    return {
        "video": str(session.current_video),
        "position_ms": str(int(session.position_ms)),
    }


class TestStatusWriter:
    def test_writes_the_fields_the_funestra_supplies(self, tmp_path):
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession())

        text = status_path.read_text(encoding="utf-8")
        assert "video=C:\\vids\\clip.mp4\n" in text or "video=C:/vids/clip.mp4\n" in text
        assert "position_ms=12345\n" in text

    def test_writes_one_key_per_line_in_the_funestras_own_order(self, tmp_path):
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(
            status_path, lambda _s: {"b": "2", "a": "1"}, now_source=lambda: 0.0,
        )

        writer.write(StubSession())

        assert status_path.read_text(encoding="utf-8") == "b=2\na=1\n"

    def test_creates_the_state_directory_since_a_funestra_may_publish_before_anything_else_has_made_it(self, tmp_path):
        status_path = tmp_path / "state" / "status.txt"
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession())
        assert status_path.exists()

    def test_throttles_writes_within_interval(self, tmp_path):
        status_path = tmp_path / "status.txt"
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )
        session = StubSession()

        writer.write(session)
        session.position_ms = 12400.0
        clock["t"] = 0.1

        assert not writer.write(session)
        assert "position_ms=12345" in status_path.read_text(encoding="utf-8")

    def test_writes_again_after_interval(self, tmp_path):
        status_path = tmp_path / "status.txt"
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )
        session = StubSession()

        writer.write(session)
        session.position_ms = 12400.0
        clock["t"] = 0.25

        assert writer.write(session)
        assert "position_ms=12400" in status_path.read_text(encoding="utf-8")

    def test_a_poller_never_reads_a_half_written_record(self, tmp_path):
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(status_path, _fields, min_interval=0.0)
        session = StubSession()
        writer.write(session)

        stop = threading.Event()
        torn: list[str] = []

        def poll() -> None:
            while not stop.is_set():
                try:
                    text = status_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "video=" not in text or "position_ms=" not in text:
                    torn.append(text)

        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        try:
            for tick in range(120):
                session.position_ms = 12345.6 + tick
                writer.write(session)
        finally:
            stop.set()
            poller.join(timeout=5)

        assert not torn, f"the poller read {len(torn)} incomplete records, e.g. {torn[0]!r}"

    def test_an_unwritable_path_is_reported_not_raised_so_a_locked_file_never_takes_down_the_run_loop_and_the_next_tick_tries_again(self, tmp_path):
        status_path = tmp_path / "status.txt"
        status_path.mkdir()
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession()) is False
        assert list(tmp_path.iterdir()) == [status_path]

    def test_a_failed_write_does_not_start_the_throttle(self, tmp_path):
        status_path = tmp_path / "state"
        status_path.mkdir()
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )

        assert writer.write(StubSession()) is False
        status_path.rmdir()

        assert writer.write(StubSession()) is True


class TestWhatEveryFunestraPublishes:
    def test_the_lines_every_funestra_shares_in_the_order_they_are_written_each_funestra_s_own_lines_being_its_own_repo_s(self):
        fields = status_fields(FunestraStatus(
            video="C:/vids/a.mp4", position_ms=1500, duration_ms=5000, paused=False, locked=True,
            speed=1.5, read_at=1_000.0))

        assert fields == {
            "video": "C:/vids/a.mp4", "position_ms": "1500", "duration_ms": "5000",
            "paused": "0", "locked": "1", "speed": "1.5", "picture": "0", "read_at": "1000.000",
        }
        assert list(fields) == ["video", "position_ms", "duration_ms", "paused", "locked",
                                "speed", "picture", "read_at"]

    def test_a_playhead_is_published_as_whole_milliseconds(self):
        assert status_fields(FunestraStatus(position_ms=12345.9))["position_ms"] == "12345"

    def test_a_status_says_when_its_playhead_was_read_since_the_file_s_own_time_trails_it_by_every_read_made_after(self):
        status = FunestraStatus(video="C:/vids/a.mp4", position_ms=1500, read_at=1_000.25)

        assert status_fields(status)["read_at"] == "1000.250"
        assert parse_status(status_fields(status)).read_at == 1_000.25

    def test_what_is_published_is_what_is_read_back(self):
        status = FunestraStatus(
            video="C:/vids/b.mp4", position_ms=250, duration_ms=9000, paused=True, locked=False,
            speed=0.75)

        assert parse_status(status_fields(status)) == status

    def test_a_status_that_says_an_image_is_on_screen_reads_back_saying_so(self):
        status = FunestraStatus(video="C:/images/one.png", locked=True, image=True)

        assert parse_status(status_fields(status)) == status

    def test_a_key_the_file_does_not_carry_keeps_the_readers_default(self):
        assert parse_status({}) == FunestraStatus()
        assert parse_status({}, default=FunestraStatus(locked=True)).locked is True
        assert parse_status({"locked": "0"}, default=FunestraStatus(locked=True)).locked is False

    def test_a_flag_is_on_only_when_the_file_says_1(self):
        assert parse_status({"paused": "1"}).paused is True
        assert parse_status({"paused": ""}, default=FunestraStatus(paused=True)).paused is False

    def test_a_number_that_cannot_be_read_keeps_the_default_too(self):
        assert parse_status({"position_ms": "soon", "duration_ms": " 40 "}).position_ms == 0
        assert parse_status({"position_ms": "soon", "duration_ms": " 40 "}).duration_ms == 40
        assert parse_status({"speed": "fast"}, default=FunestraStatus(speed=0.5)).speed == 0.5

    def test_the_lines_a_funestra_adds_of_its_own_ride_past_the_reader(self):
        status = parse_status({"video": " C:/vids/c.mp4 ", "playlist_length": "3", "state": "looping"})

        assert status == FunestraStatus(video="C:/vids/c.mp4")

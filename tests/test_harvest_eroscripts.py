"""The corpus harvester, run against an invented forum.

Every topic, title, upload key and file name here is made up.
"""
from __future__ import annotations

import email.message
import io
import json
import logging
import urllib.error
from pathlib import Path

import pytest
from app_support import haglio_settings

from tools import harvest_eroscripts as harvest


class TestFindingTheScriptsInAPost:
    def test_only_main_axis_funscripts_are_taken(self):
        cooked = (
            '<p>Enjoy.</p>'
            '<a class="attachment" href="/uploads/short-url/aaaaaaaaaaaaaaaaaaaaaaaaaaa.funscript">'
            'scene one.funscript</a> (12.3 KB)'
            '<a class="attachment" href="/uploads/short-url/bbbbbbbbbbbbbbbbbbbbbbbbbbb.funscript">'
            'scene one.roll.funscript</a> (4 KB)'
            '<a class="attachment" href="/uploads/short-url/ccccccccccccccccccccccccccc.funscript">'
            'scene one.pitch.funscript</a> (4 KB)'
            '<a class="attachment" href="/uploads/short-url/ddddddddddddddddddddddddddd.zip">'
            'scene one.zip</a> (400 KB)'
            '<a class="attachment" href="/uploads/short-url/eeeeeeeeeeeeeeeeeeeeeeeeeee.funscript">'
            'scene two &amp; three.funscript</a> (20 KB)'
        )

        found = harvest.attachments_in(cooked)

        assert found == [
            harvest.Attachment("/uploads/short-url/aaaaaaaaaaaaaaaaaaaaaaaaaaa.funscript",
                               "scene one.funscript"),
            harvest.Attachment("/uploads/short-url/eeeeeeeeeeeeeeeeeeeeeeeeeee.funscript",
                               "scene two & three.funscript"),
        ]


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeClock:
    """Time that only moves when something sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class TestPacingTheForum:
    def test_requests_are_spaced_by_the_pace(self):
        clock = _FakeClock()
        asked: list[str] = []

        def opener(request, timeout):
            asked.append(request.full_url)
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=2.5)

        forum.get_json("/a.json")
        forum.get_json("/b.json")

        assert asked == ["https://forum.invalid/a.json", "https://forum.invalid/b.json"]
        assert clock.slept == [2.5]

    def test_a_limit_the_forum_names_is_waited_out_then_retried(self):
        clock = _FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _too_many_requests(request.full_url, retry_after="7")
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        assert forum.get_json("/a.json") == {"ok": 1}
        assert calls == 2
        assert clock.slept == [7.0 + harvest.RETRY_GRACE_S]

    def test_a_limit_being_waited_out_is_said_in_the_log(self, caplog):
        clock = _FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _too_many_requests(request.full_url, retry_after="3600")
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0,
                              log=logging.getLogger("harvest-under-test"))

        with caplog.at_level(logging.INFO, logger="harvest-under-test"):
            forum.get_json("/a.json")

        assert [record.getMessage() for record in caplog.records] == [
            f"rate limited at https://forum.invalid/a.json: waiting {3600 + harvest.RETRY_GRACE_S:.0f} s",
        ]


    def test_a_request_the_network_drops_is_waited_out_and_asked_again(self, caplog):
        clock = _FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("The read operation timed out")
            if calls == 2:
                raise urllib.error.URLError("a connection attempt failed")
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0,
                              log=logging.getLogger("harvest-under-test"))

        with caplog.at_level(logging.INFO, logger="harvest-under-test"):
            assert forum.get_json("/a.json") == {"ok": 1}

        assert calls == 3
        assert [record.getMessage() for record in caplog.records] == [
            f"no answer from https://forum.invalid/a.json (The read operation timed out): waiting {harvest.NETWORK_WAITS_S[0]:.0f} s",
            f"no answer from https://forum.invalid/a.json (<urlopen error a connection attempt failed>): waiting {harvest.NETWORK_WAITS_S[1]:.0f} s",
        ]

    def test_a_network_that_stays_down_ends_the_run_with_its_error(self):
        clock = _FakeClock()

        def opener(request, timeout):
            raise TimeoutError("The read operation timed out")

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        with pytest.raises(TimeoutError):
            forum.get_json("/a.json")

    def test_a_forum_too_busy_to_answer_is_waited_out_and_asked_again(self, caplog):
        clock = _FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _too_busy(request.full_url)
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0,
                              log=logging.getLogger("harvest-under-test"))

        with caplog.at_level(logging.INFO, logger="harvest-under-test"):
            assert forum.get_json("/a.json") == {"ok": 1}

        assert calls == 2
        assert [record.getMessage() for record in caplog.records] == [
            ("no answer from https://forum.invalid/a.json (HTTP Error 503: Service Unavailable):"
             f" waiting {harvest.NETWORK_WAITS_S[0]:.0f} s"),
        ]

    def test_a_file_that_is_simply_not_there_is_not_waited_out(self):
        clock = _FakeClock()

        def opener(request, timeout):
            raise _not_found(request.full_url)

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        with pytest.raises(urllib.error.HTTPError):
            forum.get_json("/a.json")

        assert clock.slept == []


def _too_many_requests(url: str, *, retry_after: str):
    headers = email.message.Message()
    headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(url, 429, "Too Many Requests", headers, io.BytesIO(b"{}"))


def _too_busy(url: str):
    return urllib.error.HTTPError(
        url, 503, "Service Unavailable", email.message.Message(), io.BytesIO(b""))


def _not_found(url: str):
    return urllib.error.HTTPError(
        url, 404, "Not Found", email.message.Message(), io.BytesIO(b""))


def _redirect(url: str, *, to: str):
    headers = email.message.Message()
    headers["Location"] = to
    return urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))


_SHA = "0123456789abcdef0123456789abcdef01234567"
_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _short_link(sha: str = _SHA) -> str:
    number, digits = int(sha, 16), ""
    while number:
        number, digit = divmod(number, 62)
        digits = _BASE62[digit] + digits
    return f"/uploads/short-url/{digits}.funscript"


class TestWorkingOutWhereAFileIs:
    def test_a_short_link_names_the_file_so_its_address_needs_no_asking(self):
        host = harvest.FILE_HOST

        assert harvest.file_addresses(_short_link()) == [
            f"{host}/original/4X/0/1/2/{_SHA}.funscript",
            f"{host}/original/3X/0/1/{_SHA}.funscript",
            f"{host}/original/2X/0/{_SHA}.funscript",
            f"{host}/original/1X/{_SHA}.funscript",
        ]

    def test_a_name_that_begins_with_zeros_keeps_them(self):
        sha = "000000" + _SHA[6:]

        assert harvest.file_addresses(_short_link(sha))[0].endswith(f"/0/0/0/{sha}.funscript")


class TestDownloadingAScript:
    def test_the_file_is_fetched_from_where_its_link_says_without_asking_the_forum(self):
        # Each ask of the forum comes off the day's allowance and a file host
        # asks nothing, so the file is fetched by the address its link spells
        # out, and the forum is not asked for it at all.
        clock = _FakeClock()
        seen: list[tuple[str, str | None]] = []
        found = harvest.file_addresses(_short_link())[1]

        def opener(request, timeout):
            seen.append((request.full_url, request.get_header("User-api-key")))
            if request.full_url != found:
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", email.message.Message(), io.BytesIO(b""))
            return _FakeResponse(b'{"actions": []}')

        forum = harvest.Forum("https://forum.invalid", {"User-Api-Key": "k"}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        body, where = forum.download(_short_link())

        assert (body, where) == (b'{"actions": []}', found)
        assert seen == [(harvest.file_addresses(_short_link())[0], None), (found, None)]
        assert clock.slept == []

    def test_a_file_the_host_has_at_no_address_is_asked_of_the_forum(self):
        # The forum resolves its short link to the file host; the key is the
        # forum's business and goes nowhere else.
        clock = _FakeClock()
        seen: list[tuple[str, str | None]] = []

        def opener(request, timeout):
            seen.append((request.full_url, request.get_header("User-api-key")))
            if request.full_url.startswith(harvest.FILE_HOST):
                raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", email.message.Message(), io.BytesIO(b""))
            if "/uploads/short-url/" in request.full_url:
                raise _redirect(request.full_url,
                                to="https://files.invalid/original/1/2/abc123.funscript")
            return _FakeResponse(b'{"actions": []}')

        forum = harvest.Forum("https://forum.invalid", {"User-Api-Key": "k"}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        body, where = forum.download("/uploads/short-url/aaa.funscript")

        assert body == b'{"actions": []}'
        assert where == "https://files.invalid/original/1/2/abc123.funscript"
        assert seen == [
            *((address, None) for address in harvest.file_addresses("/uploads/short-url/aaa.funscript")),
            ("https://forum.invalid/uploads/short-url/aaa.funscript", "k"),
            ("https://files.invalid/original/1/2/abc123.funscript", None),
        ]
        # The pace is the forum's; a file server is not asked to wait for it.
        assert clock.slept == []


class _FakeForum:
    def __init__(self, pages: dict, topics: dict, files: dict):
        self.pages = pages
        self.topics = topics
        self.files = files
        self.asked: list[str] = []

    def get_json(self, path: str) -> dict:
        self.asked.append(path)
        if path in self.pages:
            return self.pages[path]
        topic_id = int(path.removeprefix("/t/").removesuffix(".json"))
        if topic_id not in self.topics:
            raise urllib.error.HTTPError(path, 404, "Not Found", email.message.Message(),
                                         io.BytesIO(b""))
        return self.topics[topic_id]

    def download(self, short_url: str) -> tuple[bytes, str]:
        self.asked.append(short_url)
        return self.files[short_url]


def _anchor(key: str, name: str) -> str:
    return f'<a class="attachment" href="/uploads/short-url/{key}.funscript">{name}</a>'


def _topic(topic_id: int, cooked: str) -> dict:
    return {
        "id": topic_id, "title": f"scene {topic_id}", "tags": ["alpha", "beta"],
        "created_at": "2026-01-02T03:04:05.000Z",
        "post_stream": {"posts": [{"post_number": 1, "cooked": cooked}]},
    }


class TestWalkingTheCategory:
    def test_every_new_topics_scripts_are_saved_once_under_neutral_names(self, tmp_path):
        forum = _FakeForum(
            pages={
                "/c/scripts/free-scripts/14.json?page=0": {"topic_list": {
                    "topics": [{"id": 101}, {"id": 102}],
                    "more_topics_url": "/c/scripts/free-scripts/14?page=1"}},
                "/c/scripts/free-scripts/14.json?page=1": {"topic_list": {
                    "topics": [{"id": 103}, {"id": 104}]}},
            },
            topics={
                101: _topic(101, _anchor("aaa", "scene one.funscript")
                            + _anchor("bbb", "scene one.roll.funscript")),
                103: _topic(103, _anchor("aaa", "scene one again.funscript")
                            + _anchor("ccc", "scene three.funscript")),
            },
            files={
                "/uploads/short-url/aaa.funscript": (b'{"actions": [1]}', "https://files.invalid/a"),
                "/uploads/short-url/ccc.funscript": (b'{"actions": [3]}', "https://files.invalid/c"),
            },
        )
        store = harvest.Store(tmp_path)
        store.finish(102)

        taken = harvest.harvest(forum, store, log=logging.getLogger("test"))

        assert taken == 3
        assert "/t/102.json" not in forum.asked
        assert forum.asked.count("/uploads/short-url/aaa.funscript") == 1
        assert sorted(p.name for p in (tmp_path / "scripts").iterdir()) == [
            "t101_p1_1.funscript", "t103_p1_2.funscript"]
        assert (tmp_path / "scripts" / "t103_p1_2.funscript").read_bytes() == b'{"actions": [3]}'
        records = [json.loads(line) for line in
                   (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [r["file"] for r in records] == ["t101_p1_1.funscript", "t103_p1_2.funscript"]
        assert records[1] == {
            "file": "t103_p1_2.funscript", "topic": 103, "post": 1,
            "url": "/uploads/short-url/ccc.funscript", "where": "https://files.invalid/c",
            "name": "scene three.funscript", "title": "scene 103", "tags": ["alpha", "beta"],
            "created_at": "2026-01-02T03:04:05.000Z", "bytes": 16,
        }
        assert (tmp_path / "done_topics.txt").read_text().split() == ["102", "101", "103", "104"]

    def test_a_second_run_picks_up_where_the_first_stopped(self, tmp_path):
        forum = _FakeForum(
            pages={"/c/scripts/free-scripts/14.json?page=0": {"topic_list": {
                "topics": [{"id": 101}, {"id": 103}]}}},
            topics={101: _topic(101, _anchor("aaa", "scene one.funscript")),
                    103: _topic(103, _anchor("ccc", "scene three.funscript"))},
            files={"/uploads/short-url/aaa.funscript": (b"{}", "https://files.invalid/a"),
                   "/uploads/short-url/ccc.funscript": (b"{}", "https://files.invalid/c")},
        )
        harvest.harvest(forum, harvest.Store(tmp_path), log=logging.getLogger("test"),
                        max_topics=1)
        forum.asked.clear()

        taken = harvest.harvest(forum, harvest.Store(tmp_path), log=logging.getLogger("test"))

        assert taken == 1
        assert "/t/101.json" not in forum.asked
        assert sorted(p.name for p in (tmp_path / "scripts").iterdir()) == [
            "t101_p1_1.funscript", "t103_p1_1.funscript"]


class TestWhichCorpusIsWorkedIn:
    def test_a_corpus_not_named_is_the_folder_the_shared_settings_give(self, monkeypatch):
        monkeypatch.setenv(haglio_settings.SETTINGS_ENV, haglio_settings.THE_EXAMPLE)

        args = harvest.parse_arguments([])

        assert args.corpus == Path(haglio_settings.EXAMPLE["funscript_corpus_dir"])

    def test_a_corpus_named_is_worked_in_without_asking_the_shared_settings(
            self, tmp_path, monkeypatch):
        settings = tmp_path / "settings.json"
        settings.write_text("{}", encoding="utf-8")
        monkeypatch.setenv(haglio_settings.SETTINGS_ENV, str(settings))

        args = harvest.parse_arguments(["--corpus", str(tmp_path / "collection")])

        assert args.corpus == tmp_path / "collection"

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from funestra.libmpv_loader import machine_libmpv_dir
from tools import fetch_libmpv

_ARCHIVE = b"not really a 7-zip archive"
_DIGEST = hashlib.sha256(_ARCHIVE).hexdigest()


def _never_called(*_args, **_kwargs):
    raise AssertionError("nothing here should have gone to the network")


class TestTheLock:
    def test_the_pin_names_a_source_a_tag_an_asset_and_a_digest(self):
        pinned = fetch_libmpv.lock()

        assert set(pinned) == {"source", "fallback", "tag", "asset", "sha256"}
        assert len(pinned["sha256"]) == 64

    def test_the_pinned_url_is_built_from_the_three_names(self):
        pinned = {"source": "someone/mpv-builds", "tag": "2026-01-02-abcdef",
                  "asset": "mpv-dev-x86_64-20260102-git-abcdef.7z", "sha256": _DIGEST}

        url, digest = fetch_libmpv.pinned_asset(pinned)

        assert url == ("https://github.com/someone/mpv-builds/releases/download/"
                       "2026-01-02-abcdef/mpv-dev-x86_64-20260102-git-abcdef.7z")
        assert digest == _DIGEST


class TestWhatIsFetched:
    def test_an_archive_whose_digest_matches_is_kept(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(fetch_libmpv.urllib.request, "urlretrieve",
                            lambda _url, target: Path(target).write_bytes(_ARCHIVE))

        archive = fetch_libmpv.download("https://example.invalid/mpv.7z", _DIGEST, tmp_path)

        assert archive.read_bytes() == _ARCHIVE

    def test_an_archive_whose_digest_does_not_match_stops_the_fetch_since_a_rebuilt_tag_and_a_tampered_file_cannot_be_told_apart(self, tmp_path: Path,
                                                                    monkeypatch):
        monkeypatch.setattr(fetch_libmpv.urllib.request, "urlretrieve",
                            lambda _url, target: Path(target).write_bytes(b"something else"))

        with pytest.raises(SystemExit, match="does not match the digest"):
            fetch_libmpv.download("https://example.invalid/mpv.7z", _DIGEST, tmp_path)

    def test_an_asset_nothing_publishes_a_digest_for_is_taken_and_said_so(
            self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setattr(fetch_libmpv.urllib.request, "urlretrieve",
                            lambda _url, target: Path(target).write_bytes(_ARCHIVE))

        fetch_libmpv.download("https://example.invalid/mpv.7z", "", tmp_path)

        assert "unverified" in capsys.readouterr().err


class TestWhenThePinExpires:
    def test_a_live_pin_is_used_and_nothing_is_resolved(self, monkeypatch):
        monkeypatch.setattr(fetch_libmpv, "_reachable", lambda _url: True)
        monkeypatch.setattr(fetch_libmpv, "newest_asset", _never_called)
        pinned = {"source": "someone/mpv-builds", "fallback": "other/mpv-builds",
                  "tag": "2026-01-02-abcdef", "asset": "mpv.7z", "sha256": _DIGEST}

        url, digest = fetch_libmpv.resolve(pinned)

        assert url.endswith("2026-01-02-abcdef/mpv.7z")
        assert digest == _DIGEST

    def test_a_retired_tag_falls_back_loudly_since_upstream_drops_releases_within_a_month_and_a_gate_with_no_engine_blocks_every_change(self, monkeypatch, capsys):
        monkeypatch.setattr(fetch_libmpv, "_reachable", lambda _url: False)
        monkeypatch.setattr(fetch_libmpv, "newest_asset",
                            lambda repository: ("https://example.invalid/newest.7z", ""))
        pinned = {"source": "someone/mpv-builds", "fallback": "other/mpv-builds",
                  "tag": "2026-01-02-abcdef", "asset": "mpv.7z", "sha256": _DIGEST}

        url, digest = fetch_libmpv.resolve(pinned)

        assert url == "https://example.invalid/newest.7z"
        assert digest == ""
        warning = capsys.readouterr().err
        assert "libmpv.lock" in warning
        assert "Bump the pin" in warning

    def test_the_fallback_feed_answers_when_the_first_has_nothing(self, monkeypatch):
        monkeypatch.setattr(fetch_libmpv, "_reachable", lambda _url: False)
        asked = []

        def _newest(repository):
            asked.append(repository)
            return ("https://example.invalid/other.7z", "") if len(asked) > 1 else None

        monkeypatch.setattr(fetch_libmpv, "newest_asset", _newest)
        pinned = {"source": "someone/mpv-builds", "fallback": "other/mpv-builds",
                  "tag": "2026-01-02-abcdef", "asset": "mpv.7z", "sha256": _DIGEST}

        assert fetch_libmpv.resolve(pinned)[0] == "https://example.invalid/other.7z"
        assert asked == ["someone/mpv-builds", "other/mpv-builds"]

    def test_no_feed_answering_is_a_failure_rather_than_an_empty_vendor(self, monkeypatch):
        monkeypatch.setattr(fetch_libmpv, "_reachable", lambda _url: False)
        monkeypatch.setattr(fetch_libmpv, "newest_asset", lambda _repository: None)
        pinned = {"source": "someone/mpv-builds", "fallback": "other/mpv-builds",
                  "tag": "2026-01-02-abcdef", "asset": "mpv.7z", "sha256": _DIGEST}

        with pytest.raises(SystemExit, match="could not resolve"):
            fetch_libmpv.resolve(pinned)

    def test_the_releases_are_asked_for_with_the_token_the_runner_holds_since_github_rations_unauthenticated_requests_by_address(self, monkeypatch):
        sent = []

        class _Answer:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return b"[]"

        def _urlopen(request, timeout):
            sent.append(request)
            return _Answer()

        monkeypatch.setenv("GH_TOKEN", "an-invented-token")
        monkeypatch.setattr(fetch_libmpv.urllib.request, "urlopen", _urlopen)

        assert fetch_libmpv._releases("someone/mpv-builds") == []
        assert sent[0].get_header("Authorization") == "Bearer an-invented-token"


def test_the_dll_lands_where_the_loader_looks_one_place_for_the_machine_since_an_installed_copy_of_the_package_has_no_vendor_folder_beside_it():

    assert fetch_libmpv.dll_path().parent == machine_libmpv_dir()


def test_a_wrong_user_folder_variable_moves_neither(monkeypatch, tmp_path):
    before = fetch_libmpv.dll_path()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert fetch_libmpv.dll_path() == before


def test_this_repos_gate_fetches_the_pin_itself_since_a_developers_machine_already_has_the_dll_and_would_never_try_it():
    gate = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "merge-gate.yml").read_text(encoding="utf-8")

    assert "tools/fetch_libmpv.py" in gate

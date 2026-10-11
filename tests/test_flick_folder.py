"""The flicks folder: the scan, its orders, and the condemned pile beside it."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from app_support import flick_folder as shared_layout

from funestra_core.flick_folder import (
    flat_flicks_in,
    move_flick_to_weird,
    scan_flicks,
    vr_flicks_in,
    weird_dir_for_flicks_folder,
    weird_folder_for,
)

# ---------------------------------------------------------------------------
# scan_flicks
# ---------------------------------------------------------------------------

class TestScanFlicks:
    def test_finds_mp4_files(self, tmp_path: Path):
        (tmp_path / "a.mp4").touch()
        (tmp_path / "b.mp4").touch()
        result = scan_flicks(tmp_path, shuffle_on_load=False)
        names = {p.name for p in result}
        assert names == {"a.mp4", "b.mp4"}

    def test_finds_mixed_extensions(self, tmp_path: Path):
        (tmp_path / "movie.mkv").touch()
        (tmp_path / "flick.mp4").touch()
        result = scan_flicks(tmp_path, shuffle_on_load=False)
        assert len(result) == 2

    def test_ignores_non_video_files(self, tmp_path: Path):
        (tmp_path / "video.mp4").touch()
        (tmp_path / "notes.txt").touch()
        (tmp_path / "image.jpg").touch()
        result = scan_flicks(tmp_path, shuffle_on_load=False)
        assert len(result) == 1
        assert result[0].name == "video.mp4"

    def test_ignores_subdirectories(self, tmp_path: Path):
        (tmp_path / "video.mp4").touch()
        (tmp_path / "subdir").mkdir()
        result = scan_flicks(tmp_path, shuffle_on_load=False)
        assert len(result) == 1

    def test_finds_the_flicks_in_the_folders_inside_it(self, tmp_path: Path):
        for place in ("AI/a.mp4", "non_AI/b.mp4", "c.mp4"):
            (tmp_path / place).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / place).touch()

        result = scan_flicks(tmp_path, shuffle_on_load=False)

        assert sorted(result) == [tmp_path / "AI" / "a.mp4", tmp_path / "c.mp4",
                                  tmp_path / "non_AI" / "b.mp4"]

    def test_raises_when_folder_empty(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="No video flicks found"):
            scan_flicks(tmp_path)

    def test_raises_when_only_non_video_files(self, tmp_path: Path):
        (tmp_path / "readme.txt").touch()
        with pytest.raises(RuntimeError, match="No video flicks found"):
            scan_flicks(tmp_path)

    def test_extension_matching_is_case_insensitive(self, tmp_path: Path):
        (tmp_path / "flick.MP4").touch()
        (tmp_path / "other.MKV").touch()
        result = scan_flicks(tmp_path, shuffle_on_load=False)
        assert len(result) == 2

    def test_shuffle_off_gives_deterministic_order(self, tmp_path: Path):
        for name in ["c.mp4", "a.mp4", "b.mp4"]:
            (tmp_path / name).touch()
        r1 = scan_flicks(tmp_path, shuffle_on_load=False)
        r2 = scan_flicks(tmp_path, shuffle_on_load=False)
        assert r1 == r2

    def test_shuffling_leaves_out_none_of_the_flicks(self, tmp_path: Path):
        for name in ["x.mp4", "y.mp4", "z.mp4"]:
            (tmp_path / name).touch()
        result = scan_flicks(tmp_path, shuffle_on_load=True)
        assert len(result) == 3
        assert {p.name for p in result} == {"x.mp4", "y.mp4", "z.mp4"}


class TestTheShuffleItself:
    """It was a call on a module-global generator with no seed, so the only
    thing a test could say about it was that nothing went missing.  It is a
    dependency now, and these say what it is actually asked to do."""

    @staticmethod
    def _folder(tmp_path: Path) -> Path:
        for name in ("alpha.mp4", "beta.mp4", "gamma.mp4"):
            (tmp_path / name).touch()
        return tmp_path

    def test_the_order_it_leaves_the_list_in_is_the_order_returned(self, tmp_path: Path):
        """It shuffles in place, so a caller that ignored the mutation and
        returned the list it built would come back unshuffled."""
        def _z_to_a(files):
            files.sort(key=lambda path: path.name, reverse=True)

        result = scan_flicks(self._folder(tmp_path), shuffle_on_load=True,
                            shuffle=_z_to_a)

        assert [path.name for path in result] == [
            "gamma.mp4", "beta.mp4", "alpha.mp4"]

    def test_it_is_asked_once_and_given_every_flick(self, tmp_path: Path):
        asked = []

        scan_flicks(self._folder(tmp_path), shuffle_on_load=True,
                   shuffle=lambda files: asked.append(list(files)))

        assert len(asked) == 1
        assert {path.name for path in asked[0]} == {
            "alpha.mp4", "beta.mp4", "gamma.mp4"}

    def test_it_is_not_asked_when_the_config_says_not_to(self, tmp_path: Path):
        asked = []

        scan_flicks(self._folder(tmp_path), shuffle_on_load=False,
                   shuffle=asked.append)

        assert asked == []

    def test_it_is_not_asked_for_an_order_that_was_named_outright(self, tmp_path: Path):
        """Latest is an order; shuffling it would undo it."""
        asked = []

        scan_flicks(self._folder(tmp_path), shuffle_on_load=True, recent=True,
                   shuffle=asked.append)

        assert asked == []


class TestLatestOrder:
    """Newest-first — the order "latest" asks for, so a flick that landed in the
    folder minutes ago heads the sequence instead of sitting somewhere in it."""

    @staticmethod
    def _aged(tmp_path: Path, name: str, mtime: float) -> Path:
        path = tmp_path / name
        path.touch()
        os.utime(path, (mtime, mtime))
        return path

    def test_newest_flick_comes_first(self, tmp_path: Path):
        self._aged(tmp_path, "old.mp4", 1_000)
        self._aged(tmp_path, "newest.mp4", 3_000)
        self._aged(tmp_path, "middle.mp4", 2_000)

        result = scan_flicks(tmp_path, recent=True)

        assert [path.name for path in result] == ["newest.mp4", "middle.mp4", "old.mp4"]

    def test_the_named_order_outranks_the_shuffle(self, tmp_path: Path):
        """Shuffling an order that was asked for outright would undo it, and
        ``shuffle_on_load`` is a config default rather than this session's word."""
        self._aged(tmp_path, "old.mp4", 1_000)
        self._aged(tmp_path, "new.mp4", 2_000)

        result = scan_flicks(tmp_path, shuffle_on_load=True, recent=True)

        assert [path.name for path in result] == ["new.mp4", "old.mp4"]



def test_the_flicks_folders_layout_is_the_one_every_app_reads_from_app_support():
    assert (flat_flicks_in, vr_flicks_in, weird_dir_for_flicks_folder) == (
        shared_layout.flat_flicks_in,
        shared_layout.vr_flicks_in,
        shared_layout.weird_dir_for_flicks_folder,
    )


def test_a_flick_goes_to_its_own_place_in_the_weird_pile():
    flicks = Path("C:/videos/genau/flicks")

    assert weird_folder_for(flicks / "2D" / "AI" / "loop one.mp4", flicks) == Path(
        "C:/videos/genau/weird/2D/AI"
    )


def test_a_flick_from_outside_the_flicks_folder_goes_to_the_top_of_the_weird_pile():
    flicks = Path("C:/videos/genau/flicks")

    assert weird_folder_for(Path("D:/elsewhere/loop one.mp4"), flicks) == Path(
        "C:/videos/genau/weird"
    )


def test_move_takes_the_flick_out_of_rotation(tmp_path: Path):
    flicks = tmp_path / "flicks"
    flicks.mkdir()
    flick = flicks / "odd.mp4"
    flick.write_bytes(b"flick")
    weird = tmp_path / "weird"

    landed = move_flick_to_weird(flick, weird)

    assert landed == weird / "odd.mp4"
    assert landed.read_bytes() == b"flick"
    assert not flick.exists()


def test_move_creates_the_weird_dir_on_first_use(tmp_path: Path):
    flick = tmp_path / "odd.mp4"
    flick.write_bytes(b"flick")
    weird = tmp_path / "weird"
    assert not weird.exists()

    move_flick_to_weird(flick, weird)

    assert weird.is_dir()


def test_a_flick_already_gone_is_not_an_error(tmp_path: Path):
    """Two WEIRD verbs can race the same flick; the second must not crash Genau."""
    weird = tmp_path / "weird"

    assert move_flick_to_weird(tmp_path / "missing.mp4", weird) is None


class TestSeveralFoldersBrowsedAsOne:
    """The headset browses its VR flicks and the desktop's flat flicks together,
    the way the main rotation joins the VR library to the desktop's."""

    @staticmethod
    def _two_folders(tmp_path: Path) -> tuple[Path, Path]:
        vr, flat = tmp_path / "vr_flicks", tmp_path / "flicks"
        vr.mkdir()
        flat.mkdir()
        for name in ("alpha_180.mp4", "beta_180.mp4"):
            (vr / name).touch()
        for name in ("gamma.mp4", "delta.mp4"):
            (flat / name).touch()
        return vr, flat

    def test_every_folders_flicks_are_in_the_sequence(self, tmp_path: Path):
        vr, flat = self._two_folders(tmp_path)

        result = scan_flicks((vr, flat), shuffle_on_load=False)

        assert {p.name for p in result} == {"alpha_180.mp4", "beta_180.mp4", "gamma.mp4", "delta.mp4"}
        assert [p.parent.name for p in result] == ["vr_flicks", "vr_flicks", "flicks", "flicks"]

    def test_latest_orders_them_together(self, tmp_path: Path):
        vr, flat = self._two_folders(tmp_path)
        os.utime(vr / "alpha_180.mp4", (1_000, 1_000))
        os.utime(flat / "gamma.mp4", (3_000, 3_000))
        os.utime(vr / "beta_180.mp4", (2_000, 2_000))
        os.utime(flat / "delta.mp4", (500, 500))

        result = scan_flicks((vr, flat), recent=True)

        assert [p.name for p in result] == ["gamma.mp4", "beta_180.mp4", "alpha_180.mp4", "delta.mp4"]

    def test_the_shuffle_is_asked_once_over_all_of_them(self, tmp_path: Path):
        vr, flat = self._two_folders(tmp_path)
        asked = []

        scan_flicks((vr, flat), shuffle_on_load=True, shuffle=lambda files: asked.append(list(files)))

        assert len(asked) == 1
        assert len(asked[0]) == 4

    def test_a_folder_with_nothing_in_it_is_not_an_error(self, tmp_path: Path):
        vr, flat = self._two_folders(tmp_path)
        empty = tmp_path / "empty"
        empty.mkdir()

        result = scan_flicks((vr, empty, flat), shuffle_on_load=False)

        assert len(result) == 4

    def test_no_flicks_anywhere_names_every_folder(self, tmp_path: Path):
        one, two = tmp_path / "one", tmp_path / "two"
        one.mkdir()
        two.mkdir()

        with pytest.raises(RuntimeError, match=r"one.*two"):
            scan_flicks((one, two))

    def test_one_folder_still_reads_as_one(self, tmp_path: Path):
        vr, _flat = self._two_folders(tmp_path)

        assert scan_flicks(vr, shuffle_on_load=False) == scan_flicks((vr,), shuffle_on_load=False)

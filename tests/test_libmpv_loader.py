from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import funestra
from funestra import mpv_engine
from funestra.libmpv_loader import (
    add_libmpv_to_path,
    libmpv_dirs,
    machine_libmpv_dir,
    user_folder,
)

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the known-folder API is Windows'")


def test_a_checkouts_own_vendor_dir_is_looked_in_first():

    assert libmpv_dirs()[0] == Path(funestra.__file__).resolve().parent.parent / "vendor"


def test_the_machine_wide_copy_is_looked_in_after_it():
    assert libmpv_dirs()[1] == machine_libmpv_dir()


def test_the_machine_wide_copy_is_in_the_user_folder_and_not_under_app_data():
    """AppData's Local, Roaming and LocalLow are private per packaged app -- the
    Claude app every agent's shell runs inside -- so a DLL an agent fetches there
    is found by every suite and by nothing the user launches (measured 2026-09-26)."""
    assert machine_libmpv_dir() == user_folder() / ".haglio" / "libmpv"
    assert "AppData" not in machine_libmpv_dir().parts


@windows_only
def test_a_wrong_user_folder_variable_does_not_move_the_engine(monkeypatch, tmp_path: Path):
    """The Funestras Fun Time launches inherited a folder variable that was not the
    real folder, looked for the engine there, and every one of them died on its
    first launch; the folder Windows keeps for the user is the one to ask."""
    real = machine_libmpv_dir()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert machine_libmpv_dir() == real
    assert tmp_path not in machine_libmpv_dir().parents


@windows_only
def test_no_user_folder_variable_at_all_does_not_move_it_either(monkeypatch):
    real = machine_libmpv_dir()
    monkeypatch.delenv("USERPROFILE", raising=False)

    assert machine_libmpv_dir() == real


def test_both_go_on_path_ahead_of_everything_in_that_order(monkeypatch):
    monkeypatch.setenv("PATH", r"C:\existing")

    add_libmpv_to_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[:2] == [str(d) for d in libmpv_dirs()]
    assert r"C:\existing" in parts


def test_putting_them_on_path_twice_adds_nothing(monkeypatch):
    monkeypatch.setenv("PATH", r"C:\existing")

    add_libmpv_to_path()
    add_libmpv_to_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert all(parts.count(str(d)) == 1 for d in libmpv_dirs())


# --- the import, and the PATH another thread can take out from under it -----

def test_the_engine_is_imported_once_the_folder_is_on_the_path():
    asked = []

    def load(name):
        asked.append(name)
        return "the engine"

    assert mpv_engine._import_the_engine(load) == "the engine"
    assert asked == ["mpv"]


def test_a_path_taken_out_from_under_it_is_put_back_and_the_import_retried():
    """PATH is shared, and other libraries prepend themselves to it with a read
    then a write -- vosk does exactly that, on the thread a voice app listens
    on. A write built from a read taken before ours puts the folder back out,
    and the engine is looked for by walking PATH."""
    tries = []

    def load(name):
        tries.append(name)
        if len(tries) < 3:
            raise OSError("Cannot find mpv-1.dll, mpv-2.dll or libmpv-2.dll")
        return "the engine"

    assert mpv_engine._import_the_engine(load) == "the engine"
    assert len(tries) == 3


def test_an_engine_that_is_really_not_there_says_where_it_looked():
    def load(name):
        raise OSError("Cannot find mpv-1.dll, mpv-2.dll or libmpv-2.dll")

    with pytest.raises(OSError, match="PATH starts") as refused:
        mpv_engine._import_the_engine(load, tries=2)

    for folder in libmpv_dirs():
        assert str(folder) in str(refused.value)


def test_a_folder_that_cannot_be_looked_in_at_all_says_what_it_answered(monkeypatch):
    """The other half of the same question: a folder that holds the DLL while
    the import cannot find it means PATH was rewritten under us; one that
    cannot be read at all names the error instead."""
    class Refuses(type(Path("."))):
        def is_file(self):
            raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr(mpv_engine, "libmpv_dirs", lambda: [Refuses("C:/nowhere")])

    said = mpv_engine._where_it_looked()

    assert "could not be looked in" in said and "Access is denied" in said

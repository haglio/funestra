from __future__ import annotations

from types import SimpleNamespace

import pygame
from PIL import Image

from funestra.program.window import (
    claim_the_sessions_taskbar_identity,
    replace_pygames_logo_with,
    wear_the_sessions_taskbar_button,
)


class TestAFunestraTakesTheIdentityItIsGiven:
    def test_told_one_it_takes_it(self):
        claimed = []

        claim_the_sessions_taskbar_identity("Example.App", claim=claimed.append)

        assert claimed == ["Example.App"]

    def test_told_none_it_claims_nothing(self):
        claimed = []

        claim_the_sessions_taskbar_identity(None, claim=claimed.append)

        assert claimed == []

    def test_a_refusal_never_stops_the_funestra_starting(self):
        def refuse(_identity):
            raise OSError("refused")

        claim_the_sessions_taskbar_identity("Example.App", claim=refuse)


class TestAFunestrasWindowWearsTheSessionsButton:
    def _wear(self, identity, *, dress, described=lambda _identity: None):
        wear_the_sessions_taskbar_button(4242, identity, dress=dress, described=described)

    def test_a_preview_window_wears_the_name_and_icon_registered_for_its_button(self):
        registered = object()
        dressed = []

        self._wear("Example.App.Preview", dress=lambda *worn: dressed.append(worn),
                   described={"Example.App.Preview": registered}.get)

        assert dressed == [(4242, "Example.App.Preview", registered)]

    def test_told_no_identity_it_leaves_the_window_as_it_is(self):
        dressed = []

        self._wear(None, dress=lambda *worn: dressed.append(worn))

        assert dressed == []

    def test_a_refusal_never_stops_the_funestra_starting(self):
        def refuse(*_worn):
            raise OSError("refused")

        self._wear("Example.App", dress=refuse)


def test_an_icon_file_loads_as_the_window_icon(tmp_path):
    icon = tmp_path / "made_up.ico"
    Image.new("RGBA", (16, 16), (200, 30, 30, 255)).save(icon)
    worn = []

    replace_pygames_logo_with(
        SimpleNamespace(display=SimpleNamespace(set_icon=worn.append), image=pygame.image), icon)

    assert len(worn) == 1


def test_a_missing_icon_file_leaves_the_window_its_own(tmp_path):
    worn = []

    replace_pygames_logo_with(
        SimpleNamespace(display=SimpleNamespace(set_icon=worn.append), image=pygame.image),
        tmp_path / "nowhere.ico")

    assert worn == []

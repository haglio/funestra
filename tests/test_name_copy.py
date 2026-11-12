from __future__ import annotations

import base64

from funestra.name_copy import copy_to_clipboard, copy_while_the_funestra_plays_on


def _asked_to_copy(argv: list[str]) -> str:
    spelled = argv[-1].split("FromBase64String('")[1].split("'")[0]
    return base64.b64decode(spelled).decode("utf-8")


def test_the_name_reaches_windows_clipboard_whatever_letters_it_holds():
    asked = []

    copy_to_clipboard("vidéo 'one'", run=lambda argv, **_how: asked.append(argv))

    assert [_asked_to_copy(argv) for argv in asked] == ["vidéo 'one'"]


def test_the_funestra_never_waits_for_windows_to_take_the_name():
    asked = []

    copy_while_the_funestra_plays_on("video one",
                                     run=lambda argv, **_how: asked.append(argv)).join()

    assert [_asked_to_copy(argv) for argv in asked] == ["video one"]

"""A Funestra's declared rows, made up for the tests that lay them out, draw them
and press them: the shape a source's bar takes, every state set here."""
from __future__ import annotations

from funestra.hud_button import FIT_THE_WORD, Button
from funestra.hud_icons import FMODE_ICON, MINIMIZE_ICON, shared_icon


def bar(funestra: str = "portrait", *, locked: bool = False, favorites: bool = False,
         enhanced: bool | None = None, newest: bool | None = None,
         minimize: bool = True) -> tuple[Button, ...]:
    """Stepping, the video on screen, the browse -- the enhanced switch and the
    order pair only where asked for -- and the window."""
    def own(name: str, face: str, **state) -> Button:
        return Button(f"{funestra}_{name}", face, f"{name} tip", **state)

    return (
        own("prev", "⏮"),
        own("next", "⏭"),
        own("lock", "🔒", lit=locked, favorite=True, group_break=True),
        own("trash", shared_icon("trash"), danger=True),
        own("fmode", FMODE_ICON, lit=favorites, favorite=True),
        *(() if enhanced is None else (
            own("enhanced", shared_icon("enhance_filter"), lit=enhanced,
                enhanced=True, group_break=True),)),
        own("reset", shared_icon("reset"), group_break=enhanced is None),
        *(() if newest is None else (
            own("shuffle", shared_icon("shuffle"), lit=not newest, group_break=True),
            own("latest", shared_icon("latest"), lit=newest))),
        *((own("minimize", MINIMIZE_ICON, group_break=True),) if minimize else ()),
    )


def funestra_rows(funestra: str = "portrait", *, mode: str = "",
                **state) -> tuple[tuple[Button, ...], ...]:
    """*Funestra*'s bar, under the session's mode pair -- with minimize moved up
    beside it -- where a *mode* is named."""
    if not mode:
        return (bar(funestra, **state),)
    pair = (
        Button("satellites_kino_activate", "Kino", "Kino mode",
               width=FIT_THE_WORD, lit=mode == "kino"),
        Button("origenerator_activate", "Origenerator", "Origenerator mode",
               width=FIT_THE_WORD, lit=mode == "origenerator"),
        Button(f"{funestra}_minimize", MINIMIZE_ICON, "minimize tip", group_break=True),
    )
    return pair, bar(funestra, minimize=False, **state)


def short_name(button: Button) -> str:
    """What a Funestra's button is for, the Funestra prefix dropped: "lock",
    "fmode"; a mode button keeps its whole command, naming no Funestra."""
    for prefix in ("portrait_", "landscape_"):
        if button.command.startswith(prefix):
            return button.command[len(prefix):]
    return button.command

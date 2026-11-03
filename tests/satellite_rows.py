from __future__ import annotations

from dataclasses import dataclass

from funestra.hud_button import FIT_THE_WORD, Button
from funestra.hud_icons import FMODE_ICON, MINIMIZE_ICON, shared_icon


@dataclass(frozen=True)
class _Lit:
    locked: bool = False
    favorites: bool = False
    enhanced: bool | None = None
    newest: bool | None = None


def bar(funestra: str = "portrait", *, minimize: bool = True, **state) -> tuple[Button, ...]:
    lit = _Lit(**state)

    def own(name: str, face: str, **state) -> Button:
        return Button(f"{funestra}_{name}", face, f"{name} tip", **state)

    return (
        own("prev", "⏮"),
        own("next", "⏭"),
        own("lock", "🔒", lit=lit.locked, favorite=True, group_break=True),
        own("trash", shared_icon("trash"), danger=True),
        own("fmode", FMODE_ICON, lit=lit.favorites, favorite=True),
        *(() if lit.enhanced is None else (
            own("enhanced", shared_icon("enhance_filter"), lit=lit.enhanced,
                enhanced=True, group_break=True),)),
        own("reset", shared_icon("reset"), group_break=lit.enhanced is None),
        *(() if lit.newest is None else (
            own("shuffle", shared_icon("shuffle"), lit=not lit.newest, group_break=True),
            own("latest", shared_icon("latest"), lit=lit.newest))),
        *((own("minimize", MINIMIZE_ICON, group_break=True),) if minimize else ()),
    )


def funestra_rows(funestra: str = "portrait", *, mode: str = "",
                **state) -> tuple[tuple[Button, ...], ...]:
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
    for prefix in ("portrait_", "landscape_"):
        if button.command.startswith(prefix):
            return button.command[len(prefix):]
    return button.command

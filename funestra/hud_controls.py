from __future__ import annotations

from .funestra_controls import SEEK_STEP_MS
from .funestra_verbs import SEEK_BACK, SEEK_FWD
from .hud_button import FIT_THE_WORD, Button
from .hud_icons import (
    BACK_ICON,
    FMODE_ICON,
    FORWARD_ICON,
    LOCK_ICON,
    NEXT_ICON,
    PREVIOUS_ICON,
    shared_icon,
)
from .hud_title import F_MODE_LABEL, LATEST_LABEL, PLAYBACK_SPEED_LABEL, SHUFFLE_LABEL
from .main_hud import ROW_LABEL_W, VALUE_W
from .status import FunestraStatus

TRASH_ICON = shared_icon("trash")
RESET_ICON = shared_icon("reset")
SHUFFLE_ICON = shared_icon("shuffle")
LATEST_ICON = shared_icon("latest")
VERSIONS_ICON = shared_icon("versions")
FUNSCRIPT_JUMP_ICON = shared_icon("funscript_jump")

NONE_FOR_THIS_ONE = " (none for this one)"
AN_IMAGE = "this is an image"
TRASH_TOOLTIP = "Unfavorite it — or send it to Trash when it is not a favorite"
RESET_PUTS_BACK_THE_SPEED = "normal speed"
RESET_TOOLTIP = (f"Reset — no filter, no lock, no loop, no F-Mode, {RESET_PUTS_BACK_THE_SPEED}, "
                 "shuffled from the top")


def longer_than_a_step(duration_ms: float) -> bool:
    return duration_ms > SEEK_STEP_MS


def too_short_to_step(noun: str) -> str:
    return f"this {noun} is 10s or shorter"


def too_near_the_start_to_step_back(noun: str) -> str:
    return f"less than 10s into this {noun}"


def too_near_the_end_to_step_forward(noun: str) -> str:
    return f"less than 10s left in this {noun}"


def why_it_cannot_step(verb: str, status: FunestraStatus, noun: str) -> str | None:
    if status.image:
        return AN_IMAGE
    if not longer_than_a_step(status.duration_ms):
        return too_short_to_step(noun)
    if verb == SEEK_BACK and status.position_ms < SEEK_STEP_MS:
        return too_near_the_start_to_step_back(noun)
    if verb == SEEK_FWD and not longer_than_a_step(status.duration_ms - status.position_ms):
        return too_near_the_end_to_step_forward(noun)
    return None


def transport(funestra: str, *, noun: str, longer_than_a_step: bool,
              image: bool = False) -> tuple[Button, ...]:
    cannot_step = AN_IMAGE if image else "" if longer_than_a_step else too_short_to_step(noun)
    reason = f" ({cannot_step})" if cannot_step else ""
    return (
        previous_button(f"{funestra}_prev", noun=noun),
        Button(f"{funestra}_nudge_prev", BACK_ICON, f"Back 10s{reason}", dim=bool(cannot_step)),
        Button(f"{funestra}_nudge_next", FORWARD_ICON, f"Forward 10s{reason}",
               dim=bool(cannot_step)),
        next_button(f"{funestra}_next", noun=noun),
    )


def previous_button(command: str, *, noun: str) -> Button:
    return Button(command, PREVIOUS_ICON, f"Previous {noun}")


def next_button(command: str, *, noun: str) -> Button:
    return Button(command, NEXT_ICON, f"Next {noun}")


def funscript_jump_button(command: str, *, noun: str, has_osr2: bool,
                          has_funscript: bool) -> Button:
    missing = " and ".join(why for why, lacking in (
        ("this Funestra doesn't have the OSR2", not has_osr2),
        (f"this {noun} has no funscript", not has_funscript)) if lacking)
    return Button(
        command, FUNSCRIPT_JUMP_ICON,
        f"Skip ahead to where this {noun}'s scripting starts up again"
        + (f" ({missing})" if missing else ""),
        dim=bool(missing))


def lock_tooltip(locked: bool, noun: str) -> str:
    if locked:
        return f"Locked — this {noun} repeats; press to play on through the playlist"
    return f"Unlocked — plays on through the playlist; press to hold this {noun}"


def lock_button(funestra: str, *, locked: bool, tooltip: str) -> Button:
    return Button(f"{funestra}_lock", LOCK_ICON, tooltip, lit=locked, favorite=True,
                  group_break=True)


def trash_button(funestra: str) -> Button:
    return trash_button_under(f"{funestra}_trash", TRASH_TOOLTIP)


def trash_button_under(command: str, tooltip: str) -> Button:
    return Button(command, TRASH_ICON, tooltip, danger=True)


def favorites_only_tooltip() -> str:
    return f"{F_MODE_LABEL} — browse only the favorites on this Funestra"


def fmode_button(funestra: str, tooltip: str, *, lit: bool) -> Button:
    return Button(f"{funestra}_fmode", FMODE_ICON, tooltip, lit=lit, favorite=True)


def reset_button(funestra: str, *, nothing_to_reset: bool, tooltip: str,
                 group_break: bool = True) -> Button:
    return Button(f"{funestra}_reset", RESET_ICON, tooltip, dim=nothing_to_reset,
                  group_break=group_break)


def lit_or_remembered(on: bool, remembered: bool) -> dict:
    return {"lit": on and not remembered, "remembered": on and remembered}


def browse_order_buttons(funestra: str, *, latest: bool | None,
                         remembered: bool = False) -> tuple[Button, ...]:
    if latest is None:
        return ()
    return (
        Button(f"{funestra}_shuffle", SHUFFLE_ICON, f"{SHUFFLE_LABEL} — reshuffle what plays",
               group_break=True, **lit_or_remembered(not latest, remembered)),
        Button(f"{funestra}_latest", LATEST_ICON, f"{LATEST_LABEL} — reload it newest-first",
               **lit_or_remembered(latest, remembered)),
    )


PLAYBACK_SPEED = "playback_speed"


def playback_speed_buttons(funestra: str, *, leads_its_row: bool = True) -> tuple[Button, ...]:
    return (
        Button("", PLAYBACK_SPEED_LABEL, "", width=ROW_LABEL_W if leads_its_row else FIT_THE_WORD,
               group_break=not leads_its_row),
        Button(f"{funestra}_speed_down", shared_icon("minus"), "Play the video slower",
               group_break=True),
        Button("", "", "", width=VALUE_W, host_value=PLAYBACK_SPEED),
        Button(f"{funestra}_speed_up", shared_icon("plus"), "Play the video faster"),
    )


def versions_button(command: str, *, noun: str, has_other_versions: bool) -> Button:
    return Button(
        command, VERSIONS_ICON,
        f"Another version of this {noun}" + ("" if has_other_versions else NONE_FOR_THIS_ONE),
        dim=not has_other_versions, group_break=True)

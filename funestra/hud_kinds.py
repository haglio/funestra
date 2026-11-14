from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from shared_ui.spacing import BUTTON_WORD_W

from .hud_button import FIT_THE_WORD, Button
from .hud_controls import (
    RESET_PUTS_BACK_THE_SPEED,
    RESET_TOOLTIP,
    browse_order_buttons,
    favorites_only_tooltip,
    fmode_button,
    funscript_jump_button,
    lock_button,
    lock_tooltip,
    next_button,
    playback_speed_buttons,
    previous_button,
    reset_button,
    transport,
    trash_button,
    trash_button_under,
    versions_button,
)
from .hud_icons import MINIMIZE_ICON, shared_icon
from .hud_title import F_MODE_LABEL
from .inclusion_pair import (
    BOTH,
    LENGTH,
    ORIENTATION,
    PROJECTION,
    Included,
    InclusionPair,
    enhancement_pair,
    lengths_included,
    media_pair,
)
from .main_hud import ROW_LABEL_W, VALUE_W
from .modes import LengthMode, MainMode


class HudKind(StrEnum):
    MAIN = "main"
    SATELLITE = "satellite"
    SLIDESHOW = "slideshow"


class Shows(StrEnum):
    KINO = "kino"
    GENAU = "genau"
    SLIDES = "slides"


EVERY_SHOW = frozenset(Shows)

SNIPPET_RECORDING = "recording"
SNIPPET_REPEATING = "repeating"


@dataclass(frozen=True, kw_only=True)
class HudFacts:
    funestra: str = "main"
    main_mode: MainMode = MainMode.KINO
    locked: bool = False
    f_mode: bool = False
    latest: bool | None = None
    longer_than_a_step: bool = False
    image: bool = False
    has_other_versions: bool = False
    has_osr2: bool = False
    has_funscript: bool = False
    nothing_to_reset: bool = False
    in_vr: bool = False
    crowned: bool = False
    snippet: str = ""
    plays_vr: bool | None = None
    plays_flat: bool | None = None
    plays_portrait: bool = True
    plays_landscape: bool = True
    pace_s: int = 0
    length_mode: LengthMode = LengthMode.MIXED
    compilation: str = ""
    has_compilation: bool = False
    jump_to: str = ""
    flipped: bool = False
    flick_one: str = ""
    flick_many: str = ""
    media: Included = BOTH
    enhancement: Included = BOTH
    hosted: bool = False
    clip_seconds: int | None = None


@dataclass(frozen=True)
class HudControl:
    name: str
    on: frozenset[Shows]
    buttons: Callable[[HudFacts, Shows], tuple[Button, ...]]


VIDEO = "video"
SLIDE = "slide"

OPEN_ICON = shared_icon("folder")
RECORD_ICON = shared_icon("disc")
SAVE_ICON = shared_icon("save")
LESS_ICON = shared_icon("minus")
MORE_ICON = shared_icon("plus")
COMPILATION_ICON = shared_icon("compilation")
CLIP_TO_SCENE_ICON = shared_icon("clip_to_scene")
SCENE_TO_CLIP_ICON = shared_icon("scene_to_clip")
FLIP_ENDS_ICON = shared_icon("flip_ends")
CROWN_ICON = shared_icon("crown")

SLIDESHOW_RESET_TOOLTIPS = {
    True: ("Reset — this shape's whole library back, with both filters off, "
           f"{RESET_PUTS_BACK_THE_SPEED}"),
    False: f"Reset — both filters off, {RESET_PUTS_BACK_THE_SPEED}, and this set from the top",
}

MODE_BUTTONS = (
    ("main_kino_activate", "Kino", MainMode.KINO),
    ("genau_activate", "Genau", MainMode.GENAU),
)


def shows_on(kind: HudKind, facts: HudFacts) -> Shows:
    if kind is not HudKind.MAIN:
        return Shows.SLIDES
    return Shows.KINO if facts.main_mode is MainMode.KINO else Shows.GENAU


def _prefix(facts: HudFacts, _shows: Shows) -> str:
    return facts.funestra


def _noun(facts: HudFacts, shows: Shows) -> str:
    return {Shows.KINO: VIDEO, Shows.GENAU: facts.flick_one, Shows.SLIDES: SLIDE}[shows]


def _transport(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.GENAU:
        return (previous_button("genau_prev_flick", noun=facts.flick_one),
                next_button("genau_next_flick", noun=facts.flick_one))
    return transport(facts.funestra, noun=_noun(facts, shows),
                     longer_than_a_step=facts.longer_than_a_step, image=facts.image)


def _funscript_jump(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    command = ("main_funestra_funscript_jump" if shows is Shows.KINO
               else f"{facts.funestra}_funscript_jump")
    return (funscript_jump_button(command, noun=_noun(facts, shows), has_osr2=facts.has_osr2,
                                  has_funscript=facts.has_funscript),)


def _lock(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.GENAU:
        one, pace = facts.flick_one, facts.pace_s
        tooltip = (f"Locked — this {one} repeats; press to move on every {pace}s" if facts.locked
                   else f"Unlocked — moving on every {pace}s; press to hold this {one}")
    else:
        tooltip = lock_tooltip(facts.locked, _noun(facts, shows))
    return (lock_button(facts.funestra, locked=facts.locked, tooltip=tooltip),)


def _slide_trash(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    return (trash_button(facts.funestra),)


def _fmode(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    tooltip = {
        Shows.KINO: f"{F_MODE_LABEL} — play only the well funscripted videos",
        Shows.GENAU: ("Showing the favorites only — press for all of them" if facts.f_mode
                      else f"{F_MODE_LABEL} — play only the favorites"),
        Shows.SLIDES: favorites_only_tooltip(),
    }[shows]
    return (fmode_button(facts.funestra, tooltip, lit=facts.f_mode),)


def _flip(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    one = facts.flick_one
    return (Button("genau_flip_ends", FLIP_ENDS_ICON,
                   f"Flipped — this {one} stays that way; press to put it back" if facts.flipped
                   else f"Flip this {one}, for one running opposite the OSR2 — it stays flipped",
                   lit=facts.flipped, group_break=True),)


def _flick_trash(_facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    return (trash_button_under("genau_trash_flick", "Send to Trash — move it out"),)


def _media(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    return media_pair(facts.funestra).buttons(facts.media, remembered=False, things="items")


def _enhancement(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    enhanced, originals = enhancement_pair(facts.funestra).buttons(
        facts.enhancement, remembered=False, things="items")
    return replace(enhanced, enhanced=True), originals


def _reset(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.SLIDES:
        return (reset_button(facts.funestra, nothing_to_reset=facts.nothing_to_reset,
                             tooltip=SLIDESHOW_RESET_TOOLTIPS[facts.hosted]),)
    return (reset_button(facts.funestra, nothing_to_reset=facts.nothing_to_reset,
                         tooltip=RESET_TOOLTIP),)


def _remembered(facts: HudFacts, shows: Shows) -> bool:
    return shows is Shows.KINO and bool(facts.compilation)


def _browse_order(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    return browse_order_buttons(facts.funestra, latest=facts.latest,
                                remembered=_remembered(facts, shows))


def _inclusions(facts: HudFacts, shows: Shows) -> tuple[tuple[InclusionPair, Included], ...]:
    shown = []
    if facts.plays_vr is not None and facts.plays_flat is not None:
        shown.append((PROJECTION, (bool(facts.plays_flat), bool(facts.plays_vr))))
    if shows is Shows.KINO:
        shown.append((LENGTH, lengths_included(facts.length_mode)))
    shown.append((ORIENTATION, (facts.plays_portrait, facts.plays_landscape)))
    return tuple(shown)


def _inclusion_buttons(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    things = "videos" if shows is Shows.KINO else facts.flick_many
    return tuple(button for pair, included in _inclusions(facts, shows)
                 for button in pair.buttons(included, remembered=_remembered(facts, shows),
                                            things=things))


def _compilation(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    inside = bool(facts.compilation)
    return (Button(
        "main_funestra_end_compilation" if inside else "main_funestra_compilation",
        COMPILATION_ICON,
        "Playing this compilation in order — press to leave it" if inside
        else "Play this video's compilation, in order"
        + ("" if facts.has_compilation else " (this one belongs to none)"),
        lit=inside, dim=not (inside or facts.has_compilation), group_break=True,
    ),)


def _clip_scene(facts: HudFacts, _shows: Shows) -> tuple[Button, ...]:
    to_scene = facts.jump_to == "scene"
    return (Button(
        "main_funestra_full_vid" if to_scene else "main_funestra_clip_jump",
        CLIP_TO_SCENE_ICON if to_scene else SCENE_TO_CLIP_ICON,
        "Play the full scene this clip came from" if to_scene
        else "Back to the clip taken from this scene" if facts.jump_to == "clip"
        else "Play the full scene this clip came from"
             " (no full scene in the library for this one)",
        dim=not facts.jump_to, group_break=True,
    ),)


def _versions(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    command = ("main_funestra_cycle_version" if shows is Shows.KINO
               else f"{facts.funestra}_cycle_version")
    return (versions_button(command, noun=_noun(facts, shows),
                            has_other_versions=facts.has_other_versions),)


_KINO, _GENAU, _SLIDES = (frozenset({shows}) for shows in Shows)

TRANSPORT_CONTROLS: tuple[HudControl, ...] = (
    HudControl("transport", EVERY_SHOW, _transport),
    HudControl("funscript_jump", _KINO | _SLIDES, _funscript_jump),
    HudControl("lock", EVERY_SHOW, _lock),
    HudControl("trash", _SLIDES, _slide_trash),
    HudControl("fmode", EVERY_SHOW, _fmode),
    HudControl("flip", _GENAU, _flip),
    HudControl("trash_flick", _GENAU, _flick_trash),
    HudControl("reset", _KINO | _SLIDES, _reset),
    HudControl("browse_order", EVERY_SHOW, _browse_order),
    HudControl("inclusions", _KINO | _GENAU, _inclusion_buttons),
    HudControl("media", _SLIDES, _media),
    HudControl("enhancement", _SLIDES, _enhancement),
    HudControl("compilation", _KINO, _compilation),
    HudControl("clip_scene", _KINO, _clip_scene),
    HudControl("versions", _KINO | _SLIDES, _versions),
)


def transport_row(facts: HudFacts, shows: Shows,
                  controls: tuple[HudControl, ...] = TRANSPORT_CONTROLS) -> tuple[Button, ...]:
    return tuple(button for control in controls if shows in control.on
                 for button in control.buttons(facts, shows))


def minimize_funestra_button(funestra: str) -> Button:
    return Button(f"{funestra}_minimize", MINIMIZE_ICON,
                  "Minimize this Funestra — bring it back from the taskbar", group_break=True)


_CROWN_TOOLTIPS = {
    "main": ("Crowned — a portrait video here takes most of the secondary monitor",
             "Give this Funestra the crown — its portrait videos take most of the secondary "
             "monitor"),
    "portrait": ("Crowned — this Funestra keeps most of the secondary monitor",
                 "Give this Funestra the crown — it keeps most of the secondary monitor, "
                 "whatever the Main Funestra shows"),
}


def crown_command(funestra: str) -> str:
    return f"{funestra}_crown"


def window_buttons(facts: HudFacts) -> tuple[Button, ...]:
    if facts.in_vr:
        return ()
    crown = _CROWN_TOOLTIPS.get(facts.funestra)
    return (minimize_funestra_button(facts.funestra), *(() if crown is None else (
        Button(crown_command(facts.funestra), CROWN_ICON, crown[0] if facts.crowned else crown[1],
               lit=facts.crowned),)))


def _file_controls(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.GENAU:
        return (Button("browse_library", OPEN_ICON, f"Browse the {facts.flick_many}",
                       group_break=True),)
    recording, repeating = facts.snippet == SNIPPET_RECORDING, facts.snippet == SNIPPET_REPEATING
    return (
        Button("browse_library", OPEN_ICON, "Browse the library", group_break=True),
        Button("main_funestra_record_tap", RECORD_ICON,
               "Stop recording — mark the snippet's out point" if recording
               else "Repeating the snippet — press to drop it" if repeating
               else "Record snippet",
               warn=recording, hold=repeating, group_break=True),
        Button("genaumacher_save", SAVE_ICON, "Save snippet"),
    )


def _mode_row(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    return (
        *(Button(command, label, "", width=BUTTON_WORD_W, lit=facts.main_mode is main_mode)
          for command, label, main_mode in MODE_BUTTONS),
        *window_buttons(facts),
        *_file_controls(facts, shows),
    )


def _flick_seconds_row(facts: HudFacts) -> tuple[Button, ...]:
    return (
        Button("", f"{facts.flick_one.capitalize()} seconds", "", width=ROW_LABEL_W),
        Button("genau_flick_seconds_down", LESS_ICON, "Move on sooner", group_break=True),
        Button("", "", "", width=VALUE_W, host_value="advance_interval"),
        Button("genau_flick_seconds_up", MORE_ICON, f"Leave each {facts.flick_one} longer"),
    )


def clip_seconds_row(shape: str, seconds: int) -> tuple[Button, ...]:
    return (
        Button("", "Clip seconds", "", width=FIT_THE_WORD),
        Button(f"{shape}_clip_seconds_down", LESS_ICON, "Move on sooner"),
        Button("", f"{seconds}s", "", width=VALUE_W),
        Button(f"{shape}_clip_seconds_up", MORE_ICON, "Leave each clip longer"),
        *playback_speed_buttons(shape, in_a_column_of_labels=False),
    )


def _slideshow_rows(facts: HudFacts,
                    controls: tuple[HudControl, ...]) -> tuple[tuple[Button, ...], ...]:
    pace = (() if facts.clip_seconds is None
            else (clip_seconds_row(facts.funestra, facts.clip_seconds),))
    return (transport_row(facts, Shows.SLIDES, controls), *pace)


def hud_rows(kind: HudKind, facts: HudFacts,
             controls: tuple[HudControl, ...] = TRANSPORT_CONTROLS) -> tuple[tuple[Button, ...], ...]:
    shows = shows_on(kind, facts)
    if kind is HudKind.MAIN:
        return (
            _mode_row(facts, shows),
            transport_row(facts, shows, controls),
            (playback_speed_buttons("main_funestra") if shows is Shows.KINO
             else _flick_seconds_row(facts)),
        )
    own = window_buttons(facts) if kind is HudKind.SATELLITE else ()
    return (*((own,) if own else ()), *_slideshow_rows(facts, controls))


def take_osr2_command(funestra: str) -> str:
    return f"{funestra}_take_osr2"


def osr2_button(funestra: str, *, has_it: bool) -> Button:
    if has_it:
        return Button(take_osr2_command(funestra), "OSR2",
                      "This Funestra has the OSR2 — it follows this Funestra's funscripts",
                      width=BUTTON_WORD_W, lit=True)
    return Button(take_osr2_command(funestra), "OSR2",
                  "Take over the OSR2 — it follows this Funestra's funscripts",
                  width=BUTTON_WORD_W)


def device_rows(kind: HudKind, facts: HudFacts) -> tuple[tuple[Button, ...], ...]:
    if kind is HudKind.SLIDESHOW:
        return ()
    return ((osr2_button(facts.funestra, has_it=facts.has_osr2),),)


def title_filters(facts: HudFacts) -> tuple[str, ...]:
    return tuple(word for pair, included in _inclusions(facts, shows_on(HudKind.MAIN, facts))
                 if (word := pair.title_word(included)))

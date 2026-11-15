from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from enum import Enum, IntEnum, StrEnum
from itertools import product

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
    playback_speed_buttons,
    reset_button,
    transport,
    trash_button,
    trash_button_under,
    versions_button,
)
from .hud_icons import MINIMIZE_FUNESTRA_ICON, UNFAVORITE_ICON, shared_icon
from .hud_title import (
    F_MODE_LABEL,
    LATEST_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    HudTitleFacts,
    compilation_label,
    hud_title,
    looping_label,
)
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
from .loop_cycle import ACTION, OFF, SEED
from .main_hud import VALUE_W, ModeHud
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
    favorite: bool = False
    flick_one: str = ""
    flick_many: str = ""
    media: Included = BOTH
    enhancement: Included = BOTH
    hosted: bool = False
    clip_seconds: int | None = None


def facts_raw(facts: HudFacts) -> dict:
    return {field.name: _raw_value(getattr(facts, field.name)) for field in fields(HudFacts)}


def facts_from_raw(raw: object) -> HudFacts | None:
    if not isinstance(raw, dict):
        return None
    defaults = HudFacts()
    return HudFacts(**{field.name: _read_value(getattr(defaults, field.name), raw[field.name])
                       for field in fields(HudFacts) if field.name in raw})


def _raw_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    return value


def _read_value(default, raw):
    if isinstance(default, Enum):
        try:
            return type(default)(raw)
        except ValueError:
            return default
    if isinstance(default, tuple):
        return tuple(bool(part) for part in raw) if isinstance(raw, list) else default
    return raw


@dataclass(frozen=True)
class HudControl:
    name: str
    on: frozenset[Shows]
    buttons: Callable[[HudFacts, Shows], tuple[Button, ...]]
    row: int = 1


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

ADVANCE_INTERVAL = "advance_interval"

GENAU_RESET_TOOLTIP = f"Reset — everything back to how Genau starts: no filter, no {F_MODE_LABEL}, locked, shuffled"

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
        previous, back, forward, following = transport(
            "genau", noun=facts.flick_one, longer_than_a_step=False, cannot_step=NOT_IN_GENAU)
        return (replace(previous, command="genau_prev_flick"), back, forward,
                replace(following, command="genau_next_flick"))
    return transport(facts.funestra, noun=_noun(facts, shows),
                     longer_than_a_step=facts.longer_than_a_step, image=facts.image)


NOT_IN_GENAU = "not in Genau"


def _funscript_jump(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.GENAU:
        jump = funscript_jump_button("genau_funscript_jump", noun=facts.flick_one,
                                     has_osr2=True, has_funscript=True)
        return (replace(jump, dim=True, tooltip=f"{jump.tooltip} ({NOT_IN_GENAU})"),)
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
    return (lock_button(facts.funestra, locked=facts.locked, tooltip=tooltip,
                        group_break=False),)


def _slide_trash(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    return (_unless_a_favorite(trash_button(facts.funestra), facts, shows),)


def _video_trash(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    return (_unless_a_favorite(trash_button("main"), facts, shows),)


def _unless_a_favorite(trash: Button, facts: HudFacts, shows: Shows) -> Button:
    if not facts.favorite:
        return trash
    return replace(trash, icon=UNFAVORITE_ICON, danger=False,
                   tooltip=f"Unfavorite this {_noun(facts, shows)} and move on to the next")


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


def _flick_trash(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    return (_unless_a_favorite(trash_button_under("genau_trash_flick", "Send to Trash — move it out"),
                               facts, shows),)


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
    if shows is Shows.GENAU:
        return (reset_button("genau", nothing_to_reset=facts.nothing_to_reset,
                             tooltip=GENAU_RESET_TOOLTIP),)
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
    offered = facts.plays_vr is not None and facts.plays_flat is not None
    shown = [(ORIENTATION, (facts.plays_portrait, facts.plays_landscape), True),
             (PROJECTION, (bool(facts.plays_flat), bool(facts.plays_vr)) if offered else BOTH,
              offered)]
    if shows is Shows.KINO:
        shown.append((LENGTH, lengths_included(facts.length_mode), True))
    return tuple(
        button if can else replace(button, dim=True,
                                   tooltip=f"{button.tooltip} (all these {things} are one kind)")
        for pair, included, can in shown
        for button in pair.buttons(included, remembered=_remembered(facts, shows), things=things))


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
        dim=not facts.jump_to,
    ),)


def _versions(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    command = ("main_funestra_cycle_version" if shows is Shows.KINO
               else f"{facts.funestra}_cycle_version")
    return (replace(versions_button(command, noun=_noun(facts, shows),
                                    has_other_versions=facts.has_other_versions),
                    group_break=shows is not Shows.KINO),)


_KINO, _GENAU, _SLIDES = (frozenset({shows}) for shows in Shows)


class Row(IntEnum):
    TOP = 0
    SECOND = 1


TRANSPORT_CONTROLS: tuple[HudControl, ...] = (
    HudControl("transport", EVERY_SHOW, _transport, Row.TOP),
    HudControl("funscript_jump", EVERY_SHOW, _funscript_jump, Row.TOP),
    HudControl("trash", _SLIDES, _slide_trash),
    HudControl("video_trash", _KINO, _video_trash),
    HudControl("trash_flick", _GENAU, _flick_trash),
    HudControl("lock", EVERY_SHOW, _lock),
    HudControl("fmode", EVERY_SHOW, _fmode),
    HudControl("reset", EVERY_SHOW, _reset),
    HudControl("browse_order", EVERY_SHOW, _browse_order),
    HudControl("inclusions", _KINO | _GENAU, _inclusion_buttons),
    HudControl("media", _SLIDES, _media),
    HudControl("enhancement", _SLIDES, _enhancement),
    HudControl("compilation", _KINO, _compilation),
    HudControl("clip_scene", _KINO, _clip_scene),
    HudControl("versions", _KINO | _SLIDES, _versions),
    HudControl("flip", _GENAU, _flip),
)


def _controls_on(row: Row, facts: HudFacts, shows: Shows,
                 controls: tuple[HudControl, ...]) -> tuple[Button, ...]:
    return tuple(button for control in controls if shows in control.on and control.row == row
                 for button in control.buttons(facts, shows))


def _one_group_each(*groups: tuple[Button, ...]) -> tuple[Button, ...]:
    return tuple(replace(button, group_break=True) if index == 0 else button
                 for group in groups if group for index, button in enumerate(group))


def minimize_funestra_button(funestra: str) -> Button:
    return Button(f"{funestra}_minimize", MINIMIZE_FUNESTRA_ICON,
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


def _modes(facts: HudFacts) -> tuple[Button, ...]:
    return tuple(Button(command, label, "", width=BUTTON_WORD_W, lit=facts.main_mode is main_mode)
                 for command, label, main_mode in MODE_BUTTONS)


def _flick_seconds_row(facts: HudFacts) -> tuple[Button, ...]:
    return (
        Button("", f"{facts.flick_one.capitalize()} seconds", "", width=FIT_THE_WORD),
        Button("genau_flick_seconds_down", LESS_ICON, "Move on sooner"),
        Button("", "", "", width=VALUE_W, host_value=ADVANCE_INTERVAL),
        Button("genau_flick_seconds_up", MORE_ICON, f"Leave each {facts.flick_one} longer"),
    )


def clip_seconds_row(shape: str, seconds: int) -> tuple[Button, ...]:
    return (
        Button("", "Clip seconds", "", width=FIT_THE_WORD),
        Button(f"{shape}_clip_seconds_down", LESS_ICON, "Move on sooner"),
        Button("", f"{seconds}s", "", width=VALUE_W),
        Button(f"{shape}_clip_seconds_up", MORE_ICON, "Leave each clip longer"),
        *playback_speed_buttons(shape),
    )


def _pace_row(facts: HudFacts, shows: Shows) -> tuple[Button, ...]:
    if shows is Shows.KINO:
        return playback_speed_buttons("main_funestra")
    if shows is Shows.GENAU:
        return _one_group_each(playback_speed_buttons("main_funestra"), _flick_seconds_row(facts))
    return () if facts.clip_seconds is None else clip_seconds_row(facts.funestra, facts.clip_seconds)


def _top_row(kind: HudKind, facts: HudFacts, shows: Shows,
             controls: tuple[HudControl, ...]) -> tuple[Button, ...]:
    on_top = _controls_on(Row.TOP, facts, shows, controls)
    osr2 = (osr2_button(facts.funestra, has_it=facts.has_osr2),)
    if kind is HudKind.MAIN:
        return _one_group_each(_modes(facts), osr2, on_top, window_buttons(facts),
                               _file_controls(facts, shows))
    return _one_group_each(osr2, on_top, window_buttons(facts))


def hud_rows(kind: HudKind, facts: HudFacts,
             controls: tuple[HudControl, ...] = TRANSPORT_CONTROLS) -> tuple[tuple[Button, ...], ...]:
    shows = shows_on(kind, facts)
    second = _controls_on(Row.SECOND, facts, shows, controls)
    if kind is HudKind.SLIDESHOW and facts.hosted:
        rows = (_one_group_each(_controls_on(Row.TOP, facts, shows, controls), second),)
    elif kind is HudKind.SLIDESHOW:
        minimize = () if facts.in_vr else (minimize_funestra_button(facts.funestra),)
        rows = (_one_group_each(_controls_on(Row.TOP, facts, shows, controls), minimize),
                _one_group_each(second))
    else:
        rows = (_top_row(kind, facts, shows, controls), _one_group_each(second))
    return tuple(row for row in (*rows, _pace_row(facts, shows)) if row)


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


def title_filters(facts: HudFacts) -> tuple[str, ...]:
    return tuple(word for pair, included in _inclusions(facts, shows_on(HudKind.MAIN, facts))
                 if (word := pair.title_word(included)))


def main_title(facts: HudFacts, block: ModeHud) -> str:
    playing_set = (f"{compilation_label(block.compilation)}{SEPARATOR}{block.position}/{block.total}"
                   if block.compilation else "")
    order = "" if facts.latest is None else LATEST_LABEL if facts.latest else SHUFFLE_LABEL
    if facts.main_mode is MainMode.GENAU and not facts.locked and facts.pace_s:
        order = SEPARATOR.join(part for part in (order, f"{facts.pace_s}s") if part)
    return hud_title(HudTitleFacts(locked=facts.locked, playing_set=playing_set, order=order,
                                   f_mode=block.scripted_filter, filters=title_filters(facts)))


def slideshow_title(facts: HudFacts, *, loop: str = "", action_filter: str = "") -> str:
    return hud_title(HudTitleFacts(
        playing_set=looping_label(loop) if loop else "", locked=facts.locked,
        order="" if facts.latest is None else LATEST_LABEL if facts.latest else SHUFFLE_LABEL,
        f_mode=facts.f_mode,
        filters=(media_pair("").title_word(facts.media),
                 enhancement_pair("").title_word(facts.enhancement), action_filter)))


_ONE_OR_BOTH: tuple[Included, ...] = (BOTH, (True, False), (False, True))
_LONGEST_PACE = 99


def title_choices(kind: HudKind) -> tuple[str, ...]:
    if kind is HudKind.MAIN:
        return tuple(sorted({
            main_title(HudFacts(main_mode=mode, locked=locked, latest=latest, pace_s=_LONGEST_PACE,
                                plays_flat=projection[0], plays_vr=projection[1],
                                length_mode=length, plays_portrait=orientation[0],
                                plays_landscape=orientation[1]),
                       ModeHud(scripted_filter=f_mode))
            for mode, locked, latest, f_mode, projection, length, orientation in product(
                MainMode, (True, False), (True, False, None), (True, False), _ONE_OR_BOTH,
                (LengthMode.MIXED, LengthMode.FULL, LengthMode.CLIPS), _ONE_OR_BOTH)}))
    return tuple(sorted({
        slideshow_title(HudFacts(locked=locked, latest=latest, f_mode=f_mode, media=media,
                                 enhancement=enhancement), loop=loop)
        for loop, locked, latest, f_mode, media, enhancement in product(
            (OFF, SEED, ACTION), (True, False), (True, False), (True, False), _ONE_OR_BOTH,
            _ONE_OR_BOTH)}))

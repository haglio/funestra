"""A source's console rows, made up for the tests that draw them and press
them: the shape a source's rows take, every state set here."""
from __future__ import annotations

from shared_ui.spacing import BUTTON_WORD_W

from funestra.console import ROW_LABEL_W, VALUE_W
from funestra.hud_button import Button
from funestra.hud_marks import BROKER_ICON, FMODE_ICON, MINIMIZE_ICON, shared_mark

# Wider than any console is drawn, so a hover over its button has to wrap.
LONG_TIP = ("Reset the browse: no filter, no lock, no loop, no F-Mode, and the "
            "whole library shuffled again from the top")


def console_rows(mode: str = "kino", *, locked: bool = False, favorites: bool = False,
                 remembered: bool = False,
                 enhanced: bool | None = None,
                 recording: bool = False) -> tuple[tuple[Button, ...], ...]:
    """The mode row with minimize riding it, the transport, and a named read-out
    between two arrows -- the controls only a video has, only in kino mode."""
    kino = mode == "kino"
    pace = "main_player_speed" if kino else "genau_clip_seconds"
    return (
        (Button("main_kino_activate", "Kino", "Kino mode", width=BUTTON_WORD_W, lit=kino),
         Button("genau_activate", "Genau", "Genau mode", width=BUTTON_WORD_W, lit=not kino),
         Button("main_minimize", MINIMIZE_ICON, "Minimize", group_break=True),
         *((Button("main_player_record_tap", "⏺", "Record a loop", warn=recording,
                   group_break=True),) if kino else ())),
        (Button("main_prev", "⏮", "Previous"),
         Button("main_next", "⏭", "Next"),
         Button("main_lock", "🔒", "Lock", lit=locked, favorite=True, group_break=True),
         Button("main_fmode", FMODE_ICON, "F-Mode", lit=favorites, favorite=True),
         *(() if enhanced is None else (
             Button("genau_filter_enhanced", shared_mark("enhance_filter"), "Enhanced only",
                    lit=enhanced, enhanced=True),)),
         Button("main_reset", shared_mark("reset"), LONG_TIP, group_break=True),
         Button("main_shuffle", shared_mark("shuffle"), "Shuffle",
                lit=not remembered, remembered=remembered, group_break=True),
         *((Button("main_player_cycle_version", shared_mark("versions"),
                   "Another version (none for this one)", dim=True, group_break=True),)
           if kino else ())),
        (Button("", "Playback speed" if kino else "Clip seconds", "", width=ROW_LABEL_W),
         Button(f"{pace}_down", "−", "Less", group_break=True),
         Button("", "", "", width=VALUE_W,
                host_value="playback_speed" if kino else "advance_interval"),
         Button(f"{pace}_up", "+", "More")),
    )


def motion_rows(*, cruise: bool = False) -> tuple[tuple[Button, ...], ...]:
    return ((Button("robot_hand_toggle_cruise", "cc", "Cruise control", lit=cruise),),)


def osr2_controls(*, broker: bool = True) -> tuple[Button, ...]:
    return (Button("broker_panel", BROKER_ICON, "Broker", lit=broker, warn=not broker),)

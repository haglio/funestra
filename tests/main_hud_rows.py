from __future__ import annotations

from shared_ui.spacing import BUTTON_WORD_W

from funestra.hud_button import Button
from funestra.hud_icons import FMODE_ICON, MINIMIZE_ICON, shared_icon
from funestra.main_hud import ROW_LABEL_W, VALUE_W

LONG_TIP = ("Reset the browse: no filter, no lock, no loop, no F-Mode, and the "
            "whole library shuffled again from the top")


def main_hud_rows(mode: str = "kino", *, locked: bool = False, favorites: bool = False,
                 remembered: bool = False,
                 enhanced: bool | None = None,
                 recording: bool = False) -> tuple[tuple[Button, ...], ...]:
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
             Button("genau_filter_enhanced", shared_icon("enhance_filter"), "Enhanced only",
                    lit=enhanced, enhanced=True),)),
         Button("main_reset", shared_icon("reset"), LONG_TIP, group_break=True),
         Button("main_shuffle", shared_icon("shuffle"), "Shuffle",
                lit=not remembered, remembered=remembered, group_break=True),
         *((Button("main_player_cycle_version", shared_icon("versions"),
                   "Another version (none for this one)", dim=True, group_break=True),)
           if kino else ())),
        (Button("", "Playback speed" if kino else "Clip seconds", "", width=ROW_LABEL_W),
         Button(f"{pace}_down", "\u2212", "Less", group_break=True),
         Button("", "", "", width=VALUE_W,
                host_value="playback_speed" if kino else "advance_interval"),
         Button(f"{pace}_up", "+", "More")),
    )


def motion_rows(*, learned: bool = False) -> tuple[tuple[Button, ...], ...]:
    return ((Button("robot_hand_toggle_learned", "hi", "Human inspired", lit=learned),),)


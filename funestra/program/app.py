from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

import pygame
from app_support.logging_utils import install_exception_logging
from app_support.processes import is_running
from app_support.win32 import set_app_user_model_id

from ..channel_manifest import EVERY_CHANNEL, channel_flag, channels_from_args
from ..funestra import Channels, Funestra
from ..funestra_priority import ahead_on_the_processor
from ..funestra_setup import FunestraSetup
from ..funestra_verbs import QUIT
from ..playlist import PlaylistItem, read_playlist
from .asks import tell_the_app_a_key, tell_the_app_it_came_forward
from .cli import build_parser, resolve_playlist
from .genau_here import genau_from_args, kino_and_genau
from .input import Input
from .placement import WindowPlacement
from .window import (
    before_the_window_exists,
    claim_the_sessions_taskbar_identity,
    replace_pygames_logo_with,
    run_the_window,
    take_outside_resizes,
    wear_the_sessions_taskbar_button,
)
from .window_verbs import WindowVerbs

logger = logging.getLogger(__name__)

_LOOK_FOR_A_LIST_EVERY_S = 0.1
_ASK_AFTER_THE_APP_EVERY_S = 1.0


def set_up_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    install_exception_logging(logger)
    return logger


def main(argv: list[str] | None = None, *, channels: Sequence[str] = EVERY_CHANNEL,
         silent: bool = False) -> int:
    set_up_logging()
    args = build_parser(channels).parse_args(argv)
    if args.playlist is None:
        logger.error("No videos to play (need %s)", channel_flag("playlist"))
        return 1
    with ahead_on_the_processor():
        return _run(args, resolve_playlist(args), channels=channels, silent=silent)


def _open_window(placement: WindowPlacement, claim_identity, *, hidden: bool = False) -> int:
    # SDL: before the window exists and before pygame.init(), or SDL eats the click that focuses
    # this window (funestra.sdl_hints).
    before_the_window_exists()
    # Windows reads a process's taskbar identity as each window is created.
    claim_the_sessions_taskbar_identity(placement.taskbar_identity, claim=claim_identity)
    pygame.init()
    if placement.x is not None and placement.y is not None:
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{placement.x},{placement.y}"
    replace_pygames_logo_with(pygame, placement.icon)
    # Borderless, so the client area is the place it was given: mpv paints into this window by its
    # handle and the pygame surface is never blitted.
    pygame.display.set_mode((placement.width, placement.height),
                            pygame.NOFRAME | (pygame.HIDDEN if hidden else 0))
    take_outside_resizes(pygame)
    pygame.display.set_caption(placement.title)
    hwnd = pygame.display.get_wm_info()["window"]
    wear_the_sessions_taskbar_button(hwnd, placement.taskbar_identity)
    return hwnd


def _a_list_once_one_is_written(channels: Channels, still_wanted: Callable[[], bool],
                                flicks: Path | None) -> list[PlaylistItem] | None:
    while True:
        pygame.event.get()
        if QUIT in _lines_of(channels.command) or not still_wanted():
            return None
        playlist = read_playlist(channels.playlist)
        if playlist or (flicks is not None and read_playlist(flicks)):
            return playlist
        time.sleep(_LOOK_FOR_A_LIST_EVERY_S)


def _lines_of(path: Path | None) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").split() if path else []
    except OSError:
        return []


class _EndsWithItsApp:
    def __init__(self, pid: int | None, funestra, is_running: Callable[[int], bool],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._pid, self._funestra, self._is_running, self._clock = pid, funestra, is_running, clock
        self._asked_at = float("-inf")

    def look(self) -> None:
        now = self._clock()
        if self._pid is None or now - self._asked_at < _ASK_AFTER_THE_APP_EVERY_S:
            return
        self._asked_at = now
        if not self._is_running(self._pid):
            self._funestra.apply(QUIT)


def _run(args, playlist: list[PlaylistItem], *, channels: Sequence[str] = EVERY_CHANNEL,
         silent: bool = False, claim_identity=set_app_user_model_id,
         host_is_running: Callable[[int], bool] = is_running) -> int:
    placement = WindowPlacement.from_args(args)
    files = Channels(**channels_from_args(args, channels))
    genau = genau_from_args(args)
    window = _open_window(placement, claim_identity, hidden=args.hidden)
    playlist = playlist or _a_list_once_one_is_written(
        files, lambda: args.ends_with is None or host_is_running(args.ends_with),
        None if genau is None else genau.flicks)
    if playlist is None:
        pygame.quit()
        return 0
    logger.info("Funestra playing %d item(s)", len(playlist))
    funestra = Funestra.on_window(window, FunestraSetup(
        channels=files, playlist=playlist,
        audible=not (silent or args.no_audio), tiles=placement.tiles,
        window_verbs=WindowVerbs(pygame),
        users=kino_and_genau(genau, notice=files.notice),
    ))
    window_input = Input(
        funestra,
        keys=partial(tell_the_app_a_key, files.dashboard_cmd) if args.keys else None,
        focused=partial(tell_the_app_it_came_forward, files.dashboard_cmd) if args.keys else None,
        tells_a_press_made_again=args.keys)
    ends_with_its_app = _EndsWithItsApp(args.ends_with, funestra, host_is_running)

    def deal(events, viewport: tuple[int, int]) -> None:
        ends_with_its_app.look()
        window_input.deal(events, viewport)

    run_the_window(pygame, funestra, deal)
    return 0

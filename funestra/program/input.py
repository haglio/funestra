from __future__ import annotations

import time
from collections.abc import Callable

import pygame

AGAIN_WITHIN_S = 0.5
AGAIN_WITHIN_PIXELS = 4
_HELD = (("shift", pygame.KMOD_SHIFT), ("ctrl", pygame.KMOD_CTRL), ("alt", pygame.KMOD_ALT))


def held_with(mod: int) -> str:
    return "+".join(name for name, mask in _HELD if mod & mask)


class Input:
    def __init__(self, funestra, *, keys: Callable[[str, str], None] | None = None,
                 focused: Callable[[], None] | None = None,
                 tells_a_press_made_again: bool = False,
                 pointer_at: Callable[[], tuple[int, int]] = pygame.mouse.get_pos,
                 clock: Callable[[], float] = time.monotonic,
                 again_within_s: float = AGAIN_WITHIN_S) -> None:
        self._funestra = funestra
        self._keys = keys
        self._focused = focused
        self._tells_a_press_made_again = tells_a_press_made_again
        self._pointer_at = pointer_at
        self._clock = clock
        self._again_within_s = again_within_s
        self._last_press: tuple[float, tuple[int, int]] | None = None

    def deal(self, events, viewport: tuple[int, int]) -> None:
        for ev in events:
            if ev.type == pygame.QUIT:
                self._funestra.close_requested()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self._press(ev.pos, viewport)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                self._funestra.right_press(*ev.pos, viewport=viewport)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self._funestra.release()
            elif ev.type == pygame.MOUSEMOTION:
                self._funestra.motion(*ev.pos, held=bool(ev.buttons[0]), viewport=viewport)
            elif ev.type == pygame.MOUSEWHEEL:
                self._funestra.wheel(*self._pointer_at(), ev.y, viewport=viewport)
            elif ev.type == pygame.WINDOWLEAVE:
                self._funestra.leave()
            elif ev.type == pygame.KEYDOWN and self._keys is not None:
                self._keys(pygame.key.name(ev.key), held_with(ev.mod))
            elif ev.type == pygame.WINDOWFOCUSGAINED and self._focused is not None:
                self._focused()

    def _press(self, at: tuple[int, int], viewport: tuple[int, int]) -> None:
        now, last = self._clock(), self._last_press
        again = (self._tells_a_press_made_again
                 and last is not None and now - last[0] <= self._again_within_s
                 and max(abs(at[0] - last[1][0]), abs(at[1] - last[1][1])) <= AGAIN_WITHIN_PIXELS)
        self._last_press = None if again else (now, at)
        if again:
            self._funestra.press_again(*at, viewport=viewport)
        else:
            self._funestra.press(*at, viewport=viewport)

from __future__ import annotations

from collections.abc import Callable


def told_to_the_host(move: Callable[..., None], volume, on_moved) -> Callable[..., None]:
    def moved(*args) -> None:
        move(*args)
        if on_moved is not None:
            on_moved(volume.hud)
    return moved

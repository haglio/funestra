from __future__ import annotations


def put_up_next[T](items: list[T], up: int, item: T, listed_at: int | None) -> int:
    if listed_at == up:
        return up
    if listed_at is not None:
        del items[listed_at]
        if listed_at < up:
            up -= 1
    items.insert(up + 1, item)
    return up

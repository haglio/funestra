from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .flick_overlay import FlickFrame
from .main_hud import ModeHud
from .pointer import OMNIPAUSE_TOGGLE


@runtime_checkable
class User(Protocol):
    def apply_command(self, command: str) -> bool: ...

    def tick(self) -> None: ...

    def status_fields(self) -> Mapping[str, str]: ...

    def top_block(self) -> ModeHud: ...

    def set_showing(self, showing: bool) -> None: ...

    def close(self) -> None: ...


class _Nobody:
    def apply_command(self, command: str) -> bool:
        return False

    def tick(self) -> None:
        pass

    def status_fields(self) -> Mapping[str, str]:
        return {}

    def top_block(self) -> ModeHud:
        return ModeHud()

    def set_showing(self, showing: bool) -> None:
        pass

    def own_frame(self) -> FlickFrame | None:
        return None

    def close(self) -> None:
        pass


NOBODY = ""


class RunsHere:
    def __init__(self, users: Mapping[str, User] | None) -> None:
        self._users: dict[str, User] = dict(users) if users else {NOBODY: _Nobody()}
        self._showing = next(iter(self._users))
        self.front.set_showing(True)

    def __getitem__(self, name: str) -> User:
        return self._users[name]

    @property
    def showing(self) -> str:
        return self._showing

    @property
    def front(self) -> User:
        return self._users[self._showing]

    def show(self, name: str) -> bool:
        if name not in self._users:
            return False
        if name != self._showing:
            self.front.set_showing(False)
            self._showing = name
            self.front.set_showing(True)
        return True

    def apply(self, command: str) -> bool:
        return any(user.apply_command(command) for user in self._users.values())

    def ask_to_pause(self) -> None:
        self.apply(OMNIPAUSE_TOGGLE)

    def tick(self) -> None:
        for user in self._users.values():
            user.tick()

    def status_fields(self) -> dict[str, str]:
        return {key: value for user in self._users.values()
                for key, value in user.status_fields().items()}

    def close(self) -> None:
        for user in self._users.values():
            user.close()

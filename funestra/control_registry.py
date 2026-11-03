from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

Act = Callable[[Any, str], bool]


@dataclass(frozen=True)
class Verb:
    spelling: str
    act: Act
    takes_a_value: bool = False


@dataclass(frozen=True)
class Control:
    name: str
    verbs: tuple[Verb, ...]
    needs: tuple[str, ...] = ()

    def can_act(self, controls: Any) -> bool:
        return all(getattr(controls, name) is not None for name in self.needs)


def bind(controls: tuple[Control, ...]) -> Mapping[str, tuple[Control, Verb]]:
    bound: dict[str, tuple[Control, Verb]] = {}
    for control in controls:
        for verb in control.verbs:
            if verb.spelling in bound:
                other, _ = bound[verb.spelling]
                raise ValueError(
                    f"{verb.spelling} is claimed by both "
                    f"{other.name} and {control.name}"
                )
            bound[verb.spelling] = (control, verb)
    return bound


def act(control: Control, verb: Verb, controls: Any, value: str) -> bool:
    if not control.can_act(controls):
        return False
    if verb.takes_a_value != bool(value):
        return False
    return verb.act(controls, value)


def look_up(
    command, verbs: Mapping[str, tuple[Control, Verb]], controls: Any,
) -> bool:
    if not command:
        return False
    said = command.strip().split(None, 1)
    if not said:
        return False
    declared = verbs.get(said[0].upper())
    if declared is None:
        return False
    return act(*declared, controls, said[1].strip() if len(said) > 1 else "")

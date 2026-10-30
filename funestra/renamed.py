"""The old names a renamed module, function or class still answers to.

Every app on this machine runs out of one venv per app, and every open branch of
it runs out of that same venv, so a name this package renames is still spelled
the old way by every checkout from before the rename until it is rebased. These
keep those checkouts importing and running; nothing new may use them.
"""
from __future__ import annotations

import functools
import importlib
import inspect
from collections.abc import Callable, Mapping
from typing import Any


def old_name_getter(module: str, renamed: Mapping[str, str]) -> Callable[[str], Any]:
    def __getattr__(name: str) -> Any:
        if name not in renamed:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        return getattr(importlib.import_module(module), renamed[name])
    return __getattr__


def _under_new_names(kwargs: dict[str, Any], renamed: Mapping[str, str]) -> dict[str, Any]:
    for old, new in renamed.items():
        if old in kwargs:
            kwargs[new] = kwargs.pop(old)
    return kwargs


def _taking_old_keywords(call: Callable[..., Any], renamed: Mapping[str, str]) -> Callable[..., Any]:
    """*call* under its old keywords too, and saying so in its signature, which an
    app's check of what its shells hand the shared code reads."""
    @functools.wraps(call)
    def called(*args, **kwargs):
        return call(*args, **_under_new_names(kwargs, renamed))

    signature = inspect.signature(call)
    taken = signature.parameters
    old = [inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=None)
           for name, new in renamed.items() if new in taken and name not in taken]
    kept = [p for p in taken.values() if p.kind is not inspect.Parameter.VAR_KEYWORD]
    rest = [p for p in taken.values() if p.kind is inspect.Parameter.VAR_KEYWORD]
    called.__signature__ = signature.replace(parameters=[*kept, *old, *rest])
    return called


def takes_old_keywords(renamed: Mapping[str, str]) -> Callable[[Any], Any]:
    """For a function an old checkout still calls with keywords since renamed."""
    return lambda call: _taking_old_keywords(call, renamed)


def answers_to_old_names(renamed: Mapping[str, str]) -> Callable[[type], type]:
    def wrap(cls: type) -> type:
        cls.__init__ = _taking_old_keywords(cls.__init__, renamed)
        for old, new in renamed.items():
            setattr(cls, old, property(lambda self, new=new: getattr(self, new),
                                       lambda self, value, new=new: setattr(self, new, value)))
        return cls
    return wrap

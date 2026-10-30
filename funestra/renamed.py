"""The old names a renamed module, function or class still answers to.

Every app on this machine runs out of one venv per app, and every open branch of
it runs out of that same venv, so a name this package renames is still spelled
the old way by every checkout from before the rename until it is rebased. These
keep those checkouts importing and running; nothing new may use them.
"""
from __future__ import annotations

import functools
import importlib
import importlib.abc
import importlib.util
import sys
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

PACKAGE = "funestra"


class _OldPackageName(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, old_package: str) -> None:
        self.old_package = old_package

    def new_module_name(self, old: str) -> str:
        return f"{PACKAGE}.{old.partition('.')[2]}"

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(f"{self.old_package}."):
            return None
        if importlib.util.find_spec(self.new_module_name(fullname)) is None:
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        module = importlib.import_module(self.new_module_name(spec.name))
        spec.loader_state = module.__spec__
        return module

    def exec_module(self, module):
        module.__spec__ = module.__spec__.loader_state


def answer_as(old_package: str) -> Callable[[str], ModuleType]:
    if not any(isinstance(finder, _OldPackageName) and finder.old_package == old_package
               for finder in sys.meta_path):
        sys.meta_path.insert(0, _OldPackageName(old_package))

    def __getattr__(name: str) -> ModuleType:
        if name.startswith("__"):
            raise AttributeError(name)
        try:
            return importlib.import_module(f"{old_package}.{name}")
        except ModuleNotFoundError as missing:
            raise AttributeError(name) from missing
    return __getattr__


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


def takes_old_keywords(renamed: Mapping[str, str]) -> Callable[[Any], Any]:
    """For a function an old checkout still calls with keywords since renamed."""
    def wrap(call: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(call)
        def called(*args, **kwargs):
            return call(*args, **_under_new_names(kwargs, renamed))
        return called
    return wrap


def answers_to_old_names(renamed: Mapping[str, str]) -> Callable[[type], type]:
    def wrap(cls: type) -> type:
        init = cls.__init__

        @functools.wraps(init)
        def __init__(self, *args, **kwargs) -> None:
            init(self, *args, **_under_new_names(kwargs, renamed))

        cls.__init__ = __init__
        for old, new in renamed.items():
            setattr(cls, old, property(lambda self, new=new: getattr(self, new),
                                       lambda self, value, new=new: setattr(self, new, value)))
        return cls
    return wrap


def drops_retired_arguments(*retired: str) -> Callable[[Any], Any]:
    """For a class or function an old checkout still hands arguments it no
    longer takes: those keywords are dropped, unread."""
    def without_them(call: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(call)
        def called(*args, **kwargs):
            for name in retired:
                kwargs.pop(name, None)
            return call(*args, **kwargs)
        return called

    def wrap(target: Any) -> Any:
        if isinstance(target, type):
            target.__init__ = without_them(target.__init__)
            return target
        return without_them(target)
    return wrap


def method_of(obj: object, name: str, *, old_name: str) -> Callable[..., Any]:
    """*obj*'s method *name*, or *old_name* on a collaborator from before the rename."""
    return getattr(obj, name, None) or getattr(obj, old_name)

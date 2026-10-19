"""A folder the engine's file access is held to.

The MCP server takes ``--root DIR`` for a benchmarked model, which must not
read the reference solutions kept elsewhere in the repository. Every path a
tool reads or writes -- a document opened, a reference attached, LandXML
imported, a render, an export, a save -- must then resolve, links followed,
inside DIR, or the call fails. Without a root nothing is held: the GUI and the
desktop app open and save wherever their user points them.

The root is held for the length of one tool call (``held``), not for the
process, so the engine's other callers and the tests are untouched. Relative
paths resolve as they always have (the working directory, a reference's host
folder); only where they land is checked.

A root also keeps where it is to itself: ``Root.show`` rewrites every absolute
path inside it as a path relative to the working directory, which is what a
relative path the agent gives resolves against, so a path it is shown can be
handed straight back.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Optional

#: what ends a path written into a message: a path inside the root is
#: rewritten up to the first of these
_STOPS = r"\s'\"()\[\]{},;:"


class OutsideRoot(Exception):
    """A path that leads out of the root."""

    hint = ("use a path inside it, relative to the document's folder; a path "
            "that leads out of it (absolute, through '..', or by a link) is "
            "refused")

    def __init__(self, given):
        self.given = str(given)
        super().__init__(f"{self.given!r} is outside the folder this session "
                         f"may read and write")


class Root:
    """The folder, as given (made absolute) and with its links followed."""

    def __init__(self, folder):
        self.given = os.path.abspath(os.path.expanduser(str(folder)))
        self.real = os.path.realpath(self.given)
        forms = sorted({self.given, self.real}, key=len, reverse=True)
        self._pattern = re.compile(
            "(?:" + "|".join(re.escape(f) for f in forms) + ")"
            + f"(?P<tail>/[^{_STOPS}]*)?(?![^{_STOPS}])")

    def contains(self, path) -> bool:
        """Whether ``path`` resolves, links followed, inside the root."""
        real = os.path.realpath(os.path.expanduser(str(path)))
        try:
            return os.path.commonpath([real, self.real]) == self.real
        except ValueError:  # different drives
            return False

    def base(self) -> str:
        """What a shown path is relative to: the working directory while it
        is inside the root, else the root."""
        cwd = os.path.realpath(os.getcwd())
        return cwd if self.contains(cwd) else self.real

    def show(self, value, base: Optional[str] = None):
        """``value`` -- a string, or a result's dicts and lists of them -- with
        every absolute path inside the root written relative to ``base``."""
        base = base or self.base()
        if isinstance(value, str):
            if self.given not in value and self.real not in value:
                return value
            return self._pattern.sub(
                lambda m: os.path.relpath(self.real + (m.group("tail") or ""), base),
                value)
        if isinstance(value, dict):
            return {k: self.show(v, base) for k, v in value.items()}
        if isinstance(value, list):
            return [self.show(v, base) for v in value]
        if isinstance(value, tuple):
            return tuple(self.show(v, base) for v in value)
        return value


_ROOT: ContextVar = ContextVar("roaddraft_root", default=None)


def current() -> Optional[Root]:
    """The root held now, or None."""
    return _ROOT.get()


@contextmanager
def held(root: Optional[Root]) -> Iterator[None]:
    """Hold file access to ``root`` (None holds nothing) for the block."""
    token = _ROOT.set(root)
    try:
        yield
    finally:
        _ROOT.reset(token)


def inside(path) -> bool:
    """Whether ``path`` may be used: always, with no root held."""
    root = _ROOT.get()
    return root is None or root.contains(path)


def check(path, given=None) -> Path:
    """``path``, unchanged, if it may be used; else ``OutsideRoot`` naming
    ``given`` (what the caller was handed, default ``path``)."""
    if not inside(path):
        raise OutsideRoot(path if given is None else given)
    return Path(path)


__all__ = ["OutsideRoot", "Root", "current", "held", "inside", "check"]

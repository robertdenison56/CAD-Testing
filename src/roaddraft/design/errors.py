"""Design-model error type.

Every validation failure in the ``design`` package raises ``DesignError``
with a teaching-style message and an optional ``hint``.  Command handlers
re-raise it as ``CommandFault(str(e), hint=e.hint)``; queries as a query
fault.  The design package never imports anything from commands/api/web.
"""
from __future__ import annotations

from typing import Optional


class DesignError(Exception):
    """A design-model validation or lookup failure.

    Args:
        message: human-readable teaching error (the exception text).
        hint: optional one-line suggestion of what to do instead.
    """

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DesignError({str(self)!r}, hint={self.hint!r})"

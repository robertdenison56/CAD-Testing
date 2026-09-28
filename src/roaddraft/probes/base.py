"""What a probe is. Shared by the find-probes (``tasks.py``) and the
drafting-probes (``drafting.py``)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from roaddraft.api.session import Session


@dataclass
class Result:
    passed: bool
    detail: str


@dataclass
class Probe:
    id: str
    prompt: str
    check: Callable[[Session, Session], Result]
    solve: Optional[Callable[[Session], None]] = None
    note: str = ""
    blocked_on: str = ""
    tags: List[str] = field(default_factory=list)
    #: which document of the fixture the agent is handed (see fixture.START)
    start: str = "sheets"


__all__ = ["Probe", "Result"]

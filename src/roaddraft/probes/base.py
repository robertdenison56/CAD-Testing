"""What a probe is. Shared by the find-probes (``tasks.py``) and the
drafting-probes (``drafting.py``)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from roaddraft.api.session import Session


@dataclass
class Result:
    passed: bool
    detail: str
    #: what the task asked for, item by item, and whether the document has each:
    #: scope completion, the research plan's §3.2. Empty for a probe that asks
    #: for one thing, whose one item is the pass itself.
    items: List[Tuple[str, bool]] = field(default_factory=list)

    def scope(self) -> Tuple[int, int]:
        """``(items done, items asked)``."""
        if not self.items:
            return int(self.passed), 1
        return sum(done for _name, done in self.items), len(self.items)


class Tally:
    """A check made of items. Every item is judged, so the scope can be
    counted, but the verdict is still the first problem found, in the order
    the check looks, so a check reads the same as one that stopped there.

    ``add`` judges an item (an item added twice is done only if both pass);
    ``take`` folds in another check's items and verdict; ``fail`` records a
    problem that is no one item's, such as two callouts crossing; ``clean``
    is whether nothing has gone wrong yet, for checks that only look at the
    whole once every item is in."""

    def __init__(self) -> None:
        self.done: Dict[str, bool] = {}
        self.problem: Optional[str] = None

    def add(self, item: str, problem: Optional[str]) -> bool:
        self.done[item] = self.done.get(item, True) and problem is None
        return self.fail(problem)

    def take(self, result: Result, item: str = "") -> bool:
        """Another check's result, items and verdict, as part of this one; a
        result with no items of its own counts as the one ``item``."""
        for item, done in result.items or [(item, result.passed)]:
            self.done[item] = self.done.get(item, True) and done
        return self.fail(None if result.passed else result.detail)

    def fail(self, problem: Optional[str]) -> bool:
        if problem and self.problem is None:
            self.problem = problem
        return problem is None

    @property
    def clean(self) -> bool:
        return self.problem is None

    def result(self, good: str) -> Result:
        return Result(self.problem is None, self.problem or good, list(self.done.items()))


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
    #: for an instance of a probe family (families.py): the family, and the
    #: parameters the seed drew. Empty for the fixed probes.
    family: str = ""
    params: dict = field(default_factory=dict)
    #: extra roaddraft-mcp options the probe needs (``--attachments {project}/scans``);
    #: ``{project}`` is the project folder the start is built in
    server_args: List[str] = field(default_factory=list)
    #: the task at the vague prompt level (Robert, 2026-11-08: every eval task has one):
    #: the request the way a PE would ask for it, keeping what the drafter cannot know
    #: (which files, lines and stations, the data given, the answer format a check reads)
    #: and leaving out the drafting standards ``prompt`` states (layers, text heights,
    #: label forms, scales, tick lengths). Empty: the probe has no vague form.
    vague: str = ""
    #: the check at the vague level, when ``check`` grades a convention ``vague`` leaves
    #: unstated: it grades that convention by the spec's lenient rules instead (any layer
    #: but 0, legible lettering, any standard scale, values read by meaning). None: the
    #: vague prompt keeps everything ``check`` grades, so ``check`` serves both levels.
    vague_check: Optional[Callable[[Session, Session], Result]] = None

    def check_at(self, level: str) -> Callable[[Session, Session], Result]:
        """The check an episode at prompt ``level`` is graded by."""
        return self.vague_check if level == "vague" and self.vague_check is not None else self.check


__all__ = ["Probe", "Result", "Tally"]

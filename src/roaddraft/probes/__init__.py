"""Find-probes: can an agent locate the right object and point at it?

Capability probes, deliberately not the scored benchmark in
``RoadDraft_Eval_Plan.md``: no rubric, no spec hash, no task ids. See
``tasks.py`` for the probes and ``python -m roaddraft.probes`` to run them.
"""
from roaddraft.probes.tasks import PROBES, Probe, Result, get

__all__ = ["PROBES", "Probe", "Result", "get"]

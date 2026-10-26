"""Harder-task pilots: candidate probes for tasks the frontier does not yet pass.

On 2026-10-19 the frontier models passed 96-97% of the 33 probes (GPT-6.1-Sol
32/33), so these try tasks where the engine does less of the work: input that
is not clean data, layout decisions, changes that ripple, problems nobody
named. Each pilot is a handful of hand-built instances set on the real
example sheets (``examples/Exmple Plans/Redraft`` and ``Sheets``), with a
check that reads the document and a scripted solution that passes it.

They are NOT on the Track P board: ``tasks.PROBES`` and the probe-set hash
are unchanged, and a pilot is reached only by id (``tasks.get``) or with
``runners run --pilot``. Pilot runs go under ``benchmarks/pilot_runs``.

    python -m roaddraft.probes.pilot list
    python -m roaddraft.probes.pilot selftest [ID ...]
    python -m roaddraft.probes.pilot reference --out benchmarks/pilot_references [ID ...]

One module per pilot family; each exposes ``PROBES`` and registers its own
start documents with ``common.register``.
"""
from __future__ import annotations

import importlib
from typing import Dict, List

from roaddraft.probes.base import Probe

#: the pilot modules, by the brainstorm's numbers (2026-10-19)
MODULES = [
    "qa_review",    # 14 open-ended QA review, unknown number of planted errors
    "sources",      # 2  sources that disagree
    "redlines",     # 11 redlines with knock-on edits
    "plan_set",     # 12 a small full plan set
    "layout",       # 4 crowded annotation, 17 twisted variants, 5 the model picks the sheet breaks
    "scans",        # 1 redraw from a scanned sheet, 15 plan reading
    "survey",       # 3 survey traps: misclosure, grid vs ground, survey vs international feet
    "typical",      # 10 typical section from a description
    "profile",      # 6 plan and profile on one sheet
    "striping",     # 13 striping plan with no-passing zones
    "redline_pdf",  # 18 redline understanding: a marked-up PDF is the whole brief
]

PILOT_PROBES: List[Probe] = []
for _name in MODULES:
    _module = importlib.import_module(f"roaddraft.probes.pilot.{_name}")
    for _probe in getattr(_module, "PROBES", []):
        if "pilot" not in _probe.tags:
            _probe.tags = ["pilot"] + list(_probe.tags)
        PILOT_PROBES.append(_probe)

BY_ID: Dict[str, Probe] = {p.id: p for p in PILOT_PROBES}
if len(BY_ID) != len(PILOT_PROBES):
    raise RuntimeError("two pilot probes share an id")

__all__ = ["MODULES", "PILOT_PROBES", "BY_ID"]

"""Score a label's run folders from disk and read the §3.2 measures off the traces.

The document the model left is diffed against a fresh start, as the rigs'
``score_runs.py`` did, so a re-score runs against the current probe checks.
The trace gives the measures the model cards need: calls, faults and the
invalid-call rate, fault recovery (a fault followed within three calls by a
successful call of the same tool), the longest run of the same fault, renders
looked at and whether a change followed, design queries asked before the first
change, queries against commands. ``run.json`` gives the price of the
sheet: turns, seconds, tokens, cost.
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from roaddraft.api.session import Session
from roaddraft.probes import fixture, tasks

RECOVERY_WINDOW = 3
LOOP = 5
#: the queries that answer the arithmetic a drafter would otherwise do by hand
DESIGN_QUERIES = frozenset({"station_to_xy", "xy_to_station", "resolve_anchor",
                            "get_design_data", "measure", "point_on_entity"})
RENDERS = frozenset({"render_sheet", "render_model"})


def query_first(calls: List[dict]) -> Optional[bool]:
    """Whether a design query answered before the first change was made; None
    for a trace that changed nothing."""
    for c in calls:
        if c.get("ok") and c.get("kind") == "command":
            return False
        if c.get("ok") and c["tool"] in DESIGN_QUERIES:
            return True
    return None


def renders_fixed(calls: List[dict]) -> int:
    """Renders followed by a change before the next render or the end."""
    fixed, looking = 0, False
    for c in calls:
        if c["tool"] in RENDERS and c.get("ok"):
            looking = True
        elif looking and c.get("ok") and c.get("kind") == "command":
            fixed, looking = fixed + 1, False
    return fixed


def measures(calls: List[dict]) -> dict:
    """The tool-use measures of one trace (one dict per line of trace.jsonl)."""
    faults = [i for i, c in enumerate(calls) if not c.get("ok")]
    recovered = 0
    for i in faults:
        tool = calls[i]["tool"]
        if any(c.get("ok") and c["tool"] == tool for c in calls[i + 1:i + 1 + RECOVERY_WINDOW]):
            recovered += 1
    streak = best = 0
    previous = None
    for c in calls:
        key = (c["tool"], (c.get("error") or {}).get("message")) if not c.get("ok") else None
        streak = streak + 1 if key and key == previous else (1 if key else 0)
        best = max(best, streak)
        previous = key
    kinds = Counter(c.get("kind") for c in calls)
    return {"calls": len(calls), "commands": kinds.get("command", 0),
            "queries": kinds.get("query", 0), "faults": len(faults),
            "invalid_rate": round(len(faults) / len(calls), 3) if calls else None,
            "recovered": recovered, "fault_streak": best, "fault_loop": best >= LOOP,
            "renders": sum(c["tool"] in RENDERS for c in calls),
            "renders_fixed": renders_fixed(calls),
            "design_queries": sum(c["tool"] in DESIGN_QUERIES for c in calls),
            "query_first": query_first(calls),
            "tools": dict(Counter(c["tool"] for c in calls))}


def score_folder(folder: Path, probe, starts: Optional[Dict[str, Path]] = None) -> dict:
    """One probe's run folder: the check, the measures, the run's meta."""
    folder = Path(folder)
    trace = folder / "trace.jsonl"
    calls = ([json.loads(l) for l in trace.read_text().splitlines() if l.strip()]
             if trace.exists() else [])
    row = {"probe": probe.id, "calls": len(calls)}
    meta_file = folder / "run.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        row.update({k: meta.get(k) for k in ("backend", "model", "stop", "turns", "seconds",
                                               "tokens", "cost_usd")})
    if not calls:
        row.update({"passed": False, "detail": "no tool calls"})
        return row
    starts = starts if starts is not None else {}
    if probe.start not in starts:
        starts[probe.start] = Path(tempfile.mkdtemp(prefix="roaddraft-start-"))
        fixture.start_document(starts[probe.start], probe.start)
    baseline = Session.load(starts[probe.start] / fixture.START[probe.start],
                            out_dir=starts[probe.start])
    doc = folder / "project" / fixture.START[probe.start]
    result = probe.check(baseline, Session.load(doc, out_dir=folder))
    row.update({"passed": bool(result.passed), "detail": result.detail})
    row.update(measures(calls))
    row["fault_messages"] = [(c["tool"], (c.get("error") or {}).get("message", "")[:160])
                             for c in calls if not c.get("ok")]
    return row


def score_label(root: Path, only: Optional[List[str]] = None) -> List[dict]:
    """Every probe folder under ``root`` (``runs/<label>``); writes scores.json."""
    root = Path(root)
    rows, starts = [], {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if only and folder.name not in only:
            continue
        try:
            probe = tasks.get(folder.name)
        except KeyError:
            continue
        rows.append(score_folder(folder, probe, starts))
    (root / "scores.json").write_text(json.dumps(rows, indent=1))
    return rows


def format_table(rows: List[dict]) -> str:
    lines = []
    for r in rows:
        verdict = "PASS" if r.get("passed") else "FAIL"
        cost = f" ${r['cost_usd']:.2f}" if r.get("cost_usd") is not None else ""
        lines.append(f"{verdict}  {r['probe']}: {r.get('calls', 0)} calls, {r.get('faults', 0)} faults"
                     f"{' (loop)' if r.get('fault_loop') else ''}, {r.get('turns') or 0} turns, "
                     f"{r.get('seconds') or 0} s{cost}; stop: {r.get('stop')}")
        lines.append(f"      {r.get('detail', '')}")
        for tool, message in (r.get("fault_messages") or [])[:6]:
            lines.append(f"      FAULT {tool}: {message}")
    passed = sum(bool(r.get("passed")) for r in rows)
    lines.append(f"\n{passed}/{len(rows)} passed")
    return "\n".join(lines)

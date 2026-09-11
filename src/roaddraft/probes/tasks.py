"""Find-probes: can an agent locate the right object and point at it?

These are capability probes, not the scored benchmark. There is no rubric, no
spec hash, no task ids -- nothing here mints anything the eval plan depends on.
Each probe is one instruction, and the check asks a single question of the
finished document: *did the work land on the thing it was supposed to land on?*

A probe is scored by diffing the submitted document against the untouched
fixture and looking at what was added, so it does not care which commands were
used. A callout composed by hand out of draw_line and place_text scores exactly
like one from place_callout -- what is being measured is aim, not vocabulary.

``TOLERANCE_FT`` is 1.0 ft: on a 1"=50' sheet that is 0.02 in, tight enough
that the classic curve mistake (aiming at the midpoint of an arc's endpoints,
which is 15.5 ft off on this alignment) fails, and loose enough that rounding
does not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from roaddraft.api.session import Session
from roaddraft.document.entities import Line, Polyline, Text, entity_distance
from roaddraft.document.locate import point_at, resolve_entity
from roaddraft.probes import fixture

TOLERANCE_FT = 1.0

TITLE_FIELDS = {
    "project": "SR-100 WIDENING",
    "sheet_title": "ROADWAY PLAN",
    "scale": "1\" = 50'",
}


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


# ------------------------------------------------------------------ helpers


def added_entities(baseline: Session, submitted: Session):
    """Entities in the submitted document that the fixture did not have."""
    before = set(baseline.doc.model_entities)
    for sheet in baseline.doc.sheets.values():
        before |= set(sheet.entities)
    out = [e for eid, e in submitted.doc.model_entities.items() if eid not in before]
    for sheet in submitted.doc.sheets.values():
        out += [e for eid, e in sheet.entities.items() if eid not in before]
    return out


def leader_tips(entities):
    """Both ends of every added line/polyline: a leader tip is one of them."""
    tips = []
    for e in entities:
        if isinstance(e, Line):
            tips += [e.start, e.end]
        elif isinstance(e, Polyline) and e.vertices:
            tips += [e.vertices[0], e.vertices[-1]]
    return tips


def targets(session: Session, **find) -> List[str]:
    """Ids of the entities a probe considers correct to point at."""
    r = session.query("find_entities", {**find, "limit": 500})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return [row["id"] for row in r["entities"]]


def aimed_at(baseline: Session, submitted: Session, wanted: List[str],
             what: str, count: int = 1) -> Result:
    """Did the added linework put ``count`` tips within tolerance of ``wanted``?"""
    added = added_entities(baseline, submitted)
    if not added:
        return Result(False, "nothing was added to the document")
    if not any(isinstance(e, Text) for e in added):
        return Result(False, f"{len(added)} entities added but no text, so nothing "
                             f"is labelled")
    tips = leader_tips(added)
    if not tips:
        return Result(False, "text was added but no leader, so nothing points at "
                             f"{what}")
    hit = {}
    for eid in wanted:
        found = resolve_entity(baseline.doc, eid)
        if found is None:
            continue
        entity, owner, _ref, _space = found
        for tip in tips:
            distance = entity_distance(owner, entity, tip)
            if distance <= TOLERANCE_FT:
                hit.setdefault(eid, distance)
    if len(hit) >= count:
        near = ", ".join(f"{eid} ({d:.2f} ft)" for eid, d in sorted(hit.items())[:count])
        return Result(True, f"leader lands on {near}")
    best = _closest(baseline, wanted, tips)
    return Result(False, f"hit {len(hit)} of {count} required; nearest miss on {what} "
                         f"was {best}")


def _closest(baseline: Session, wanted: List[str], tips) -> str:
    best = None
    for eid in wanted:
        found = resolve_entity(baseline.doc, eid)
        if found is None:
            continue
        entity, owner, _ref, _space = found
        for tip in tips:
            distance = entity_distance(owner, entity, tip)
            if best is None or distance < best[1]:
                best = (eid, distance, tip)
    if best is None:
        return "no candidate entity resolved"
    return (f"{best[0]} at {best[1]:.2f} ft from [{best[2][0]:.1f}, {best[2][1]:.1f}] "
            f"(needed {TOLERANCE_FT:.2f} ft)")


def aimed_at_point(baseline: Session, submitted: Session, point, what: str,
                   must_contain: Optional[str] = None) -> Result:
    """Did the added linework put a tip on ``point``, and say the right thing?"""
    added = added_entities(baseline, submitted)
    if not added:
        return Result(False, "nothing was added to the document")
    texts = [e for e in added if isinstance(e, Text)]
    if not texts:
        return Result(False, "no text, so nothing is labelled")
    tips = leader_tips(added)
    if not tips:
        return Result(False, f"no leader, so nothing points at {what}")
    best = min((((tip[0] - point[0]) ** 2 + (tip[1] - point[1]) ** 2) ** 0.5, tip)
               for tip in tips)
    if best[0] > TOLERANCE_FT:
        return Result(False, f"nearest leader tip is {best[0]:.2f} ft from {what} at "
                             f"[{point[0]:.1f}, {point[1]:.1f}] (needed "
                             f"{TOLERANCE_FT:.2f} ft)")
    if must_contain and not any(must_contain in e.content for e in texts):
        return Result(False, f"the leader is on {what} but no text reads "
                             f"{must_contain!r}; found "
                             f"{[e.content for e in texts][:3]}")
    return Result(True, f"leader lands {best[0]:.2f} ft from {what}"
                        + (f" and the text carries {must_contain!r}" if must_contain
                           else ""))


def callout_at(session: Session, eid: str, where="mid", content="EP", dy=-150.0):
    """The scripted solution: aim by entity, put the text clear of it."""
    if "V-ANNO-TEXT" not in session.doc.layers:
        session.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    point = point_at(*_entity_and_owner(session, eid), where)[0]
    r = session.execute("place_callout", {
        "space": "model", "target_entity": eid, "at": where,
        "position": [point[0] + 150.0, point[1] + dy], "content": content,
        "layer": "V-ANNO-TEXT"})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])


def _entity_and_owner(session: Session, eid: str):
    found = resolve_entity(session.doc, eid)
    if found is None:
        raise RuntimeError(f"no entity {eid}")
    return found[1], found[0]


# -------------------------------------------------------------------- probes


def _edges(session, **extra):
    return targets(session, anchor={"kind": "offset",
                                    "offset": list(fixture.EDGE_OFFSETS)}, **extra)


def _check_edge_on_sheet(sheet):
    def check(baseline, submitted):
        return aimed_at(baseline, submitted, _edges(baseline, visible_on=sheet),
                        f"a pavement edge on {sheet}")
    return check


def _solve_edge_on_sheet(sheet):
    def solve(session):
        callout_at(session, _edges(session, visible_on=sheet)[0],
                   content="EDGE OF PAVEMENT")
    return solve


def _check_curved_edge(baseline, submitted):
    wanted = targets(baseline, anchor={"kind": "offset",
                                       "offset": list(fixture.EDGE_OFFSETS)},
                     type="arc", visible_on="C-102")
    return aimed_at(baseline, submitted, wanted, "the curved pavement edge on C-102")


def _solve_curved_edge(session):
    wanted = targets(session, anchor={"kind": "offset",
                                      "offset": list(fixture.EDGE_OFFSETS)},
                     type="arc", visible_on="C-102")
    callout_at(session, wanted[0], content="EDGE OF PAVEMENT (CURVE)")


def _check_shoulder(baseline, submitted):
    wanted = targets(baseline, anchor={"kind": "offset", "offset": -20.0},
                     visible_on="C-101")
    return aimed_at(baseline, submitted, wanted, "the left shoulder on C-101")


def _solve_shoulder(session):
    wanted = targets(session, anchor={"kind": "offset", "offset": -20.0},
                     visible_on="C-101")
    callout_at(session, wanted[0], content="SHOULDER 20' LT")


def _check_centerline(baseline, submitted):
    wanted = targets(baseline, anchor={"kind": "element"}, visible_on="C-103")
    return aimed_at(baseline, submitted, wanted, "the SR-100 centerline on C-103")


def _solve_centerline(session):
    wanted = targets(session, anchor={"kind": "element"}, visible_on="C-103")
    callout_at(session, wanted[0], content="SR-100 CENTERLINE")


def _check_both_edges(baseline, submitted):
    left = targets(baseline, anchor={"kind": "offset", "offset": -12.0},
                   visible_on="C-101")
    right = targets(baseline, anchor={"kind": "offset", "offset": 12.0},
                    visible_on="C-101")
    one = aimed_at(baseline, submitted, left, "the left pavement edge on C-101")
    if not one.passed:
        return Result(False, "left edge: " + one.detail)
    two = aimed_at(baseline, submitted, right, "the right pavement edge on C-101")
    if not two.passed:
        return Result(False, "right edge: " + two.detail)
    return Result(True, f"both edges: {one.detail}; {two.detail}")


def _solve_both_edges(session):
    left = targets(session, anchor={"kind": "offset", "offset": -12.0},
                   visible_on="C-101")
    right = targets(session, anchor={"kind": "offset", "offset": 12.0},
                    visible_on="C-101")
    callout_at(session, left[0], content="EP 12' LT", dy=200.0)
    callout_at(session, right[0], content="EP 12' RT", dy=-200.0)


def _check_title_blocks(baseline, submitted):
    missing = []
    for sheet in submitted.doc.sheets.values():
        fields = sheet.title_block_fields or {}
        for key, value in TITLE_FIELDS.items():
            actual = str(fields.get(key, "")).strip()
            if key == "sheet_title":
                if not actual:
                    missing.append(f"{sheet.name}.{key} empty")
            elif actual.upper() != value.upper():
                missing.append(f"{sheet.name}.{key}={actual!r} (wanted {value!r})")
    if missing:
        return Result(False, "; ".join(missing[:4]))
    return Result(True, f"all {len(submitted.doc.sheets)} title blocks carry the "
                        f"project, sheet title and scale")


def _solve_title_blocks(session):
    for sheet in session.doc.sheets.values():
        session.execute("fill_title_block", {
            "sheet": sheet.name,
            "fields": {**TITLE_FIELDS, "sheet_title": f"ROADWAY PLAN {sheet.name}"}})


def _pc_of_the_first_curve(session: Session) -> dict:
    """Where the PC is, and how its station reads -- through the reference."""
    r = session.query("resolve_anchor", {"alignment": f"DESIGN:{fixture.ALIGNMENT}",
                                         "anchor": "PC-1"})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return r


def _check_pc_by_station(baseline, submitted):
    pc = _pc_of_the_first_curve(baseline)
    return aimed_at_point(baseline, submitted, pc["point"],
                          "the PC of the first curve", must_contain=pc["station_text"])


def _solve_pc_by_station(session):
    pc = _pc_of_the_first_curve(session)
    if "V-ANNO-TEXT" not in session.doc.layers:
        session.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    r = session.execute("place_callout", {
        "space": "model", "target": pc["point"],
        "position": [pc["point"][0] + 200.0, pc["point"][1] - 200.0],
        "content": pc["auto_content"], "layer": "V-ANNO-TEXT"})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])


PROBES: List[Probe] = [
    Probe(id="edge-c102",
          prompt="On sheet C-102, add a callout pointing at the edge of pavement.",
          check=_check_edge_on_sheet("C-102"), solve=_solve_edge_on_sheet("C-102"),
          tags=["find", "reference"],
          note="The design is in the referenced basefile, so the sheet file owns "
               "no geometry to look at."),
    Probe(id="edge-curve-c102",
          prompt="On sheet C-102, call out the edge of pavement where SR-100 curves. "
                 "The leader must point at the curved edge itself.",
          check=_check_curved_edge, solve=_solve_curved_edge,
          tags=["find", "curve"],
          note="The trap: the midpoint of an arc's endpoints is 15.5 ft off the arc "
               "on this alignment, which fails the 1 ft tolerance."),
    Probe(id="shoulder-c101",
          prompt="Call out the left shoulder on sheet C-101.",
          check=_check_shoulder, solve=_solve_shoulder,
          tags=["find", "discriminate"],
          note="Shoulder is 20 ft, pavement edge is 12 ft; aiming at the wrong "
               "parallel line fails."),
    Probe(id="centerline-c103",
          prompt="Call out the SR-100 centerline on sheet C-103.",
          check=_check_centerline, solve=_solve_centerline,
          tags=["find", "discriminate"]),
    Probe(id="both-edges-c101",
          prompt="On sheet C-101, call out both edges of pavement -- one callout on "
                 "the left edge and one on the right.",
          check=_check_both_edges, solve=_solve_both_edges,
          tags=["find", "multiple"]),
    Probe(id="title-blocks",
          prompt="Populate the title block on every sheet: project SR-100 WIDENING, "
                 "a sheet title, and the scale 1\" = 50'.",
          check=_check_title_blocks, solve=_solve_title_blocks,
          tags=["sheets"],
          note="No geometry to find; checks that 'every sheet' is taken literally."),
    Probe(id="pc-by-station",
          prompt="Call out the PC of the first curve of SR-100 on sheet C-102, "
                 "labelled with its station.",
          check=_check_pc_by_station, solve=_solve_pc_by_station,
          tags=["find", "station", "reference-design"],
          note="Needs the referenced design: resolve_anchor on 'DESIGN:SR-100' "
               "gives the PC in host coordinates and the station text to write. "
               "There is no entity at a PC, so the point is the only way in."),
]

BY_ID = {probe.id: probe for probe in PROBES}


def get(probe_id: str) -> Probe:
    if probe_id not in BY_ID:
        raise KeyError(f"no probe {probe_id!r}; probes: {', '.join(BY_ID)}")
    return BY_ID[probe_id]


__all__ = ["TOLERANCE_FT", "TITLE_FIELDS", "Probe", "Result", "PROBES", "BY_ID", "get",
           "added_entities", "leader_tips", "targets", "aimed_at", "callout_at"]

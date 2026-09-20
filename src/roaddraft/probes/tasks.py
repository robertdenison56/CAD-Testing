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

Aim is always judged in the model, in feet. A callout drawn on a sheet -- where
plan annotation belongs -- has its leader tips carried back through the
viewport they sit in before they are measured, so paper-space and model-space
work are held to the same 1 ft. The ``-paper`` probes additionally require the
work to be on the sheet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from roaddraft.api.session import Session
from roaddraft.document import viewmap
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


def added_by_space(baseline: Session, submitted: Session, on_sheet: Optional[str] = None):
    """``(space key, entity)`` for what the submission added to the fixture.
    ``on_sheet`` keeps only what was drawn on that sheet's paper."""
    before = set(baseline.doc.model_entities)
    for sheet in baseline.doc.sheets.values():
        before |= set(sheet.entities)
    out = []
    if on_sheet is None:
        out += [("model", e) for eid, e in submitted.doc.model_entities.items()
                if eid not in before]
    for key, sheet in submitted.doc.sheets.items():
        if on_sheet is None or sheet.name == on_sheet:
            out += [(key, e) for eid, e in sheet.entities.items() if eid not in before]
    return out


def added_entities(baseline: Session, submitted: Session, on_sheet: Optional[str] = None):
    """Entities in the submitted document that the fixture did not have."""
    return [e for _space, e in added_by_space(baseline, submitted, on_sheet)]


def leader_tips(entities):
    """Both ends of every added line/polyline: a leader tip is one of them."""
    tips = []
    for e in entities:
        if isinstance(e, Line):
            tips += [e.start, e.end]
        elif isinstance(e, Polyline) and e.vertices:
            tips += [e.vertices[0], e.vertices[-1]]
    return tips


def model_tips(submitted: Session, added) -> list:
    """Leader tips in model feet. A tip drawn on a sheet is carried back
    through the viewport it sits in; one outside every viewport points at
    nothing in the model and is dropped."""
    tips = []
    for space, entity in added:
        sheet = submitted.doc.sheets.get(space)
        for tip in leader_tips([entity]):
            if sheet is None:
                tips.append(tip)
                continue
            vp = viewmap.viewport_under(sheet, tip)
            if vp is not None:
                tips.append(vp.transform().to_model(tip))
    return tips


def _nothing_added(on_sheet: Optional[str]) -> str:
    if on_sheet:
        return (f"nothing was drawn on sheet {on_sheet} itself -- this probe wants the "
                f"callout in paper space, not in the model")
    return "nothing was added to the document"


def targets(session: Session, **find) -> List[str]:
    """Ids of the entities a probe considers correct to point at."""
    r = session.query("find_entities", {**find, "limit": 500})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return [row["id"] for row in r["entities"]]


def aimed_at(baseline: Session, submitted: Session, wanted: List[str],
             what: str, count: int = 1, on_sheet: Optional[str] = None) -> Result:
    """Did the added linework put ``count`` tips within tolerance of ``wanted``?"""
    added = added_by_space(baseline, submitted, on_sheet)
    if not added:
        return Result(False, _nothing_added(on_sheet))
    if not any(isinstance(e, Text) for _space, e in added):
        return Result(False, f"{len(added)} entities added but no text, so nothing "
                             f"is labelled")
    tips = model_tips(submitted, added)
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
                   must_contain: Optional[str] = None,
                   on_sheet: Optional[str] = None) -> Result:
    """Did the added linework put a tip on ``point``, and say the right thing?"""
    added = added_by_space(baseline, submitted, on_sheet)
    if not added:
        return Result(False, _nothing_added(on_sheet))
    texts = [e for _space, e in added if isinstance(e, Text)]
    if not texts:
        return Result(False, "no text, so nothing is labelled")
    tips = model_tips(submitted, added)
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


def _paper_layer(session: Session) -> str:
    if "S-ANNO-CALL" not in session.doc.layers:
        session.execute("create_layer", {"name": "S-ANNO-CALL", "color": "black"})
    return "S-ANNO-CALL"


def _check_edge_on_paper(baseline, submitted):
    return aimed_at(baseline, submitted, _edges(baseline, visible_on="C-102"),
                    "a pavement edge on C-102", on_sheet="C-102")


def _solve_edge_on_paper(session):
    """The T2 route, start to finish: find what the sheet shows, name it, and
    let the engine see it through the viewport."""
    r = session.query("find_entities", {
        "anchor": {"kind": "offset", "offset": list(fixture.EDGE_OFFSETS)},
        "visible_on": "C-102"})
    row = r["entities"][0]
    x, y = row["sheet_point"]
    r = session.execute("place_callout", {
        "space": "C-102", "target_entity": row["id"], "position": [x + 2.5, y - 2.0],
        "content": "EDGE OF PAVEMENT", "layer": _paper_layer(session)})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])


STATION_PROBE = {"station": "18+00", "offset": 12.0, "anchor": "18+00@12R"}


def _station_point(session: Session) -> dict:
    r = session.query("station_to_xy", {
        "alignment": f"DESIGN:{fixture.ALIGNMENT}", "station": STATION_PROBE["station"],
        "offset": STATION_PROBE["offset"], "sheet": "C-101"})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return r


def _check_station_on_paper(baseline, submitted):
    return aimed_at_point(baseline, submitted, _station_point(baseline)["point"],
                          "SR-100 18+00, 12' RT", must_contain="18+00",
                          on_sheet="C-101")


def _solve_station_on_paper(session):
    at = _station_point(session)
    x, y = at["on_sheet"]["sheet_point"]
    r = session.execute("place_callout", {
        "space": "C-101", "target_anchor": STATION_PROBE["anchor"],
        "alignment": f"DESIGN:{fixture.ALIGNMENT}", "position": [x + 2.0, y - 2.5],
        "content": f"STA {at['station_text']}, 12.00' RT\nBEGIN GUARDRAIL",
        "layer": _paper_layer(session)})
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
          prompt="Call out the PC of the first curve of SR-100 on sheet C-101, "
                 "labelled with its station.",
          check=_check_pc_by_station, solve=_solve_pc_by_station,
          tags=["find", "station", "reference-design"],
          note="Needs the referenced design: resolve_anchor on 'DESIGN:SR-100' "
               "gives the PC in host coordinates and the station text to write. "
               "There is no entity at a PC, so the point is the only way in."),
    Probe(id="edge-c102-paper",
          prompt="On sheet C-102, call out the edge of pavement. Draw the callout on "
                 "the sheet itself, in paper space, the way plan annotation is drawn "
                 "-- not in the model.",
          check=_check_edge_on_paper, solve=_solve_edge_on_paper,
          tags=["find", "reference", "paper"],
          note="The T2 shape. The edge is in a referenced basefile and the callout is "
               "in paper inches, so the tip has to go through the viewport. The leader "
               "tip is carried back to the model and held to the same 1 ft."),
    Probe(id="sta-offset-c101-paper",
          prompt="On sheet C-101, in paper space, call out the point 12 ft right of "
                 "SR-100 station 18+00 as BEGIN GUARDRAIL, with the station in the "
                 "text.",
          check=_check_station_on_paper, solve=_solve_station_on_paper,
          tags=["station", "reference-design", "paper"],
          note="How most real plan callouts are aimed: a station and an offset, with "
               "no entity there to find. 1 ft is 0.02 in on this sheet."),
]

BY_ID = {probe.id: probe for probe in PROBES}


def get(probe_id: str) -> Probe:
    if probe_id not in BY_ID:
        raise KeyError(f"no probe {probe_id!r}; probes: {', '.join(BY_ID)}")
    return BY_ID[probe_id]


__all__ = ["TOLERANCE_FT", "TITLE_FIELDS", "Probe", "Result", "PROBES", "BY_ID", "get",
           "added_entities", "added_by_space", "leader_tips", "model_tips", "targets",
           "aimed_at", "aimed_at_point", "callout_at"]

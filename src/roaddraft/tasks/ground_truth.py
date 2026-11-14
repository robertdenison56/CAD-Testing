"""Ground truth for a task and matching a document against it (spec section 7.5).

``compute_ground_truth`` rebuilds the alignment from the brief and calls the
same ``stationing_plan`` / ``compile_label`` / ``curve_table_rows`` the
commands use, with the deliverable's sizes, so a reference solution matches
the truth exactly.  The truth covers the whole finished drawing; ``scope``
says which of its groups the task asks for (``tasks.types``), and the
verifier grades only those.  ``match_truth`` is E0's whole-drawing check:
every anchored label by ``(alignment, ref, kind)``, content and position.
"""
from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import (
    LABEL_KINDS, LabelSpec, TickSpec, compile_label, curve_table_rows, stationing_plan,
)
from roaddraft.core.units import format_length
from roaddraft.design.model import DesignModel
from roaddraft.design.offsets import offset_pieces
from roaddraft.document.document import Document
from roaddraft.document.entities import Text
from roaddraft.tasks.brief import GroundTruth, TaskBrief
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import GROUPS, OPEN_BREAKS, task_type


#: what a real plan sheet's deliverable adds to its truth sheet (tasks.real): its border,
#: the viewport twist the layout must keep, its own title block fields (which must be
#: filled, and which a prompt level states), and its north arrow's place and turn
REAL_SHEET_KEYS = ("template", "twist_deg", "required_title_fields", "title_stated",
                   "north_arrow")


def _label_row(spec: LabelSpec, layer: str, height: float) -> dict:
    return {"kind": spec.kind, "alignment": spec.alignment, "anchor": spec.ref,
            "content": spec.content, "station": float(spec.station), "space": "model",
            "side": spec.side, "label_offset": float(spec.label_offset),
            "rotation": spec.rotation, "position": [float(spec.position[0]),
                                                    float(spec.position[1])],
            "rotation_deg": float(spec.rotation_deg), "halign": spec.halign,
            "valign": spec.valign, "layer": layer, "height": float(height), "required": True,
            **({"view_rotation": float(spec.view_rotation)} if spec.view_rotation else {})}


def sheet_rows(align: Alignment, D: dict, S: dict, name: str) -> Tuple[List[dict], List[dict], set]:
    """``(curve tables, sheets, match stations)`` of a truth, from the sheets a
    deliverable lists: each sheet's viewport, stretch, title block and match
    lines, and the curve table of each sheet that shows a curve.  Its own
    function so that a layout whose breaks the drafter chose (``tasks.breaks``)
    is given its truth by the same derivation as the generator's own."""
    layers = S["layers"]
    table_anchor = {"alignment": name, "ref": "CURVES", "kind": "curve_table"}
    curve_tables: List[dict] = []
    sheets: List[dict] = []
    match_stations = set()
    for sh in D["sheets"]:
        if sh["curves"]:  # a sheet that shows no curve carries no curve table
            headers, rows, widths = curve_table_rows(align, D["curve_table_columns"],
                                                     curves=sh["curves"])
            curve_tables.append({
                "sheet": sh["name"], "curves": list(sh["curves"]),
                "columns": list(D["curve_table_columns"]), "headers": headers, "rows": rows,
                "widths": widths, "position": list(sh["curve_table_position"]),
                "text_height": float(D["text_heights"]["sheet_table_in"]),
                "title": S["curve_table"]["title"], "layer": layers["tables"],
                "anchor": dict(table_anchor)})
        matches = []
        for m in sh.get("matches", []):
            half = float(m["half_width_ft"])
            matches.append({
                "station": float(m["station"]), "station_text": m["station_text"],
                "start": align.station_to_xy(m["station"], -half)[0],
                "end": align.station_to_xy(m["station"], half)[0],
                "half_width_ft": half, "layer": layers.get("match", layers["ticks"]),
                "label": m["label"],
                "other_sheet": m["other_sheet"], "side": m["side"],
                "label_offset_in": float(m["label_offset_in"]), "rotation": m["rotation"]})
            match_stations.add(float(m["station"]))
        extra = {k: sh[k] for k in REAL_SHEET_KEYS if k in sh}
        sheets.append({**extra, "name": sh["name"], "size": sh["size"],
                       "feet_per_inch": float(D["feet_per_inch"]),
                       "viewport": dict(sh["viewport"]),
                       "station_range": list(sh["station_range"]), "curves": list(sh["curves"]),
                       "north_arrow_block": S["sheet"]["north_arrow"]["block"],
                       "north_arrow_layer": layers.get("symbols", "0"),
                       "title_block_fields": dict(sh["title_block_fields"]),
                       "matches": matches})
    return curve_tables, sheets, match_stations


def compute_ground_truth(brief: TaskBrief) -> GroundTruth:
    D = brief.deliverable
    S = brief.drafting_spec
    name = brief.alignment_name
    align = Alignment.from_dict(brief.design["alignments"][name])
    layers = S["layers"]
    height = float(D["text_heights"]["model_label_ft"])
    label_offset = float(D["label_offset_ft"])
    # a real sheet's viewport is twisted: its model labels read upright on the sheet
    vr = float(D.get("view_rotation") or 0.0)
    # a real sheet's labels sit where they clear its existing work (tasks.real): the
    # station numbers' side, and each curve point, bearing and bubble's side and offset
    poses = D.get("label_poses") or {}

    def posed(spec: LabelSpec, group: str) -> LabelSpec:
        pz = (poses.get(group) or {}).get(spec.ref)
        if not pz:
            return spec
        ap = resolve_anchor(align, parse_anchor(spec.ref))
        return compile_label(align, ap, spec.kind, side=pz["side"],
                             label_offset=float(pz["label_offset_ft"]), content=spec.content,
                             view_rotation=vr)

    plan = stationing_plan(align, interval=float(D["stationing_interval_ft"]),
                           tick_half=float(D["tick_half_len_ft"]), label_offset=label_offset,
                           lettering=D.get("station_lettering", "caltrans"),
                           station_side=poses.get("station_side") or D.get("station_label_side"),
                           point_offset=float(D.get("point_label_offset_ft", label_offset)),
                           view_rotation=vr)
    labels: List[dict] = []
    ticks: List[dict] = []
    for item in plan.items:
        if isinstance(item, TickSpec):
            ticks.append({"station": float(item.station), "station_text": item.station_text,
                          "start": list(item.start), "end": list(item.end),
                          "layer": layers["ticks"]})
        else:
            labels.append(_label_row(posed(item, "points"), layers["labels"], height))
    bearing_offset = float(D.get("bearing_label_offset_ft", label_offset))
    for n in range(1, len(align.tangents()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"T-{n}"))
        labels.append(_label_row(posed(compile_label(align, ap, "bearing",
                                                     label_offset=bearing_offset,
                                                     view_rotation=vr), "bearings"),
                                 layers["labels"], height))
    mc_offset = float(D.get("mc_label_offset_ft", label_offset))
    for n in range(1, len(align.curves()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"MC-{n}"))
        labels.append(_label_row(posed(compile_label(align, ap, "mc", label_offset=mc_offset,
                                                     view_rotation=vr), "callouts"),
                                 layers["labels"], height))

    elements = [{"ref": align.element_ref(i), "kind": el.kind, "layer": layers["alignment"]}
                for i, el in enumerate(align.elements)]
    curve_tables, sheets, match_stations = sheet_rows(align, D, S, name)
    # -- plan prep: pavement edges, width dimensions, the base drawing, the layer set
    pave = D.get("pavement") or {}
    edges: List[dict] = []
    for value in pave.get("offsets_ft", []):
        for piece in offset_pieces(align, float(value), None):
            row = {"ref": piece.ref, "kind": piece.kind, "station": float(piece.station),
                   "offset": float(piece.offset), "layer": pave["layer"]}
            if piece.kind == "tangent":
                row.update(start=list(piece.start), end=list(piece.end))
            else:
                row.update(center=list(piece.center), radius=float(piece.radius),
                           start_angle_deg=float(piece.start_angle_deg),
                           end_angle_deg=float(piece.end_angle_deg))
            edges.append(row)
    dimensions: List[dict] = []
    half = float(pave.get("half_width_ft") or 0.0)
    tangents = align.tangents()
    for wd in D.get("width_dimensions", []):
        raw = float(wd["station"])
        t = tangents[int(wd["ref"].split("-")[1]) - 1]
        dimensions.append({
            "ref": wd["ref"], "station": raw, "station_text": wd["station_text"],
            "p1": align.station_to_xy(raw, -half)[0], "p2": align.station_to_xy(raw, half)[0],
            "value": 2.0 * half, "text": format_length(2.0 * half, "feet", 2),
            "tangent_range": [float(align.begin_station + t.start_dist),
                              float(align.begin_station + t.end_dist)],
            "layer": D.get("dims_layer", layers.get("dims"))})
    # a real sheet's construction callouts: each note's tip from its station and offset on
    # its line, in the model and on the paper through the sample sheet's viewport
    # (tasks.real).  The verifier judges the tip through the viewport the drafter's sheet
    # is drawn through (d1-verify-v8, checks.expected_callout_tip); tip_paper is the
    # task's own projection, for a reader of the truth and for a sheet with no viewport yet
    callouts: List[dict] = []
    for c in D.get("callouts") or []:
        on = Alignment.from_dict(brief.design["alignments"][c["alignment"]])
        tip = on.station_to_xy(float(c["station"]), float(c["offset"]))[0]
        vp = D["sheets"][0]["viewport"]
        t = geo.ViewportTransform(vp["center_paper"], vp["model_center"], vp["feet_per_inch"],
                              vp.get("rotation_deg", 0.0))
        row = dict(c)
        row.update(sheet=D["sheets"][0]["name"], tip_model=[float(tip[0]), float(tip[1])],
                   tip_paper=[float(v) for v in t.to_paper(tip)])
        callouts.append(row)
    references: List[dict] = [dict(r) for r in D.get("references") or []]
    if D.get("basefile"):
        ref_spec = S.get("reference", {})
        references.append({"file": D["basefile"], "name": ref_spec.get("name", "BASE"),
                           "space": ref_spec.get("space", "model")})
    asks = task_type(D.get("task_type", "plan-sheet")).asks
    scope = [g for g in GROUPS if g in asks]
    if OPEN_BREAKS in asks:  # the breaks are the drafter's: graded by verify.breaks
        scope.append(OPEN_BREAKS)
    counts = {"labels": len(labels), "ticks": len(ticks), "curves": len(align.curves()),
              "tangents": len(align.tangents()), "equations": len(align.equations),
              "sheets": len(sheets), "match_lines": len(match_stations), "edges": len(edges),
              "dimensions": len(dimensions), "references": len(references),
              "callouts": len(callouts)}
    fingerprint = DesignModel.from_dict({"alignments": brief.design["alignments"],
                                         "profiles": brief.design["profiles"]}).fingerprint()
    return GroundTruth(task_id=brief.task_id, design_fingerprint=fingerprint, labels=labels,
                       ticks=ticks, elements=elements, curve_tables=curve_tables, sheets=sheets,
                       edges=edges, dimensions=dimensions, callouts=callouts,
                       references=references,
                       layers=list(S.get("layer_set") or dict.fromkeys(layers.values())),
                       alignments=copy.deepcopy(brief.design["alignments"]), scope=scope,
                       counts=counts)


def _descriptor(label: dict) -> str:
    return f"{label['kind']} @ {label['anchor']} of {label['alignment']}"


def match_truth(doc: Document, truth: GroundTruth,
                position_tolerance: Optional[float] = None) -> dict:
    """Compare a document's anchored labels with the whole truth.

    A truth label matches an entity when ``(anchor.alignment, anchor.ref,
    anchor.kind)`` are equal, the content is equal, and the position is within
    ``position_tolerance`` (default: the spec's ``position_model_ft``).
    """
    tol = (DRAFTING_SPEC_V1["tolerances"]["position_model_ft"]
           if position_tolerance is None else float(position_tolerance))
    by_key: Dict[Tuple[str, str, str], List[Text]] = {}
    for e in list(doc.model_entities.values()):
        if isinstance(e, Text) and e.anchor and e.anchor.get("kind") in LABEL_KINDS:
            key = (e.anchor.get("alignment"), e.anchor.get("ref"), e.anchor.get("kind"))
            by_key.setdefault(key, []).append(e)
    matched = 0
    missing: List[str] = []
    content_mismatch: List[dict] = []
    position_mismatch: List[dict] = []
    used = set()
    for label in truth.labels:
        key = (label["alignment"], label["anchor"], label["kind"])
        cands = by_key.get(key, [])
        if not cands:
            missing.append(_descriptor(label))
            continue
        e = cands[0]
        used.add(e.id)
        if e.content != label["content"]:
            content_mismatch.append({"label": _descriptor(label), "id": e.id,
                                     "expected": label["content"], "actual": e.content})
        elif geo.distance(e.position, label["position"]) > tol:
            position_mismatch.append({"label": _descriptor(label), "id": e.id,
                                      "expected": label["position"],
                                      "actual": list(e.position),
                                      "distance": geo.distance(e.position, label["position"])})
        else:
            matched += 1
    truth_keys = {(l["alignment"], l["anchor"], l["kind"]) for l in truth.labels}
    extra = [e.id for key, ents in by_key.items() if key not in truth_keys for e in ents]
    extra += [e.id for key, ents in by_key.items() if key in truth_keys
              for e in ents[1:]]  # duplicates
    return {"matched": matched, "missing": missing, "extra": sorted(extra),
            "content_mismatch": content_mismatch, "position_mismatch": position_mismatch}


__all__ = ["compute_ground_truth", "sheet_rows", "match_truth"]

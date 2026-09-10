"""Ground truth for a task and matching a document against it (spec section 7.5).

``compute_ground_truth`` rebuilds the alignment from the brief and calls the
same ``stationing_plan`` / ``compile_label`` / ``curve_table_rows`` the
commands use, with the deliverable's sizes, so a reference solution matches
the truth exactly.  ``match_truth`` compares a document's anchored labels
with the truth by ``(alignment, ref, kind)``, content and position.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import (
    LABEL_KINDS, LabelSpec, TickSpec, compile_label, curve_table_rows, stationing_plan,
)
from roaddraft.design.model import DesignModel
from roaddraft.document.document import Document
from roaddraft.document.entities import Text
from roaddraft.tasks.brief import GroundTruth, TaskBrief
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1


def _label_row(spec: LabelSpec, layer: str, height: float) -> dict:
    return {"kind": spec.kind, "alignment": spec.alignment, "anchor": spec.ref,
            "content": spec.content, "station": float(spec.station), "space": "model",
            "side": spec.side, "label_offset": float(spec.label_offset),
            "rotation": spec.rotation, "position": [float(spec.position[0]),
                                                    float(spec.position[1])],
            "rotation_deg": float(spec.rotation_deg), "halign": spec.halign,
            "valign": spec.valign, "layer": layer, "height": float(height), "required": True}


def compute_ground_truth(brief: TaskBrief) -> GroundTruth:
    D = brief.deliverable
    S = brief.drafting_spec
    name = brief.alignment_name
    align = Alignment.from_dict(brief.design["alignments"][name])
    layers = S["layers"]
    height = float(D["text_heights"]["model_label_ft"])
    label_offset = float(D["label_offset_ft"])

    plan = stationing_plan(align, interval=float(D["stationing_interval_ft"]),
                           tick_half=float(D["tick_half_len_ft"]), label_offset=label_offset)
    labels: List[dict] = []
    ticks: List[dict] = []
    for item in plan.items:
        if isinstance(item, TickSpec):
            ticks.append({"station": float(item.station), "station_text": item.station_text,
                          "start": list(item.start), "end": list(item.end),
                          "layer": layers["ticks"]})
        else:
            labels.append(_label_row(item, layers["labels"], height))
    bearing_offset = float(D.get("bearing_label_offset_ft", label_offset))
    for n in range(1, len(align.tangents()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"T-{n}"))
        labels.append(_label_row(compile_label(align, ap, "bearing", label_offset=bearing_offset),
                                 layers["labels"], height))
    for n in range(1, len(align.curves()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"MC-{n}"))
        labels.append(_label_row(compile_label(align, ap, "mc", label_offset=label_offset),
                                 layers["labels"], height))

    elements = [{"ref": align.element_ref(i), "kind": el.kind, "layer": layers["alignment"]}
                for i, el in enumerate(align.elements)]
    headers, rows, widths = curve_table_rows(align, D["curve_table_columns"])
    curve_table = {"space": D["sheet_name"], "columns": list(D["curve_table_columns"]),
                   "headers": headers, "rows": rows, "widths": widths,
                   "position": list(D["curve_table_position"]),
                   "text_height": float(D["text_heights"]["sheet_table_in"]),
                   "title": S["curve_table"]["title"], "layer": layers["tables"],
                   "anchor": {"alignment": name, "ref": "CURVES", "kind": "curve_table"}}
    sheet = {"name": D["sheet_name"], "size": D["sheet_size"],
             "feet_per_inch": float(D["feet_per_inch"]), "viewport": dict(D["viewport"]),
             "north_arrow_block": S["sheet"]["north_arrow"]["block"],
             "title_block_fields": dict(D["title_block_fields"])}
    counts = {"labels": len(labels), "ticks": len(ticks), "curves": len(align.curves()),
              "tangents": len(align.tangents()), "equations": len(align.equations)}
    fingerprint = DesignModel.from_dict({"alignments": brief.design["alignments"],
                                         "profiles": brief.design["profiles"]}).fingerprint()
    return GroundTruth(task_id=brief.task_id, design_fingerprint=fingerprint, labels=labels,
                       ticks=ticks, elements=elements, curve_table=curve_table, sheet=sheet,
                       counts=counts)


def _descriptor(label: dict) -> str:
    return f"{label['kind']} @ {label['anchor']} of {label['alignment']}"


def match_truth(doc: Document, truth: GroundTruth,
                position_tolerance: Optional[float] = None) -> dict:
    """Compare a document's anchored labels with the truth.

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


__all__ = ["compute_ground_truth", "match_truth"]

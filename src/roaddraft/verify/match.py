"""Label matching (eval plan section 3.3): the core of D1-03 ... D1-07.

Every ``Text`` in model space and on the deliverable sheets is sorted into
one of three bins:

- **unanchored** -- no anchor, an anchor whose ``kind`` is not a label kind,
  or an anchor no anchoring command stamped (``placed_by`` absent or not in
  ``bus.ANCHOR_PRODUCERS``).  Listed once, informational, never matched: text
  earns credit only through anchors.
- **inconsistent** -- a trusted anchor on one of the truth's alignments that
  does not hold together: the ref does not resolve, the kind does not fit
  the ref, the recorded station disagrees with the ref, or a sheet label names
  a viewport its sheet does not have.  This is what a hand-rewritten anchor
  looks like; it is reported (D1-07) and never matched.
- **candidates** -- the rest, keyed by ``(alignment, ref, kind)``.  For each
  the verifier recomputes the pose the entity's *own* anchor record implies
  (``compile_label``, then ``sheet_pose`` through the recorded viewport for a
  sheet label) and compares it with where the entity actually is.  A bearing
  anchored at a station inside a tangent is that tangent's bearing
  (d1-verify-v5, PE decision 2026-10-18): it is keyed and posed as ``T-n``, so it
  meets the truth's label and its placement is judged at the tangent's middle.

Each truth label the task asks for (its group is in scope) then takes the
best candidate under its key; any others are duplicates.  Matching is
space-agnostic: a label placed on a sheet through a viewport counts the same
as one in model space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.core import geometry as geo
from roaddraft.design.anchors import parse_anchor, resolve_record
from roaddraft.design.errors import DesignError
from roaddraft.design.labels import LABEL_KINDS, SHEET_LABEL_OFFSET, compile_label, sheet_pose
from roaddraft.document.entities import Text
from roaddraft.verify.context import Context, ViewportView
from roaddraft.verify.normalize import normalize
from roaddraft.verify.semantic import same_label

Key = Tuple[str, str, str]

#: which check scores a truth label of each kind (PE decision 2026-10-09:
#: equations score with the stations, C-n callouts with the curve points)
KIND_CHECK = {"station": "D1-03", "equation": "D1-03",
              "pc": "D1-04", "pt": "D1-04", "pcc": "D1-04", "prc": "D1-04", "mc": "D1-04",
              "bearing": "D1-05"}
#: the truth group each label kind belongs to (tasks.types)
KIND_GROUP = {"station": "stations", "equation": "stations",
              "pc": "curve_points", "pt": "curve_points", "pcc": "curve_points",
              "prc": "curve_points", "mc": "callouts", "bearing": "bearings"}


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two angles, degrees."""
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


@dataclass
class Candidate:
    entity: Text
    space: str  # "model" or the sheet id
    key: Key
    expected_position: List[float]
    expected_rotation: float
    placed: bool  # position and rotation agree with the anchor record
    view: Optional[ViewportView]  # model labels: the viewport they are seen through
    visible: bool
    station: Optional[float] = None  # the anchor's raw station

    @property
    def id(self) -> str:
        return self.entity.id

    def paper_height(self, ctx: Context) -> float:
        """Text height on paper, inches."""
        if self.space != "model":
            return float(self.entity.height)
        fpi = self.view.vp.feet_per_inch if self.view is not None else ctx.fpi_used
        return float(self.entity.height) / float(fpi)


@dataclass
class Inconsistent:
    entity: Text
    key: Key
    note: str


@dataclass
class LabelMatch:
    """One truth label and what the document offers for it."""

    truth: dict
    check: str
    exact: bool = True  # the prompt stated label formats: compare text, not meaning
    chosen: Optional[Candidate] = None
    duplicates: List[Candidate] = field(default_factory=list)

    @property
    def key(self) -> Key:
        return (self.truth["alignment"], self.truth["anchor"], self.truth["kind"])

    @property
    def anchor(self) -> dict:
        return {"alignment": self.truth["alignment"], "ref": self.truth["anchor"],
                "kind": self.truth["kind"]}

    def content_ok(self, cand: Candidate) -> bool:
        if self.exact:
            return normalize(cand.entity.content) == normalize(self.truth["content"])
        if same_label(self.truth["kind"], cand.entity.content, self.truth["content"]):
            return True
        # a station number lettered the Caltrans way (the ones digit) or in full:
        # the anchor ref is the full station text, so both read as the station
        return (self.truth["kind"] == "station"
                and same_label("station", cand.entity.content, self.truth["anchor"]))

    @property
    def credited(self) -> bool:
        return (self.chosen is not None and self.chosen.visible
                and self.content_ok(self.chosen))


@dataclass
class LabelIndex:
    by_key: Dict[Key, List[Candidate]] = field(default_factory=dict)
    inconsistent: List[Inconsistent] = field(default_factory=list)
    unanchored: List[Tuple[Text, str]] = field(default_factory=list)  # (entity, note)
    anchored: int = 0  # texts with a trusted anchor
    matches: List[LabelMatch] = field(default_factory=list)
    #: trusted custom-kind labels on each deliverable sheet (match-line labels live here)
    custom: Dict[str, List[Candidate]] = field(default_factory=dict)


def _texts(ctx: Context):
    for e in ctx.doc.model_entities.values():
        if isinstance(e, Text):
            yield "model", e
    for sv in ctx.sheets:
        if sv.sheet is not None:
            for e in sv.sheet.entities.values():
                if isinstance(e, Text):
                    yield sv.sheet.id, e


class _Bad(Exception):
    pass


def _expected_pose(ctx: Context, text: Text, space: str, rec: dict, align):
    """``(canonical ref, raw station, position, rotation, tolerance)`` the record implies."""
    kind = rec["kind"]
    try:
        ap = resolve_record(align, rec)
        named = parse_anchor(rec["ref"])
    except DesignError:
        raise _Bad("the anchor does not resolve on its alignment")
    if ap.kind_hint == "station":
        if named.kind_hint != "station" or named.ref != ap.ref:
            raise _Bad("the anchor's station and ref disagree")
    elif rec.get("station") is not None:
        if abs(float(rec["station"]) - float(ap.station)) > float(ctx.tol["station_ft"]):
            raise _Bad("the anchor's station and ref disagree")
    model_offset = rec.get("label_offset") if space == "model" else None
    try:
        spec = compile_label(align, ap, kind, side=rec.get("side"), label_offset=model_offset,
                             rotation=rec.get("rotation"), content=text.content,
                             view_rotation=float(rec.get("view_rotation") or 0.0))
    except DesignError:
        raise _Bad("the label kind does not fit the anchor")
    if space == "model":
        return (ap.ref, float(ap.station), spec.position, spec.rotation_deg,
                float(ctx.tol["position_model_ft"]))
    sv = ctx.sheet_view(space)
    vp = (sv.sheet.viewport_by_id(rec.get("viewport"))
          if sv is not None and rec.get("viewport") else None)
    if vp is None:
        raise _Bad("the anchor names no viewport on its sheet")
    offset = rec.get("label_offset")
    position, rotation = sheet_pose(spec, vp.transform(), vp.rotation_deg,
                                    SHEET_LABEL_OFFSET if offset is None else float(offset))
    return ap.ref, float(ap.station), position, rotation, float(ctx.tol["position_paper_in"])


def _as_tangent_bearing(ctx: Context, rec: dict, align) -> dict:
    """A bearing anchored at a station strictly inside a tangent, read as that
    tangent's ``T-n`` bearing; any other record unchanged.  The labelers accept a
    station for a bearing, and the task words it as the tangent's bearing at its
    middle, so the station is where on the tangent it was put, not which bearing."""
    if rec.get("kind") != "bearing":
        return rec
    try:
        ap = resolve_record(align, rec)
    except DesignError:
        return rec  # _expected_pose reports it as inconsistent
    if ap.kind_hint != "station" or ap.tangent_index is None:
        return rec
    t = align.tangents()[ap.tangent_index - 1]
    start = float(align.begin_station) + t.start_dist
    margin = float(ctx.tol["station_ft"])  # a station at a BC or EC is no tangent's
    if not start + margin < float(ap.station) < start + t.length - margin:
        return rec
    return {**rec, "ref": f"T-{ap.tangent_index}", "station": None}


def index_labels(ctx: Context) -> LabelIndex:
    """Bin every text and match the truth labels in scope (see the module docstring)."""
    idx = LabelIndex()
    rot_tol = float(ctx.tol["rotation_deg"])
    for space, text in _texts(ctx):
        rec = text.anchor
        if not rec:
            idx.unanchored.append((text, "text without an anchor earns no credit"))
            continue
        if rec.get("placed_by") not in ANCHOR_PRODUCERS:
            idx.unanchored.append((text, "the anchor was not placed by an anchoring command"))
            continue
        if rec.get("kind") not in LABEL_KINDS:
            idx.unanchored.append((text, "the anchor kind is not a label kind"))
            continue
        idx.anchored += 1
        found = ctx.truth_alignment(rec.get("alignment"))
        if found is None:
            continue  # anchored to an alignment the task did not ask for: an extra
        name, align = found  # the truth's name, however the anchor named it
        try:
            ref, station, position, rotation, tol = _expected_pose(
                ctx, text, space, _as_tangent_bearing(ctx, rec, align), align)
        except _Bad as bad:
            idx.inconsistent.append(Inconsistent(text, (name, rec["ref"], rec["kind"]), str(bad)))
            continue
        placed = (geo.distance(text.position, position) <= tol
                  and angle_diff(text.rotation_deg, rotation) <= rot_tol)
        if space == "model":
            view = ctx.model_view(text.position)
            visible = view is not None
        else:
            view = None
            visible = ctx.sheet_visible(space, text.position)
        key = (name, ref, rec["kind"])
        cand = Candidate(entity=text, space=space, key=key,
                         expected_position=[float(position[0]), float(position[1])],
                         expected_rotation=float(rotation), placed=placed, view=view,
                         visible=visible, station=station)
        if rec["kind"] == "custom" and space != "model":
            idx.custom.setdefault(space, []).append(cand)
        idx.by_key.setdefault(key, []).append(cand)

    for label in ctx.truth.labels:
        check = KIND_CHECK.get(label["kind"])
        if check is None or KIND_GROUP[label["kind"]] not in ctx.scope:
            continue
        m = LabelMatch(truth=label, check=check, exact=ctx.states("label_format"))
        cands = sorted(idx.by_key.get(m.key, []),
                       key=lambda c: (not m.content_ok(c), not c.visible, not c.placed, c.id))
        if cands:
            m.chosen, m.duplicates = cands[0], cands[1:]
        idx.matches.append(m)
    return idx


__all__ = ["KIND_CHECK", "KIND_GROUP", "Candidate", "Inconsistent", "LabelMatch", "LabelIndex",
           "index_labels", "angle_diff"]

"""What every check needs to know about the document under test, worked out once.

The deliverable sheets (each with its usable area, viewports and the part of
the alignment it must show), the given design, the task's scope and prompt
level.  Everything here is read from the document and the truth; nothing is
cached on either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.horizontal import Alignment, CurveElement
from roaddraft.design.model import DesignModel
from roaddraft.document.document import Document
from roaddraft.document.references import reference_alignments
from roaddraft.document.sheets import Sheet, Viewport
from roaddraft.tasks.brief import GroundTruth
from roaddraft.tasks.types import BASE_SCOPE, GROUPS

Rect = Tuple[float, float, float, float]

#: points sampled per curve when fitting an alignment into a viewport
_ARC_SAMPLES = 16
_STEP_FT = 10.0


def rect_contains(rect: Rect, p: Sequence[float], eps: float = 1e-9) -> bool:
    return rect[0] - eps <= p[0] <= rect[2] + eps and rect[1] - eps <= p[1] <= rect[3] + eps


def rect_inside(inner: Rect, outer: Rect, eps: float = 1e-9) -> bool:
    return (inner[0] >= outer[0] - eps and inner[1] >= outer[1] - eps
            and inner[2] <= outer[2] + eps and inner[3] <= outer[3] + eps)


def rect_intersection(a: Rect, b: Rect) -> Optional[Rect]:
    r = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return r if r[0] <= r[2] and r[1] <= r[3] else None


def truth_alignments(truth: GroundTruth) -> List[str]:
    """The alignments the truth is drawn from, primary first."""
    names: List[str] = []
    tables = [t.get("anchor", {}).get("alignment") for t in truth.curve_tables]
    notes = [c.get("alignment") for c in getattr(truth, "callouts", None) or []]
    for name in tables + [label["alignment"] for label in truth.labels] + notes:
        if name and name not in names:
            names.append(name)
    return names


def design_sources(doc: Document, names: Sequence[str]) -> List[Tuple[str, Optional[str], Alignment, DesignModel]]:
    """Where each of ``names`` lives: ``(name, qualified name or None,
    alignment, design model)`` -- this document's own design first, else an
    attached reference placed at identity whose design carries it (a sheet
    file that references its base drawing, labelled through ``BASE:ALIGN-1``).
    A name found nowhere is left out."""
    out = []
    refs = None
    for name in names:
        if name in doc.design.alignments:
            out.append((name, None, doc.design.alignments[name], doc.design))
            continue
        if refs is None:
            refs = list(reference_alignments(doc))
        for ref, base, align, placement in refs:
            if align.name == name and placement.is_identity:
                out.append((name, f"{ref.name}:{name}", align, base.design))
                break
    return out


def given_design(doc: Document, truth: GroundTruth) -> DesignModel:
    """The part of the design the task gave: the truth's alignments and the
    profiles bound to them, wherever they live (this document, or a base
    drawing it references at identity).  An alignment the agent added is not
    part of it, so creating one is not tampering (it just anchors nothing the
    truth asks for); renaming, editing or deleting a given one is."""
    names = truth_alignments(truth)
    model = DesignModel()
    for name, _qualified, align, design in design_sources(doc, names):
        model.alignments[name] = align
        for pname, profile in design.profiles.items():
            if profile.alignment == name:
                model.profiles[pname] = profile
    return model


def design_home(doc: Document, truth: GroundTruth) -> Optional[Document]:
    """The document the truth's design, the centerline drawn from it and its
    pavement edges are graded in (D1-15, D1-01, D1-12): ``doc`` itself, as
    always.  Only on a truth whose scope carries ``BASE_SCOPE`` (the revision
    dial's base-drawing flavour: the design is the drafter's to change where it
    lives, in the base drawing the sheet file references) is it that base
    drawing, read through the reference at identity that holds the truth's
    line -- or None when no attached reference does, and then nothing of the
    three is there to credit.  The sheet file's own design is not looked at on
    such a truth: a line created in it is not the base drawing's, changed."""
    if BASE_SCOPE not in (truth.scope or ()):
        return doc
    names = truth_alignments(truth)
    for _ref, base, align, placement in reference_alignments(doc):
        if names and align.name == names[0] and placement.is_identity:
            return base
    return None


def alignment_samples(align: Alignment) -> List[List[float]]:
    """Points along the centerline dense enough to fit-test it on paper."""
    pts: List[List[float]] = []
    for el in align.elements:
        pts.append(list(el.start))
        if isinstance(el, CurveElement):
            s, e = el.ccw_angles()
            s, e = geo.arc_sweep(s, e)
            for i in range(1, _ARC_SAMPLES):
                pts.append(geo.arc_point(el.center, el.radius, s + (e - s) * i / _ARC_SAMPLES))
        pts.append(list(el.end))
    return pts


def segment_samples(align: Alignment, lo_raw: float, hi_raw: float) -> List[List[float]]:
    """Centerline points between two raw stations, every 10 ft plus the ends."""
    begin = float(align.begin_station)
    lo = min(max(float(lo_raw) - begin, 0.0), align.length)
    hi = min(max(float(hi_raw) - begin, 0.0), align.length)
    dists = {lo, hi} | {d for el in align.elements for d in (el.start_dist, el.end_dist)
                        if lo < d < hi}
    d = lo
    while d < hi:
        dists.add(d)
        d += _STEP_FT
    return [align.point_at(x) for x in sorted(dists)]


@dataclass
class ViewportView:
    vp: Viewport
    transform: geo.ViewportTransform
    rect: Rect  # paper rect of the viewport
    window: Optional[Rect]  # the part of it inside the usable area


@dataclass
class SheetView:
    """One deliverable sheet: what the truth asks for and what the document has."""

    truth: dict
    sheet: Optional[Sheet] = None
    usable: Optional[Rect] = None
    views: List[ViewportView] = field(default_factory=list)
    showing: Optional[ViewportView] = None  # first viewport showing this sheet's share
    fitted: Optional[ViewportView] = None   # ... that also sits inside the usable area
    used: Optional[ViewportView] = None     # the viewport the sheet is drawn through

    @property
    def name(self) -> str:
        return self.truth["name"]

    @property
    def fpi(self) -> float:
        if self.used is not None:
            return float(self.used.vp.feet_per_inch)
        return float(self.truth["feet_per_inch"])

    def model_view(self, p: Sequence[float]) -> Optional[ViewportView]:
        """The viewport a model point is seen through on this sheet (inside
        the viewport and the usable area), or None."""
        for view in self.views:
            if view.window is not None and rect_contains(view.window, view.transform.to_paper(p)):
                return view
        return None

    def visible(self, q: Sequence[float]) -> bool:
        return self.usable is not None and rect_contains(self.usable, q)


@dataclass
class Context:
    doc: Document
    truth: GroundTruth
    spec: dict
    level: str = "explicit"  # the prompt level the task was posed at
    stated: frozenset = frozenset()  # conventions that prompt states (spec prompt_levels)
    title_stated: List[str] = field(default_factory=list)  # title fields whose values it gives
    scope: frozenset = frozenset(GROUPS)  # the truth groups the task asks for
    truth_names: List[str] = field(default_factory=list)  # the truth's alignments, primary first
    sheets: List[SheetView] = field(default_factory=list)
    alignment_name: Optional[str] = None
    alignment: Optional[Alignment] = None
    #: the truth's alignments by every name an anchor may use for them: the name
    #: itself (the document's own, or the one the agent created) and the
    #: qualified name through a reference at identity
    aliases: Dict[str, Tuple[str, Alignment]] = field(default_factory=dict)

    @property
    def tol(self) -> dict:
        return self.spec["tolerances"]

    @property
    def lenient(self) -> dict:
        return self.spec["lenient"]

    def states(self, convention: str) -> bool:
        """Did the prompt state this convention (so it is graded exactly)?"""
        return convention in self.stated

    def asks(self, *groups: str) -> bool:
        """Does the task ask for any of these truth groups?"""
        return any(g in self.scope for g in groups)

    def truth_alignment(self, name: Optional[str]) -> Optional[Tuple[str, Alignment]]:
        """``(truth name, alignment)`` for an anchor's alignment name -- a truth
        alignment named directly (the document's own, or the one the agent
        created) or through a reference at identity -- or None for any other
        (one the agent added that the truth never asks for, or a reference
        moved off identity).  The geometry is the truth's own when the truth
        carries it, else the copy the name resolves to."""
        return self.aliases.get(name) if name else None

    @property
    def layers(self) -> dict:
        return self.spec["layers"]

    @property
    def many_sheets(self) -> bool:
        return len(self.sheets) > 1

    # -- the first sheet, for code that wants one
    @property
    def first(self) -> Optional[SheetView]:
        return self.sheets[0] if self.sheets else None

    @property
    def sheet(self) -> Optional[Sheet]:
        return self.first.sheet if self.first else None

    @property
    def usable(self) -> Optional[Rect]:
        return self.first.usable if self.first else None

    @property
    def views(self) -> List[ViewportView]:
        return self.first.views if self.first else []

    @property
    def fpi_used(self) -> float:
        return self.first.fpi if self.first else float(self.truth.sheet.get("feet_per_inch", 1))

    @property
    def any_sheet(self) -> bool:
        return any(sv.sheet is not None for sv in self.sheets)

    @classmethod
    def build(cls, doc: Document, truth: GroundTruth, spec: dict,
              level: str = "explicit") -> "Context":
        levels = spec["prompt_levels"]
        if level not in levels:
            raise ValueError(f"unknown prompt level {level!r}; levels: {', '.join(levels)}")
        ctx = cls(doc=doc, truth=truth, spec=spec, level=level,
                  stated=frozenset(levels[level]["states"]),
                  title_stated=list(levels[level].get("title_fields", [])),
                  scope=frozenset(truth.scope or GROUPS))
        names = ctx.truth_names = truth_alignments(truth)
        for name, qualified, align, _design in design_sources(doc, names):
            if name in truth.alignments:  # the geometry the truth was computed from
                align = Alignment.from_dict(truth.alignments[name])
            ctx.aliases[name] = (name, align)
            if qualified:
                ctx.aliases[qualified] = (name, align)
        if names:
            ctx.alignment_name = names[0]
            # the design the truth was computed from, when the truth carries it; the
            # document's own copy, or its referenced base drawing's, otherwise (older
            # truths; equal when the design is given)
            if names[0] in truth.alignments:
                ctx.alignment = Alignment.from_dict(truth.alignments[names[0]])
            else:
                found = ctx.aliases.get(names[0])
                ctx.alignment = found[1] if found else None
        for want in truth.sheets:
            sv = SheetView(truth=want, sheet=doc.sheet_by_ref(want["name"]))
            ctx.sheets.append(sv)
            if sv.sheet is None:
                continue
            sv.usable = tuple(sv.sheet.usable_area())
            for vp in sv.sheet.viewports:
                rect = tuple(vp.paper_bbox())
                sv.views.append(ViewportView(vp=vp, transform=vp.transform(), rect=rect,
                                             window=rect_intersection(rect, sv.usable)))
            if ctx.alignment is not None:
                lo, hi = want.get("station_range") or (ctx.alignment.begin_station,
                                                       ctx.alignment.end_station)
                samples = segment_samples(ctx.alignment, lo, hi)
                for view in sv.views:
                    if all(rect_contains(view.rect, view.transform.to_paper(p)) for p in samples):
                        sv.showing = sv.showing or view
                        if rect_inside(view.rect, sv.usable):
                            sv.fitted = view
                            break
            sv.used = sv.fitted or sv.showing or (sv.views[0] if sv.views else None)
        return ctx

    # ---------------------------------------------------------- visibility

    def sheet_view(self, space: str) -> Optional[SheetView]:
        """The deliverable sheet with this id or name."""
        for sv in self.sheets:
            if sv.sheet is not None and space in (sv.sheet.id, sv.sheet.name):
                return sv
        return None

    def model_view(self, p: Sequence[float]) -> Optional[ViewportView]:
        """The viewport a model-space point is seen through on any deliverable
        sheet, or None."""
        for sv in self.sheets:
            view = sv.model_view(p)
            if view is not None:
                return view
        return None

    def sheet_visible(self, space: str, q: Sequence[float]) -> bool:
        sv = self.sheet_view(space)
        return sv is not None and sv.visible(q)


__all__ = ["Context", "SheetView", "ViewportView", "given_design", "design_sources",
           "design_home", "truth_alignments",
           "alignment_samples", "segment_samples", "rect_contains", "rect_inside",
           "rect_intersection"]

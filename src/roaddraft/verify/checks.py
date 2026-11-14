"""One function per check id (D1-00 ... D1-11), over one shared analysis.

Each check returns ``(credit, findings)`` with credit in [0, 1]; ``rubric``
weighs the checks the task's scope puts in play.  The formulas follow the
eval plan's section 3.4 table, with these readings made precise:

- D1-03/04/05 credit a truth label when its chosen candidate is visible on
  a deliverable sheet with the right content.  A visible label (chosen or
  duplicate) with the wrong content is ``wrong_value``: wrong work on the
  sheet.
- D1-07, D1-08 and D1-09 judge the quality of the work that is there, so
  they are ratios over present, in-scope work; with none present there is
  nothing to judge and they score 0 (an empty sheet earns nothing).
  D1-07 is consistent labels over matched labels plus hand-rewritten
  anchors; D1-09 is conforming items over matched items plus the four spec
  layers.
- D1-01 credits an element matched on any layer and reports ``wrong_layer``
  when no match is on the alignment layer (D1-09 takes the points).
  Linework on the alignment layer that strays off the design is
  ``geometry_mismatch`` while some element is still unmatched (a wrong
  attempt at it) and ``extra_linework`` once every element is matched; both
  are value findings.
- D1-02 credits a truth tick only with a line an anchoring command placed
  (``placed_by`` in ``bus.ANCHOR_PRODUCERS``), as labels are credited; a
  line drawn by hand that would have matched is ``unanchored`` (d1-verify-v6).
- Per-sheet checks (D1-00, D1-06, D1-10, D1-11) average over the deliverable
  sheets; D1-08 adds up overlaps across them.  With two sheets D1-00 also
  wants the match line drawn at the break and labelled on each sheet.
- D1-15, D1-01 and D1-12 read the design, its centerline and its pavement
  edges in the document under test.  Only a truth whose scope carries
  ``tasks.types.BASE_SCOPE`` (2026-11-13: a revision the drafter makes in the
  base drawing a sheet file references) has them read in that base drawing
  instead, through the reference (``context.design_home``); every other truth
  is scored as it was.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from pathlib import Path

from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.core import geometry as geo
from roaddraft.core.units import format_station
from roaddraft.design.errors import DesignError
from roaddraft.document import dimgeom
from roaddraft.document.entities import BlockRef, Dimension, Entity, Line, Polyline, Table, Text
from roaddraft.tasks.types import GROUP_LAYER_ROLE
from roaddraft.verify.context import Context, SheetView, design_home, rect_inside
from roaddraft.verify.geometry import (
    LineworkResult, TickMatch, crosses_at, match_edges, match_linework, match_ticks, pieces_of,
    same_piece,
)
from roaddraft.verify.legibility import (
    clipped, crossing_pairs, outside, overlapping_pairs, reference_items, sheet_items,
    sheet_strokes, upside_down,
)
from roaddraft.verify.match import LabelIndex, index_labels
from roaddraft.verify.normalize import normalize
from roaddraft.verify.report import Finding
from roaddraft.verify.semantic import column_key, same_cell, same_match_label, scale_fpi

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")

_CURVE_NO = re.compile(r"^C(?:URVE)?\s*(?:NO\.?)?\s*[-#]?\s*(\d+)$", re.I)

Result = Tuple[float, List[Finding]]

NO_SHEET = "the deliverable sheet does not exist"

#: Checks the verifier adds beside the spec's frozen list (d1-verify-v7): the
#: construction callouts of a real plan sheet (``tasks.real_callouts``), judged
#: like labels -- credit only for a note ``place_callout`` placed, with its text as
#: given and its leader tip on the point called out, as the sheet's own viewport
#: shows it (d1-verify-v8: the drafter's viewport, not the sample sheet's); a
#: callout at one of those points reading another note is wrong work on the sheet
#: (hard fail).  They enter
#: a task's rubric only through their groups (``tasks.types.CHECK_GROUPS``), so a
#: task that does not ask for the group never sees them and the spec's hash and
#: every task id stand.  Folded into the spec's own list at its next version.
EXTRA_CHECKS = (
    {"id": "D1-16",
     "name": "construction callouts: each note placed as a callout, reading as given, its "
             "leader tip on the station and offset called out",
     "weight": 14, "hard_fail": True},
)


def _no_sheet(sv: SheetView) -> str:
    return f"sheet {sv.name} does not exist"


# ------------------------------------------------------------------- tables


@dataclass
class TableEval:
    table: Table
    headers_ok: bool
    correct_rows: int
    n_rows: int
    findings: List[Finding] = field(default_factory=list)

    @property
    def score(self) -> float:
        rows = self.correct_rows / self.n_rows if self.n_rows else 1.0
        return (0.2 if self.headers_ok else 0.0) + 0.8 * rows


@dataclass
class TableResult:
    truth: dict
    chosen: Optional[TableEval] = None
    others: List[TableEval] = field(default_factory=list)
    unanchored: List[Table] = field(default_factory=list)


def evaluate_table(table: Table, truth_table: dict, exact: bool = True,
                   core: Optional[List[str]] = None) -> TableEval:
    """Compare one anchored table with a sheet's truth curve table, cell by cell.

    ``exact`` (the prompt stated the columns): the headers must be the
    spec's, in order, and cells must read exactly.  Otherwise columns are
    recognised by what their headers mean, only the ``core`` columns are
    required, and cells are compared by value."""
    align = truth_table["anchor"]["alignment"]
    headers = [c["header"] for c in table.columns]
    keys = list(truth_table["columns"])
    truth_rows = list(truth_table["rows"])
    table_anchor = dict(truth_table["anchor"])
    if exact:
        by_header = {normalize(h): k for h, k in zip(truth_table["headers"], keys)}
        header_key = lambda h: by_header.get(normalize(h))
        required = keys
        cell_ok = lambda key, a, e: normalize(a) == normalize(e)
        row_name = lambda text: normalize(text)
        headers_ok = ([normalize(h) for h in headers]
                      == [normalize(h) for h in truth_table["headers"]])
    else:
        header_key = column_key
        required = [k for k in (core or keys)]
        cell_ok = same_cell
        row_name = lambda text: (lambda m: int(m.group(1)) if m else normalize(text))(
            _CURVE_NO.match(normalize(text)))
        headers_ok = all(any(column_key(h) == k for h in headers) for k in required)
    ev = TableEval(table=table, correct_rows=0, n_rows=len(truth_rows), headers_ok=headers_ok)
    if not headers_ok:
        ev.findings.append(Finding("wrong_field", anchor=table_anchor, entity_ids=[table.id],
                                   expected=list(truth_table["headers"]), actual=headers,
                                   note="the table's column headers are not the spec's"))
    col: Dict[str, int] = {}
    for j, h in enumerate(headers):
        k = header_key(h)
        if k is not None:
            col.setdefault(k, j)
    missing_cols = [k for k in required if k not in col]
    curve_col = col.get("curve")
    names = [row_name(r[keys.index("curve")]) if "curve" in keys else None for r in truth_rows]
    by_name: Dict[object, List[int]] = {}
    if curve_col is not None:
        for i, row in enumerate(table.rows):
            by_name.setdefault(row_name(row[curve_col]), []).append(i)
    used = set()

    def compare(i: int, trow: List[str], anchor: dict, note_extra: str = "") -> bool:
        ok = not missing_cols
        for j, k in enumerate(keys):
            if k not in col:
                continue
            cell = table.rows[i][col[k]]
            if not cell_ok(k, cell, trow[j]):
                ev.findings.append(Finding("wrong_value", anchor=anchor, entity_ids=[table.id],
                                           expected=trow[j], actual=cell,
                                           note=f"curve table column {truth_table['headers'][j]}"
                                                f"{note_extra}"))
                ok = False
        return ok

    for t, trow in enumerate(truth_rows):
        anchor = {"alignment": align, "ref": trow[0], "kind": "curve_table"}
        if curve_col is not None:
            rows = by_name.get(names[t], [])
        else:
            rows = [t] if t < len(table.rows) else []
        if not rows:
            ev.findings.append(Finding("missing", anchor=anchor, entity_ids=[table.id],
                                       note="the curve table has no row for this curve"))
            continue
        used.update(rows)
        if compare(rows[0], trow, anchor):
            ev.correct_rows += 1
        for extra in rows[1:]:
            ev.findings.append(Finding("duplicate", anchor=anchor, entity_ids=[table.id],
                                       note="the curve table repeats this curve's row"))
            compare(extra, trow, anchor, " (a repeated row)")
    for i, row in enumerate(table.rows):
        if i not in used:
            ev.findings.append(Finding("wrong_value", anchor=table_anchor, entity_ids=[table.id],
                                       actual=list(row),
                                       note="the curve table has a row for a curve this sheet "
                                            "does not show"))
    if missing_cols:
        ev.findings.append(Finding("wrong_field", anchor=table_anchor, entity_ids=[table.id],
                                   expected=missing_cols,
                                   note="the curve table lacks columns the spec requires"))
    return ev


def analyze_tables(ctx: Context) -> Dict[str, TableResult]:
    """Per deliverable sheet that must carry a curve table: the anchored
    tables on it, best first."""
    out: Dict[str, TableResult] = {}
    for want in ctx.truth.curve_tables:
        res = TableResult(truth=want)
        out[want["sheet"]] = res
        sv = ctx.sheet_view(want["sheet"])
        if sv is None:
            continue
        evals = []
        for e in sv.sheet.entities.values():
            if not isinstance(e, Table):
                continue
            rec = e.anchor or {}
            if rec.get("placed_by") not in ANCHOR_PRODUCERS or rec.get("kind") != "curve_table":
                res.unanchored.append(e)
                continue
            found = ctx.truth_alignment(rec.get("alignment"))
            if found is not None and found[0] == want["anchor"]["alignment"]:
                evals.append(evaluate_table(e, want, exact=ctx.states("table_columns"),
                                            core=ctx.lenient["table_core_columns"]))
        evals.sort(key=lambda ev: (-ev.score, ev.table.id))
        if evals:
            res.chosen, res.others = evals[0], evals[1:]
    return out


# ----------------------------------------------------------------- analysis


@dataclass
class DimMatch:
    """One truth width dimension and the document's best answer to it."""

    truth: dict
    chosen: Optional[Dimension] = None  # a dimension across the pavement on this tangent
    at_station: bool = False            # ... at the stated station
    text_ok: bool = False               # ... reading the width

    @property
    def credited(self) -> bool:
        return self.chosen is not None and self.at_station and self.text_ok

    @property
    def anchor(self) -> dict:
        # the tangent, never the station: the explicit prompt states it, the vague one
        # leaves it to the drafter, and the agent view must not show it either way
        # (d1-verify-v4; it is the ``expected`` of a misplaced finding, which is stripped)
        return {"ref": self.truth["ref"], "kind": "width"}


def _dimension_points(dim: Dimension):
    if dim.kind not in ("linear", "aligned") or dim.p2 is None:
        return None
    return dim.p1, dim.p2


def analyze_dimensions(ctx: Context) -> List[DimMatch]:
    """Match the truth's width dimensions: a model-space linear/aligned
    dimension whose two points sit on the two pavement edges at one station
    on the tangent.  Explicit: at the stated station, text exact.  Vague:
    anywhere on the tangent, text by value."""
    out: List[DimMatch] = []
    if not ctx.truth.dimensions or ctx.alignment is None:
        return out
    align = ctx.alignment
    tol = float(ctx.tol["position_model_ft"])
    sta_tol = float(ctx.tol["station_ft"])
    exact = ctx.states("label_format")
    dims = [e for e in ctx.doc.model_entities.values() if isinstance(e, Dimension)]
    for want in ctx.truth.dimensions:
        m = DimMatch(truth=want)
        half = float(want["value"]) / 2.0
        lo, hi = want["tangent_range"]
        best = None
        for dim in dims:
            pts = _dimension_points(dim)
            if pts is None:
                continue
            try:
                a, b = (align.xy_to_station(q) for q in pts)
            except DesignError:
                continue
            offsets = sorted((a["offset"], b["offset"]))
            if abs(offsets[0] + half) > tol or abs(offsets[1] - half) > tol:
                continue
            if abs(a["station"] - b["station"]) > sta_tol:
                continue
            station = (a["station"] + b["station"]) / 2.0
            if not (lo - sta_tol <= station <= hi + sta_tol):
                continue
            at_station = abs(station - float(want["station"])) <= sta_tol
            text = dimgeom.text_of(dim)
            if exact:
                text_ok = normalize(text) == normalize(want["text"])
            else:
                nums = _NUMBER.findall(text)
                text_ok = bool(nums) and abs(float(nums[0]) - float(want["value"])) <= 0.005 + 1e-9
            score = (text_ok, at_station or not exact, at_station, dim.id)
            if best is None or score > best[0]:
                best = (score, dim, at_station, text_ok)
        if best is not None:
            _, m.chosen, m.at_station, m.text_ok = best
            if not exact:
                m.at_station = True  # anywhere on the tangent will do
        out.append(m)
    return out


@dataclass
class CalloutCandidate:
    """A callout on the document: its text (with a ``callout`` record), the
    leader tip read from the lines drawn with it, on paper."""
    text: Text
    tip: Optional[List[float]]
    visible: bool


@dataclass
class CalloutMatch:
    """One truth callout against the document."""
    truth: dict
    expected: Optional[List[float]] = None  # where the tip belongs on the paper (expected_callout_tip)
    chosen: Optional[CalloutCandidate] = None
    distance: Optional[float] = None    # tip to the point called out, paper inches
    wrong: Optional[CalloutCandidate] = None  # a callout at the point reading another note
    by_hand: Optional[Text] = None      # the note typed as text, with no callout record

    @property
    def anchor(self) -> dict:
        return {"alignment": self.truth["alignment"], "ref": self.truth["ref"],
                "kind": "callout"}


@dataclass
class Analysis:
    ctx: Context
    labels: LabelIndex
    linework: Optional[LineworkResult]
    ticks: List[TickMatch]
    tables: Dict[str, TableResult]
    edges: Optional[LineworkResult] = None
    dimensions: List[DimMatch] = field(default_factory=list)
    callouts: List[CalloutMatch] = field(default_factory=list)

    def anchor(self, ref: str, kind: str) -> dict:
        return {"alignment": self.ctx.alignment_name, "ref": ref, "kind": kind}

    def chosen_tables(self) -> List[TableEval]:
        return [t.chosen for t in self.tables.values() if t.chosen is not None]


#: how far a north arrow may turn from north on the sheet (degrees)
NORTH_TOL_DEG = 2.0

#: anchored parts of a label (a curve bubble's circle and leader) or of a callout (its
#: leader, shoulder and arrowhead), never ticks
LABEL_PART_KINDS = ("mc_bubble", "mc_leader", "callout_leader")


def analyze(ctx: Context) -> Analysis:
    model = list(ctx.doc.model_entities.values())
    tol = float(ctx.tol["position_model_ft"])
    # what the drafter was handed (a real sheet's base file) earns no linework credit
    handed = {i for sh in ctx.truth.sheets for i in sh.get("given_entities") or ()}
    # the design's own linework is looked for where the design lives: in this document, or,
    # on a truth marked ``BASE_SCOPE``, in the base drawing the sheet file references
    home = design_home(ctx.doc, ctx.truth)
    lines = model if home is ctx.doc else (list(home.model_entities.values())
                                           if home is not None else [])
    drawn = [e for e in lines if e.id not in handed]
    linework = (match_linework(ctx.alignment, drawn, ctx.layers["alignment"], tol)
                if ctx.alignment is not None else None)
    lo, hi = ctx.lenient["tick_length_in"]
    # a curve bubble's leader can cross the line at a station: it is the bubble's, not a
    # tick; nor is a line the drafter was handed (a real sheet's pipe crossing the line)
    given = {i for sh in ctx.truth.sheets for i in sh.get("given_entities") or ()}
    tickable = [e for e in model if e.id not in given and (getattr(e, "anchor", None) or {}
                                                           ).get("kind") not in LABEL_PART_KINDS]
    # a tick earns credit only when an anchoring command placed it (d1-verify-v6), as a
    # label does: a line drawn by hand at the station, however exact, is reported, not credited
    stamped = {e.id for e in tickable
               if (getattr(e, "anchor", None) or {}).get("placed_by") in ANCHOR_PRODUCERS}
    tick_args = dict(exact=ctx.states("tick_length"), rot_tol_deg=float(ctx.tol["rotation_deg"]),
                     length_range=(lo * ctx.fpi_used, hi * ctx.fpi_used))
    ticks = match_ticks(ctx.truth.ticks, [e for e in tickable if e.id in stamped], tol,
                        **tick_args)
    by_hand = match_ticks(ctx.truth.ticks, [e for e in tickable if e.id not in stamped], tol,
                          **tick_args)
    for tm, hm in zip(ticks, by_hand):
        if not tm.hits and hm.hits:
            tm.unanchored = hm.hits[0]
    edges = None
    if ctx.truth.edges and ctx.alignment is not None and ctx.asks("edges"):
        edges = match_edges(ctx.alignment, ctx.truth.edges, lines, ctx.layers["edges"], tol)
    return Analysis(ctx=ctx, labels=index_labels(ctx), linework=linework, ticks=ticks,
                    tables=analyze_tables(ctx), edges=edges,
                    dimensions=analyze_dimensions(ctx) if ctx.asks("widths") else [],
                    callouts=analyze_callouts(ctx) if ctx.asks("notes") else [])


def _pt_key(p) -> Tuple[float, float]:
    return (round(float(p[0]), 6), round(float(p[1]), 6))


def callout_tip(entities: Dict[str, Entity], text: Text) -> Optional[List[float]]:
    """Where a callout's leader points, read from what is drawn: the line that
    ends at the text's insertion point and, when that is the level shoulder
    ``place_callout`` draws, the leader that meets its far end (as
    ``legibility`` finds leaders).  None when no line reaches the text."""
    lines = [e for e in entities.values() if isinstance(e, Line)]
    here = _pt_key(text.position)
    first = [ln for ln in lines if _pt_key(ln.start) == here or _pt_key(ln.end) == here]
    if not first:
        return None
    shoulder = first[0]
    far = shoulder.end if _pt_key(shoulder.start) == here else shoulder.start
    if abs(float(shoulder.end[1]) - float(shoulder.start[1])) <= 1e-9:
        key = _pt_key(far)
        for ln in lines:
            if ln is shoulder:
                continue
            if _pt_key(ln.start) == key:
                return [float(ln.end[0]), float(ln.end[1])]
            if _pt_key(ln.end) == key:
                return [float(ln.start[0]), float(ln.start[1])]
    return [float(far[0]), float(far[1])]


def expected_callout_tip(ctx: Context, truth: dict) -> List[float]:
    """Where a note's leader tip belongs on the paper: the station and offset
    called out (``tip_model``) seen through the viewport the deliverable sheet
    is drawn through (``SheetView.used``), so a sheet the drafter laid out on
    their own centre is judged as drawn (d1-verify-v8).  The task's own
    projection (``tip_paper``, through the sample sheet's viewport) only when
    the sheet has no viewport to see through yet."""
    sv = next((v for v in ctx.sheets if v.name == truth.get("sheet")), None) or ctx.first
    if sv is not None and sv.used is not None and truth.get("tip_model") is not None:
        p = sv.used.transform.to_paper(truth["tip_model"])
        return [float(p[0]), float(p[1])]
    return [float(v) for v in truth["tip_paper"]]


def analyze_callouts(ctx: Context) -> List[CalloutMatch]:
    """Each truth callout against the document's callouts (texts carrying a
    ``callout`` record): the nearest one reading the note is its match, one
    callout to a note; a callout reading none of the notes with its tip on a
    note's point (``expected_callout_tip``) is that note's ``wrong``; a note
    typed as plain text is noted as ``by_hand``."""
    cands: List[CalloutCandidate] = []
    for sv in ctx.sheets:
        if sv.sheet is None:
            continue
        for e in sv.sheet.entities.values():
            if isinstance(e, Text) and (e.anchor or {}).get("kind") == "callout":
                cands.append(CalloutCandidate(e, callout_tip(sv.sheet.entities, e),
                                              ctx.sheet_visible(sv.sheet.id, e.position)))
    for e in ctx.doc.model_entities.values():  # a callout in the model, seen through a viewport
        if isinstance(e, Text) and (e.anchor or {}).get("kind") == "callout":
            tip = callout_tip(ctx.doc.model_entities, e)
            view = ctx.model_view(e.position)
            paper = view.transform.to_paper(tip) if (view is not None and tip is not None) else None
            cands.append(CalloutCandidate(e, [float(paper[0]), float(paper[1])] if paper else None,
                                          view is not None))
    matches = [CalloutMatch(truth=c, expected=expected_callout_tip(ctx, c))
               for c in ctx.truth.callouts]
    pairs = []
    for i, m in enumerate(matches):
        want = normalize(m.truth["content"])
        for j, cand in enumerate(cands):
            if normalize(cand.text.content) != want:
                continue
            d = geo.distance(cand.tip, m.expected) if cand.tip is not None else float("inf")
            pairs.append((d, i, j))
    taken: set = set()
    for d, i, j in sorted(pairs):
        m = matches[i]
        if m.chosen is not None or j in taken:
            continue
        m.chosen, m.distance = cands[j], d
        taken.add(j)
    tol = float(ctx.tol["position_paper_in"])
    notes = {normalize(c["content"]) for c in ctx.truth.callouts}
    for j, cand in enumerate(cands):
        if j in taken or cand.tip is None or normalize(cand.text.content) in notes:
            continue
        for m in matches:
            if m.chosen is None and geo.distance(cand.tip, m.expected) <= tol:
                m.wrong = cand
                break
    plain = [t for t, _why in ctx_texts_without_callout_record(ctx)]
    for m in matches:
        if m.chosen is None:
            want = normalize(m.truth["content"])
            m.by_hand = next((t for t in plain if normalize(t.content) == want), None)
    return matches


def ctx_texts_without_callout_record(ctx: Context):
    """``(text, where)`` for every text with no ``callout`` record, in any space."""
    for e in ctx.doc.model_entities.values():
        if isinstance(e, Text) and (e.anchor or {}).get("kind") != "callout":
            yield e, "model"
    for sv in ctx.sheets:
        if sv.sheet is not None:
            for e in sv.sheet.entities.values():
                if isinstance(e, Text) and (e.anchor or {}).get("kind") != "callout":
                    yield e, sv.sheet.id


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ------------------------------------------------------------------- checks


@dataclass
class MatchFound:
    lines: List[Entity] = field(default_factory=list)   # match lines at the break
    labels: List[Entity] = field(default_factory=list)  # this sheet's labels at it


def _match_line(a: Analysis, sv: SheetView, m: dict,
                found: Optional[MatchFound] = None) -> Tuple[float, List[Finding]]:
    """Half the match credit for the line across the centerline at the break
    (seen on this sheet), half for this sheet's label at it.  ``found``
    collects the entities for D1-09."""
    ctx = a.ctx
    tol = float(ctx.tol["position_model_ft"])
    anchor = a.anchor(m["station_text"], "match_line")
    findings: List[Finding] = []
    credit = 0.0
    truth_piece = pieces_of(Line(id="truth", start=m["start"], end=m["end"]))[0]
    station_pt = truth_piece.m
    lines = [p for e in ctx.doc.model_entities.values()
             if isinstance(e, (Line, Polyline)) for p in pieces_of(e) if p.kind == "line"]
    if ctx.states("match_line"):
        hits = [p for p in lines if same_piece(p, truth_piece, tol)]
    else:
        min_len = float(ctx.lenient["match_line_min_in"]) * sv.fpi
        hits = [p for p in lines if p.length >= min_len
                and crosses_at(p, truth_piece, tol, float(ctx.tol["rotation_deg"]))]
    if found is not None:
        found.lines = sorted({h.entity.id: h.entity for h in hits}.values(), key=lambda e: e.id)
    if hits and sv.model_view(station_pt) is not None:
        credit += 0.5
    elif hits:
        findings.append(Finding("not_visible", anchor=anchor,
                                entity_ids=sorted({h.entity.id for h in hits}),
                                note=f"the match line is not seen on sheet {sv.name}"))
    else:
        findings.append(Finding("missing", anchor=anchor,
                                note="no match line across the centerline at the break"))
    label_anchor = a.anchor(m["station_text"], "match_label")
    cands = [c for c in a.labels.custom.get(sv.sheet.id, [])
             if c.station is not None
             and abs(c.station - float(m["station"])) <= float(ctx.tol["station_ft"])]
    if not cands:
        findings.append(Finding("missing", anchor=label_anchor,
                                note=f"no match line label on sheet {sv.name}"))
        return credit, findings
    exact = ctx.states("match_line")

    def ok(c) -> bool:
        if exact:
            return normalize(c.entity.content) == normalize(m["label"])
        return same_match_label(c.entity.content, m["station_text"], m["other_sheet"])

    good = [c for c in cands if c.visible and ok(c)]
    if found is not None:
        found.labels = [c.entity for c in (good or cands[:1])]
    if good:
        return credit + 0.5, findings
    c = cands[0]
    if not c.visible:
        findings.append(Finding("not_visible", anchor=label_anchor, entity_ids=[c.id],
                                note="the match line label is outside the usable area"))
    else:
        findings.append(Finding("wrong_value", anchor=label_anchor, entity_ids=[c.id],
                                expected=m["label"], actual=c.entity.content,
                                note="the match line label reads wrong"))
    return credit, findings


def check_sheet_setup(a: Analysis) -> Result:  # D1-00
    ctx = a.ctx
    parts = ctx.spec["sheet_setup"]["many_sheets" if ctx.many_sheets else "one_sheet"]
    credits, findings = [], []
    for sv in ctx.sheets:
        want = sv.truth
        if sv.sheet is None:
            findings.append(Finding("sheet_missing", expected=want["name"], note=_no_sheet(sv)))
            credits.append(0.0)
            continue
        credit = 0.0
        if sv.sheet.size == want["size"]:
            credit += parts["sheet"]
        else:
            findings.append(Finding("sheet_missing", expected=want["size"], actual=sv.sheet.size,
                                    note=f"sheet {sv.name} is not the size asked for"))
        if ctx.states("scale"):
            allowed = [float(want["feet_per_inch"])]
        else:
            allowed = [float(f) for f in ctx.lenient["standard_feet_per_inch"]]
        scales = [float(v.vp.feet_per_inch) for v in sv.views]
        if any(abs(s - f) < 1e-9 for s in scales for f in allowed):
            credit += parts["scale"]
        else:
            findings.append(Finding("viewport_scale", expected=allowed, actual=scales,
                                    note=(f"no viewport on {sv.name} is at the scale asked for"
                                          if scales else f"sheet {sv.name} has no viewport")))
        twist = want.get("twist_deg")
        turned = (sv.fitted is None or twist is None
                  or abs((float(sv.fitted.vp.rotation_deg) - float(twist) + 180.0) % 360.0 - 180.0)
                  <= float(ctx.tol["rotation_deg"]))
        if sv.fitted is not None and turned:
            credit += parts["fitted"]
        elif sv.fitted is not None:
            findings.append(Finding(
                "not_fitted", entity_ids=[sv.fitted.vp.id], expected=float(twist),
                actual=float(sv.fitted.vp.rotation_deg),
                note=f"the viewport on {sv.name} is not turned to the sheet's twist, so the "
                     f"plan does not read as published"))
        else:
            findings.append(Finding(
                "not_fitted", entity_ids=[sv.showing.vp.id] if sv.showing else [],
                note=(f"the viewport showing the alignment on {sv.name} runs outside the usable "
                      f"area" if sv.showing else
                      f"no viewport on {sv.name} shows its whole part of the alignment")))
        matches = want.get("matches") or []
        if matches and "match_line" in parts:
            got = []
            for m in matches:
                c, fs = _match_line(a, sv, m)
                got.append(c)
                findings.extend(fs)
            credit += parts["match_line"] * _mean(got)
        credits.append(credit)
    return _mean(credits), findings


def check_linework(a: Analysis) -> Result:  # D1-01
    if a.linework is None:
        return 0.0, [Finding("missing", note="the alignment is not in the design")]
    layer = a.ctx.layers["alignment"]
    els = a.linework.elements
    findings = []
    for em in els:
        anchor = a.anchor(em.ref, "element")
        if not em.hits:
            findings.append(Finding("missing", anchor=anchor,
                                    note="no linework matches this alignment element"))
        elif not any(h.entity.layer == layer for h in em.hits):
            findings.append(Finding("wrong_layer", anchor=anchor,
                                    entity_ids=sorted({h.entity.id for h in em.hits}),
                                    expected=layer,
                                    actual=sorted({h.entity.layer for h in em.hits})))
    matched = sum(1 for em in els if em.hits)
    if a.linework.bad_entities:
        complete = matched == len(els)
        for e in a.linework.bad_entities:
            findings.append(Finding(
                "extra_linework" if complete else "geometry_mismatch", entity_ids=[e.id],
                note="linework on the alignment layer that is not part of the design" if complete
                else "linework on the alignment layer that does not follow the design geometry"))
    return (matched / len(els) if els else 1.0), findings


def check_ticks(a: Analysis) -> Result:  # D1-02
    findings, hits = [], 0
    for tm in a.ticks:
        anchor = a.anchor(tm.truth["station_text"], "tick")
        if tm.hits:
            hits += 1
        elif tm.near is not None:
            findings.append(Finding("misplaced", anchor=anchor, entity_ids=[tm.near.entity.id],
                                    expected=[tm.piece.a, tm.piece.b],
                                    actual=[tm.near.a, tm.near.b],
                                    note="a tick near this station is off the station or the "
                                         "wrong length"))
        elif tm.unanchored is not None:
            findings.append(Finding("unanchored", anchor=anchor,
                                    entity_ids=[tm.unanchored.entity.id],
                                    note="the tick at this station was not placed by an "
                                         "anchoring command, so it earns no credit"))
        else:
            findings.append(Finding("missing", anchor=anchor, note="no tick at this station"))
    return (hits / len(a.ticks) if a.ticks else 1.0), findings


def _check_labels(a: Analysis, check_id: str) -> Result:  # D1-03, D1-04, D1-05
    matches = [m for m in a.labels.matches if m.check == check_id]
    findings, ok = [], 0
    for m in matches:
        c = m.chosen
        if c is None:
            findings.append(Finding("missing", anchor=m.anchor,
                                    note="no anchored label for this anchor"))
        elif not c.visible:
            findings.append(Finding("not_visible", anchor=m.anchor, entity_ids=[c.id],
                                    note=NO_SHEET if not a.ctx.any_sheet else
                                    "the label is not inside a viewport and the usable area of "
                                    "a deliverable sheet"))
        elif not m.content_ok(c):
            findings.append(Finding("wrong_value", anchor=m.anchor, entity_ids=[c.id],
                                    expected=m.truth["content"], actual=c.entity.content,
                                    note="the label reads wrong"))
        else:
            ok += 1
        for d in m.duplicates:
            if d.visible and not m.content_ok(d):
                findings.append(Finding("wrong_value", anchor=m.anchor, entity_ids=[d.id],
                                        expected=m.truth["content"], actual=d.entity.content,
                                        note="a second label for this anchor reads wrong"))
            else:
                findings.append(Finding("duplicate", anchor=m.anchor, entity_ids=[d.id],
                                        note="a second label for this anchor"))
    return (ok / len(matches) if matches else 1.0), findings


def check_curve_table(a: Analysis) -> Result:  # D1-06
    credits, findings = [], []
    for name, t in a.tables.items():
        anchor = dict(t.truth["anchor"])
        sv = a.ctx.sheet_view(name)
        if sv is None:
            findings.append(Finding("missing", anchor=anchor, note=f"sheet {name} does not exist"))
            credits.append(0.0)
            continue
        findings.extend(Finding("unanchored", entity_ids=[e.id],
                                note="a table not placed by place_curve_table earns no credit")
                        for e in t.unanchored)
        if t.chosen is None:
            findings.append(Finding("missing", anchor=anchor,
                                    note=f"no anchored curve table on sheet {name}"))
            credits.append(0.0)
            continue
        findings.extend(t.chosen.findings)
        for other in t.others:
            findings.append(Finding("duplicate", anchor=anchor, entity_ids=[other.table.id],
                                    note=f"a second curve table on sheet {name}"))
            findings.extend(f for f in other.findings if f.is_value)
        credits.append(t.chosen.score)
    return _mean(credits), findings


def check_anchored_position(a: Analysis) -> Result:  # D1-07
    findings, placed, matched = [], 0, 0
    for m in a.labels.matches:
        c = m.chosen
        if c is None:
            continue
        matched += 1
        if c.placed:
            placed += 1
        else:
            findings.append(Finding("misplaced", anchor=m.anchor, entity_ids=[c.id],
                                    expected={"position": c.expected_position,
                                              "rotation_deg": c.expected_rotation},
                                    actual={"position": list(c.entity.position),
                                            "rotation_deg": c.entity.rotation_deg},
                                    note="the label is not where its anchor puts it"))
    for inc in a.labels.inconsistent:
        findings.append(Finding("anchor_inconsistent",
                                anchor={"alignment": inc.key[0], "ref": inc.key[1],
                                        "kind": inc.key[2]},
                                entity_ids=[inc.entity.id], note=inc.note))
    for text, note in a.labels.unanchored:
        findings.append(Finding("unanchored", entity_ids=[text.id], note=note))
    denom = matched + len(a.labels.inconsistent)
    return (placed / denom if denom else 0.0), findings


def check_legibility(a: Analysis) -> Result:  # D1-08
    ctx = a.ctx
    if not ctx.any_sheet:
        return 0.0, [Finding("sheet_missing", note=NO_SHEET)]
    # legibility judges the whole sheet, but only once some of the asked-for work
    # is on it: a label, the table, the north arrow or the sheet itself
    block = ctx.spec["sheet"]["north_arrow"]["block"]
    present = (any(m.chosen is not None and m.chosen.visible for m in a.labels.matches)
               or (ctx.asks("table") and bool(a.chosen_tables()))
               or (ctx.asks("widths") and any(dm.chosen is not None for dm in a.dimensions))
               or (ctx.asks("notes") and any(cm.chosen is not None for cm in a.callouts))
               or (ctx.asks("sheet") and ctx.any_sheet)
               or (ctx.asks("north") and any(
                   isinstance(e, BlockRef) and e.block_name == block
                   for sv in ctx.sheets if sv.sheet is not None
                   for e in sv.sheet.entities.values())))
    if not present:
        return 0.0, [Finding("missing", note="none of the work asked for is on a sheet to judge")]
    findings, pairs, off = [], [], []
    for sv in ctx.sheets:
        if sv.sheet is None:
            continue
        items = sheet_items(ctx, sv)
        # a real plan sheet (tasks.real) lists what the drafter was handed: its own
        # overlaps are the original drafters', so only pairs with new work count, and the
        # referenced base drawings' text joins it as context
        given = set(sv.truth.get("given_entities") or ())
        if given:
            context = reference_items(ctx, sv)
            items = items + context
            given |= {it.entity_id for it in context}
        sv_pairs = [p for p in overlapping_pairs(items) if not (p[0] in given and p[1] in given)]
        # a dimension's lines or a callout's leader through another item's text is the
        # same offence (d1-verify-v4); a pair already charged for its text counts once
        seen = set(sv_pairs)
        sv_through = []
        for line_owner, text_owner in crossing_pairs(items, sheet_strokes(ctx, sv)):
            key = tuple(sorted((line_owner, text_owner)))
            if key in seen or (line_owner in given and text_owner in given):
                continue
            seen.add(key)
            sv_through.append((line_owner, text_owner))
        sv_off = [i for i in outside(items, sv.usable) if i not in given]
        cut = [i for i in clipped(ctx, sv) if i not in given]  # cut by its viewport's edge
        flipped = [i for i in upside_down(ctx, sv) if i not in given]  # as plotted
        pairs += sv_pairs + sv_through
        off += sv_off + cut + flipped
        findings += [Finding("overlap", entity_ids=list(p), note=f"on sheet {sv.name}")
                     for p in sv_pairs]
        findings += [Finding("overlap", entity_ids=[line_owner, text_owner],
                             note=f"a line of {line_owner} runs through the text of "
                                  f"{text_owner} on sheet {sv.name}")
                     for line_owner, text_owner in sv_through]
        findings += [Finding("off_sheet", entity_ids=[i],
                             note=f"outside the usable area of sheet {sv.name}")
                     for i in sv_off]
        findings += [Finding("clipped", entity_ids=[i],
                             note=f"cut by the edge of its viewport on sheet {sv.name}")
                     for i in cut]
        findings += [Finding("upside_down", entity_ids=[i],
                             note=f"reads upside down on sheet {sv.name} as plotted (a model "
                                  f"label under a twisted viewport wants view_rotation)")
                     for i in flipped]
    return max(0.0, 1.0 - 0.25 * (len(pairs) + len(off))), findings


def check_standards(a: Analysis) -> Result:  # D1-09
    ctx = a.ctx
    layers, props = ctx.layers, ctx.spec["layer_props"]
    text = ctx.spec["text"]
    pct = float(text["height_tolerance_pct"]) / 100.0
    findings: List[Finding] = []
    total = conforming = 0

    exact_layers, exact_heights = ctx.states("layers"), ctx.states("text_heights")
    ranges = {"labels": ctx.lenient["label_height_in"], "tables": ctx.lenient["table_height_in"],
              "dims": ctx.lenient["label_height_in"]}

    def height_ok(h: float, role: str, target: float) -> bool:
        if exact_heights:
            return abs(h - target) <= target * pct + 1e-9
        lo, hi = ranges[role]
        return lo - 1e-9 <= h <= hi + 1e-9

    def overrides_ok(e: Entity, layer: str) -> bool:
        p = props.get(layer, {})
        return ((e.color is None or e.color == p.get("color", e.color))
                and (e.linetype is None or e.linetype == p.get("linetype", e.linetype)))

    def item(e: Entity, role: str, anchor: Optional[dict], height=None, target=None) -> None:
        # with the layers stated, the spec's layer and its properties; without, any
        # layer but 0 (nothing is drafted on layer 0)
        nonlocal total, conforming
        total += 1
        want = layers[role]
        bad = []
        if exact_layers and e.layer != want:
            bad.append(Finding("wrong_layer", anchor=anchor, entity_ids=[e.id], expected=want,
                               actual=e.layer))
        elif exact_layers and not overrides_ok(e, want):
            bad.append(Finding("wrong_layer_props", anchor=anchor, entity_ids=[e.id],
                               note="the entity overrides its layer's color or linetype"))
        elif not exact_layers and e.layer == "0":
            bad.append(Finding("wrong_layer", anchor=anchor, entity_ids=[e.id], actual=e.layer,
                               note="drafted on layer 0"))
        if height is not None and not height_ok(height, role, target):
            bad.append(Finding("wrong_height", anchor=anchor, entity_ids=[e.id],
                               expected=target if exact_heights else list(ranges[role]),
                               actual=round(height, 6), note="text height on paper, inches"))
        findings.extend(bad)
        conforming += not bad

    for m in a.labels.matches:
        if m.chosen is not None:
            item(m.chosen.entity, "labels", m.anchor, m.chosen.paper_height(ctx),
                 float(text["label_height_in"]))
    if ctx.asks("ticks"):
        for tm in a.ticks:
            if tm.hits:
                hit = next((h for h in tm.hits if h.entity.layer == layers["ticks"]), tm.hits[0])
                item(hit.entity, "ticks", a.anchor(tm.truth["station_text"], "tick"))
    if a.linework is not None and ctx.asks("linework"):
        for em in a.linework.elements:
            if em.hits:
                hit = next((h for h in em.hits if h.entity.layer == layers["alignment"]),
                           em.hits[0])
                item(hit.entity, "alignment", a.anchor(em.ref, "element"))
    if ctx.asks("table"):
        for ev in a.chosen_tables():
            t = ev.table
            item(t, "tables", dict(ctx.truth.curve_table["anchor"]), float(t.text_height),
                 float(text["table_height_in"]))
    if a.edges is not None:
        for em in a.edges.elements:
            if em.hits:
                hit = next((h for h in em.hits if h.entity.layer == layers["edges"]), em.hits[0])
                item(hit.entity, "edges", a.anchor(em.ref, "edge"))
    for dm in a.dimensions:
        if dm.chosen is not None:
            item(dm.chosen, "dims", dm.anchor, float(dm.chosen.text_height) / ctx.fpi_used,
                 float(text["label_height_in"]))
    block = ctx.spec["sheet"]["north_arrow"]["block"]
    if ctx.asks("north") and "symbols" in layers:
        for sv in ctx.sheets:
            if sv.sheet is None:
                continue
            arrows = [e for e in sv.sheet.entities.values()
                      if isinstance(e, BlockRef) and e.block_name == block]
            for e in arrows[:1]:
                item(e, "symbols", {"ref": sv.name, "kind": "north_arrow"})
    if ctx.asks("sheet") and "match" in layers:
        for sv in ctx.sheets:
            if sv.sheet is None:
                continue
            for m in sv.truth.get("matches") or []:
                found = MatchFound()
                _match_line(a, sv, m, found)
                for e in found.lines[:1] + found.labels[:1]:
                    item(e, "match", a.anchor(m["station_text"], "match_line"))
    work = total
    # the layer set: every standard layer when the task is to set them up, else (at
    # the explicit level) the layers the asked-for work is drawn on
    if ctx.asks("layers"):
        names = list(ctx.spec.get("layer_set") or dict.fromkeys(layers.values()))
    elif exact_layers:
        names = []
        has_matches = any(sv.truth.get("matches") for sv in ctx.sheets)
        for g in GROUP_LAYER_ROLE:
            role = GROUP_LAYER_ROLE[g]
            if g not in ctx.scope or role not in layers or layers[role] in names:
                continue
            if g == "sheet" and not has_matches:
                continue  # a one-sheet layout draws nothing on the match level
            names.append(layers[role])
    else:
        names = []
    for name in names:
        total += 1
        want = props.get(name, {})
        layer = ctx.doc.layers.get(name)
        if layer is None:
            findings.append(Finding("missing", expected=dict(want) if exact_layers else None,
                                    note=f"layer {name} does not exist"))
            continue
        if exact_layers:
            # color, linetype and weight are the standard; the description is a note
            have = {"color": layer.color, "linetype": layer.linetype,
                    "lineweight_mm": layer.lineweight_mm}
            wrong = {k: have[k] for k, v in want.items() if k in have
                     and (abs(float(have[k]) - float(v)) > 1e-6 if k == "lineweight_mm"
                          else have[k] != v)}
            if wrong:
                findings.append(Finding("wrong_layer_props", expected=dict(want), actual=wrong,
                                        note=f"layer {name} properties"))
                continue
        conforming += 1
    if total == 0 or (work == 0 and not ctx.asks("layers")):
        return 0.0, [Finding("missing", note="no required work to judge")] + findings
    return conforming / total, findings


def check_title_block(a: Analysis) -> Result:  # D1-10
    ctx = a.ctx
    credits, findings = [], []
    for sv in ctx.sheets:
        if sv.sheet is None:
            findings.append(Finding("sheet_missing", note=_no_sheet(sv)))
            credits.append(0.0)
            continue
        # a field the prompt gave a value for must carry it; any other need only be
        # filled in -- except the scale, which must always match the viewport used.  A
        # real sheet (tasks.real) names its own border's fields and what each level states
        real = "required_title_fields" in sv.truth
        required = (sv.truth["required_title_fields"] if real
                    else ctx.spec["sheet"]["required_title_fields"])
        stated = (set((sv.truth.get("title_stated") or {}).get(ctx.level, ())) if real
                  else set(ctx.title_stated))
        expected = dict(sv.truth["title_block_fields"])
        fpi = sv.fpi
        if not real:
            expected["scale"] = ctx.spec["sheet"]["scale_text_format"].format(fpi=fpi)
        fields = sv.sheet.title_block_fields
        ok = 0
        for name in required:
            value = fields.get(name)
            if value is None or not str(value).strip():
                findings.append(Finding("missing_field",
                                        note=f"title block field {name} on sheet {sv.name}"))
                continue
            if name == "scale" and name not in stated:
                right = scale_fpi(value) is not None and abs(scale_fpi(value) - fpi) < 1e-9
            elif name in stated:
                right = normalize(value) == normalize(expected.get(name, value))
            else:
                right = True
            if right:
                ok += 1
            else:
                findings.append(Finding("wrong_field", expected=expected.get(name), actual=value,
                                        note=f"title block field {name} on sheet {sv.name}"))
        credits.append(ok / len(required) if required else 1.0)
    return _mean(credits), findings


def check_north_arrow(a: Analysis) -> Result:  # D1-11
    ctx = a.ctx
    block = ctx.spec["sheet"]["north_arrow"]["block"]
    credits, findings = [], []
    for sv in ctx.sheets:
        if sv.sheet is None:
            findings.append(Finding("sheet_missing", note=_no_sheet(sv)))
            credits.append(0.0)
            continue
        refs = [e for e in sv.sheet.entities.values()
                if isinstance(e, BlockRef) and e.block_name == block]
        inside = [e for e in refs
                  if (bb := e.bbox(ctx.doc)) is not None and rect_inside(tuple(bb), sv.usable)]
        north = (sv.truth.get("north_arrow") or {}).get("rotation_deg")
        if inside and north is not None and not any(
                abs((float(e.rotation_deg) - float(north) + 180.0) % 360.0 - 180.0)
                <= NORTH_TOL_DEG for e in inside):
            credits.append(0.5)
            findings.append(Finding("wrong_value", entity_ids=[e.id for e in inside],
                                    expected=float(north),
                                    actual=[float(e.rotation_deg) for e in inside],
                                    note=f"the north arrow on {sv.name} does not point to "
                                         f"north through the turned viewport"))
        elif inside:
            credits.append(1.0)
        elif refs:
            credits.append(0.0)
            findings.append(Finding("off_sheet", entity_ids=[e.id for e in refs],
                                    note=f"the north arrow on {sv.name} is outside the usable "
                                         f"area"))
        else:
            credits.append(0.0)
            findings.append(Finding("missing", note=f"no north arrow on sheet {sv.name}"))
    return _mean(credits), findings


def check_pavement_edges(a: Analysis) -> Result:  # D1-12
    if a.edges is None:
        return 0.0, [Finding("missing", note="no pavement edges in the truth")]
    layer = a.ctx.layers["edges"]
    findings = []
    for em in a.edges.elements:
        anchor = a.anchor(em.ref, "edge")
        if not em.hits:
            findings.append(Finding("missing", anchor=anchor,
                                    note="no linework matches this piece of the pavement edge"))
        elif not any(h.entity.layer == layer for h in em.hits):
            findings.append(Finding("wrong_layer", anchor=anchor,
                                    entity_ids=sorted({h.entity.id for h in em.hits}),
                                    expected=layer,
                                    actual=sorted({h.entity.layer for h in em.hits})))
    matched = sum(1 for em in a.edges.elements if em.hits)
    complete = matched == len(a.edges.elements)
    for e in a.edges.bad_entities:
        findings.append(Finding(
            "extra_linework" if complete else "geometry_mismatch", entity_ids=[e.id],
            note="linework on the pavement edge layer that is not part of the edges" if complete
            else "linework on the pavement edge layer that is not at the pavement width"))
    return (matched / len(a.edges.elements) if a.edges.elements else 1.0), findings


def check_pavement_widths(a: Analysis) -> Result:  # D1-13
    findings, ok = [], 0
    for dm in a.dimensions:
        if dm.chosen is None:
            findings.append(Finding("missing", anchor=dm.anchor,
                                    note="no dimension across the pavement on this tangent"))
        elif not dm.text_ok:
            findings.append(Finding("wrong_value", anchor=dm.anchor, entity_ids=[dm.chosen.id],
                                    expected=dm.truth["text"], actual=dimgeom.text_of(dm.chosen),
                                    note="the width dimension reads wrong"))
        elif not dm.at_station:
            findings.append(Finding("misplaced", anchor=dm.anchor, entity_ids=[dm.chosen.id],
                                    expected=dm.truth["station_text"],
                                    note="the width is dimensioned at another station of this "
                                         "tangent"))
        else:
            ok += 1
    return (ok / len(a.dimensions) if a.dimensions else 1.0), findings


def check_reference(a: Analysis) -> Result:  # D1-14
    ctx = a.ctx
    credits, findings = [], []
    tol = float(ctx.tol["position_model_ft"])
    for want in ctx.truth.references:
        refs = [r for r in ctx.doc.references.values() if Path(r.path).name == want["file"]]
        if not refs:
            findings.append(Finding("missing", expected=want["file"],
                                    note="the base drawing is not attached as a reference"))
            credits.append(0.0)
            continue
        r = sorted(refs, key=lambda r: r.id)[0]
        credit = 0.5
        space_ok = (r.space == want.get("space", "model")) and r.model == "model"
        identity = (geo.distance(r.offset, [0.0, 0.0]) <= tol
                    and abs(r.rotation_deg) <= float(ctx.tol["rotation_deg"])
                    and abs(r.scale - 1.0) <= 1e-6)
        if space_ok and identity:
            credit += 0.25
        else:
            findings.append(Finding("misplaced", entity_ids=[r.id],
                                    expected={"space": want.get("space", "model"), "offset": [0, 0],
                                              "rotation_deg": 0, "scale": 1},
                                    actual={"space": r.space, "offset": list(r.offset),
                                            "rotation_deg": r.rotation_deg, "scale": r.scale,
                                            "model": r.model},
                                    note="the reference is not attached at its own coordinates "
                                         "in model space"))
        if r.visible and r.clip is None and not r.masks:
            credit += 0.25
        else:
            findings.append(Finding("not_visible", entity_ids=[r.id],
                                    note="the reference is hidden or clipped"))
        if ctx.states("match_line") and want.get("name") and r.name != want["name"]:
            findings.append(Finding("wrong_field", entity_ids=[r.id], expected=want["name"],
                                    actual=r.name, note="the reference name"))
        credits.append(credit)
    return _mean(credits), findings


def check_alignment_created(a: Analysis) -> Result:  # D1-15
    """The alignment the prompt described, created in the design: begin
    station, the elements (ends, centers, radii) and the equations, each
    within the spec's tolerances.  A difference is wrong design (hard fail);
    the drawn linework is D1-01's business."""
    ctx = a.ctx
    name, want = ctx.alignment_name, ctx.alignment
    if want is None:
        return 0.0, [Finding("missing", note="the truth has no alignment")]
    # where the design lives: this document, or the base drawing (a truth marked BASE_SCOPE)
    home = design_home(ctx.doc, ctx.truth)
    have = home.design.alignments.get(name) if home is not None else None
    if have is None:
        return 0.0, [Finding("missing", anchor={"alignment": name, "ref": name, "kind": "alignment"},
                             note="no alignment of this name in the design")]
    tol_p, tol_s, tol_l = (float(ctx.tol["position_model_ft"]), float(ctx.tol["station_ft"]),
                           float(ctx.tol["length_ft"]))
    findings, ok = [], 0
    total = 1 + len(want.elements) + len(want.equations)

    def near(p, q) -> bool:
        return geo.distance(p, q) <= tol_p

    if abs(float(have.begin_station) - float(want.begin_station)) <= tol_s:
        ok += 1
    else:
        findings.append(Finding("wrong_value", anchor={"alignment": name, "ref": "BEGIN",
                                                       "kind": "begin_station"},
                                expected=format_station(want.begin_station),
                                actual=format_station(have.begin_station),
                                note="the alignment begins at the wrong station"))
    kinds_want = [el.kind for el in want.elements]
    kinds_have = [el.kind for el in have.elements]
    if kinds_have != kinds_want:
        findings.append(Finding("wrong_value", anchor={"alignment": name, "ref": "elements",
                                                       "kind": "elements"},
                                expected=kinds_want, actual=kinds_have,
                                note="the alignment does not have the tangents and curves "
                                     "described"))
    else:
        for i, (w, h) in enumerate(zip(want.elements, have.elements)):
            anchor = {"alignment": name, "ref": want.element_ref(i), "kind": w.kind}
            if w.kind == "tangent":
                good = near(w.start, h.start) and near(w.end, h.end)
            else:
                good = (near(w.pc, h.pc) and near(w.pt, h.pt) and near(w.center, h.center)
                        and abs(float(w.radius) - float(h.radius)) <= tol_l)
            if good:
                ok += 1
            else:
                findings.append(Finding("wrong_value", anchor=anchor,
                                        note=f"{want.element_ref(i)} is not where the PIs and "
                                             f"radii put it"))
    if len(have.equations) != len(want.equations):
        findings.append(Finding("wrong_value", anchor={"alignment": name, "ref": "equations",
                                                       "kind": "equations"},
                                expected=len(want.equations), actual=len(have.equations),
                                note="the alignment does not have the station equations "
                                     "described"))
    else:
        for n, (w, h) in enumerate(zip(want.equations, have.equations), start=1):
            if (abs(float(w.back) - float(h.back)) <= tol_s
                    and abs(float(w.ahead) - float(h.ahead)) <= tol_s):
                ok += 1
            else:
                findings.append(Finding("wrong_value", anchor={"alignment": name,
                                                               "ref": f"EQ-{n}",
                                                               "kind": "equation"},
                                        expected=f"{format_station(w.back)} BK = "
                                                 f"{format_station(w.ahead)} AH",
                                        actual=f"{format_station(h.back)} BK = "
                                               f"{format_station(h.ahead)} AH",
                                        note="the station equation reads wrong"))
    return ok / total, findings


def check_callouts(a: Analysis) -> Result:  # D1-16 (EXTRA_CHECKS)
    """Each construction callout the task asks for: placed by ``place_callout``
    (its record), reading the note as given, visible on the sheet, its leader
    tip within the paper tolerance of the station and offset called out, seen
    through the viewport the sheet is drawn through (``expected_callout_tip``).
    A callout at one of those points that reads none of the notes is wrong work
    on the sheet (``wrong_value``); a missing or misplaced one costs credit."""
    ctx = a.ctx
    if not ctx.truth.callouts:
        return 0.0, [Finding("missing", note="no construction callouts in the truth")]
    tol = float(ctx.tol["position_paper_in"])
    findings: List[Finding] = []
    ok = 0
    for m in a.callouts:
        if m.wrong is not None:
            findings.append(Finding("wrong_value", anchor=m.anchor, entity_ids=[m.wrong.text.id],
                                    expected=m.truth["content"], actual=m.wrong.text.content,
                                    note="the callout at this point reads another note"))
        c = m.chosen
        if c is None:
            if m.by_hand is not None:
                findings.append(Finding("unanchored", anchor=m.anchor, entity_ids=[m.by_hand.id],
                                        note="the note was typed as text, not placed as a "
                                             "callout"))
            elif m.wrong is None:
                findings.append(Finding("missing", anchor=m.anchor,
                                        note="no callout reads this note"))
            continue
        if (c.text.anchor or {}).get("placed_by") != "place_callout":
            findings.append(Finding("unanchored", anchor=m.anchor, entity_ids=[c.text.id],
                                    note="the callout's record was not placed by the callout "
                                         "command"))
            continue
        if c.tip is None:
            findings.append(Finding("misplaced", anchor=m.anchor, entity_ids=[c.text.id],
                                    note="no leader reaches the note"))
            continue
        if not c.visible:
            findings.append(Finding("not_visible", anchor=m.anchor, entity_ids=[c.text.id],
                                    note="the note is not on the deliverable sheet"))
            continue
        if m.distance is None or m.distance > tol:
            findings.append(Finding("misplaced", anchor=m.anchor, entity_ids=[c.text.id],
                                    expected=[round(v, 3) for v in m.expected],
                                    actual=[round(v, 3) for v in c.tip],
                                    note=f"the leader tip is {m.distance:.2f} in from the point "
                                         f"called out"))
            continue
        ok += 1
    return ok / len(a.callouts), findings


CHECKS: Dict[str, Callable[[Analysis], Result]] = {
    "D1-16": check_callouts,
    "D1-00": check_sheet_setup,
    "D1-01": check_linework,
    "D1-02": check_ticks,
    "D1-03": lambda a: _check_labels(a, "D1-03"),
    "D1-04": lambda a: _check_labels(a, "D1-04"),
    "D1-05": lambda a: _check_labels(a, "D1-05"),
    "D1-06": check_curve_table,
    "D1-07": check_anchored_position,
    "D1-08": check_legibility,
    "D1-09": check_standards,
    "D1-10": check_title_block,
    "D1-11": check_north_arrow,
    "D1-12": check_pavement_edges,
    "D1-13": check_pavement_widths,
    "D1-14": check_reference,
    "D1-15": check_alignment_created,
}

__all__ = ["CHECKS", "Analysis", "analyze", "evaluate_table", "TableEval", "TableResult"]

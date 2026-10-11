"""Fixture builders for the verifier's validation suite (eval plan section 3.6).

``Base`` is a task drafted by its reference solution, which the verifier
scores 100.  A ``Mutation`` changes one thing about that drawing -- through
the command bus wherever the bus can make the change, so provenance is
stamped the way an agent's would be -- and says which checks must move, to
what credit, with which finding codes.  Every check not named must stay at
full credit with no findings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Union

from roaddraft.document.entities import BlockRef, Line, Table, Text
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.verify import verify
from roaddraft.verify.match import KIND_CHECK
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1 as _SPEC
_L = _SPEC["layers"]

SHEET = "C-101"
#: the default base: three curves, a station equation, 1" = 100'
BASE = {"seed": 1, "curves": 3, "equations": True}


class Base:
    """A reference-drafted task and helpers to find and change what is on it."""

    def __init__(self, seed: int, curves: Optional[int] = None, equations: bool = False):
        self.task = generate_task(seed, curves=curves, equations=equations)
        self.session = session_for_task(self.task)
        reference_solution(self.task, self.session)
        self.truth = self.task.truth
        self.D = self.task.brief.deliverable
        self.A = self.task.brief.alignment_name

    @property
    def doc(self):
        return self.session.doc

    @property
    def sheet(self):
        return self.doc.sheet_by_ref(SHEET)

    def ex(self, command: str, params: dict) -> dict:
        result = self.session.execute(command, params)
        assert result["ok"], (command, result.get("error"))
        return result

    def verify(self, level: str = "explicit"):
        return verify(self.doc, self.truth, prompt_level=level)

    # ------------------------------------------------------------- lookups

    def labels(self, kind: Optional[str] = None) -> List[Text]:
        out = []
        for space in [self.doc.model_entities, self.sheet.entities]:
            for e in space.values():
                if isinstance(e, Text) and e.anchor and (kind is None or e.anchor["kind"] == kind):
                    out.append(e)
        return out

    def label(self, ref: str, kind: str) -> Text:
        found = [e for e in self.labels(kind) if e.anchor["ref"] == ref]
        assert len(found) == 1, (ref, kind, found)
        return found[0]

    def ticks(self) -> List[Line]:
        return [e for e in self.doc.model_entities.values()
                if isinstance(e, Line) and e.anchor and e.anchor["kind"] == "tick"]

    def elements(self):
        return [e for e in self.doc.model_entities.values()
                if e.anchor and e.anchor["kind"] == "element"]

    def table(self) -> Table:
        return next(e for e in self.sheet.entities.values() if isinstance(e, Table))

    def north_arrow(self) -> BlockRef:
        return next(e for e in self.sheet.entities.values() if isinstance(e, BlockRef))

    @property
    def viewport(self):
        return self.sheet.viewports[0]

    # -------------------------------------------------------------- counts

    def n(self, check_id: str) -> int:
        """Truth labels scored by ``check_id``."""
        return sum(1 for label in self.truth.labels if KIND_CHECK.get(label["kind"]) == check_id)

    @property
    def n_labels(self) -> int:
        return len(self.truth.labels)

    @property
    def n_ticks(self) -> int:
        return len(self.truth.ticks)

    @property
    def n_elements(self) -> int:
        return len(self.truth.elements)

    @property
    def n_curves(self) -> int:
        return self.truth.counts["curves"]

    @property
    def d109_total(self) -> int:
        """D1-09's items on the reference: every label, tick, element, the
        table, the north arrow, and the layers the layout draws on (the
        alignment, its annotation, the curve table, the north arrow's)."""
        return self.n_labels + self.n_ticks + self.n_elements + 1 + 1 + 4

    def free_model_point(self):
        """A model point inside the viewport that no text or table covers on paper."""
        from roaddraft.verify.context import Context
        from roaddraft.verify.legibility import sheet_items, text_quad, overlap_depth
        from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
        ctx = Context.build(self.doc, self.truth, DRAFTING_SPEC_V1)
        items = sheet_items(ctx)
        view = ctx.views[0]
        x0, y0, x1, y1 = view.window
        h = float(self.D["text_heights"]["model_label_ft"])
        fpi = float(view.vp.feet_per_inch)
        for i in range(1, 20):
            for j in range(1, 20):
                q = [x0 + (x1 - x0) * i / 20.0, y0 + (y1 - y0) * j / 20.0]
                quad = text_quad(q, "BC 000+00.00", h / fpi, 0.0, "center", "middle")
                if all(overlap_depth(quad, it.quad) < -0.25 for it in items):
                    return view.transform.to_model(q)
        raise AssertionError("no free spot on the sheet")


Credit = Union[float, Callable[[Base], float]]


@dataclass
class Mutation:
    name: str
    apply: Callable[[Base], None]
    credits: Dict[str, Credit] = field(default_factory=dict)
    codes: Dict[str, Set[str]] = field(default_factory=dict)
    hard_fail: bool = False
    tampered: bool = False
    base: dict = field(default_factory=lambda: dict(BASE))


# ----------------------------------------------------------------- builders


def _delete(b: Base, ids):
    b.ex("delete_entities", {"ids": list(ids)})


def _set(b: Base, eid: str, **changes):
    b.ex("modify_entity", {"id": eid, "changes": changes})


def _first_station(b: Base) -> Text:
    return b.labels("station")[3]


def _station_label_params(b: Base, text: Text, **over) -> dict:
    p = {"space": "model", "alignment": b.A, "anchor": text.anchor["ref"], "kind": "station",
         "label_offset": b.D["label_offset_ft"], "height": b.D["text_heights"]["model_label_ft"],
         "layer": _L["labels"]}
    p.update(over)
    return p


def _rewrite_ref(b: Base):
    e = b.label("PC-1", "pc")
    _set(b, e.id, anchor={**e.anchor, "ref": "PC-2"})


def _delete_region2_ticks(b: Base):
    st = b.doc.design.alignments[b.A].stations()
    region2 = [t for t in b.ticks() if st.to_display(t.anchor["station"])[1] == 2]
    assert region2
    _delete(b, [t.id for t in region2])


def _region1_share(b: Base) -> float:
    st = b.doc.design.alignments[b.A].stations()
    n1 = sum(1 for t in b.truth.ticks if st.to_display(t["station"])[1] == 1)
    return n1 / b.n_ticks


def _bump_radius_cell(b: Base):
    t = b.table()
    col = [c["header"] for c in t.columns].index("R")
    rows = [list(r) for r in t.rows]
    rows[0][col] = "%.2f'" % (float(rows[0][col].rstrip("'")) + 0.10)
    _set(b, t.id, rows=rows)


def _drop_row(b: Base):
    t = b.table()
    _set(b, t.id, rows=[list(r) for r in t.rows[:-1]])


def _table_as_place_table(b: Base):
    t = b.table()
    _delete(b, [t.id])
    b.ex("place_table", {"space": SHEET, "position": list(t.position), "title": t.title,
                         "columns": [dict(c) for c in t.columns],
                         "rows": [list(r) for r in t.rows], "text_height": t.text_height,
                         "layer": t.layer})


def _overlap_text(b: Base):
    e = _first_station(b)
    b.ex("place_text", {"space": "model", "position": list(e.position), "content": "XX+XX.XX",
                        "height": e.height, "rotation_deg": e.rotation_deg, "halign": e.halign,
                        "valign": e.valign, "layer": _L["labels"]})


def _label_off_sheet(b: Base):
    e = _first_station(b)
    _delete(b, [e.id])
    b.ex("place_label", {"space": SHEET, "alignment": b.A, "anchor": e.anchor["ref"],
                         "kind": "station", "label_offset": 40.0, "layer": _L["labels"]})


def _polyline_alignment(b: Base):
    _delete(b, [e.id for e in b.elements()])
    pis = b.doc.design.alignments[b.A].pis
    b.ex("draw_polyline", {"space": "model", "vertices": [list(p.point) for p in pis],
                           "layer": _L["alignment"]})


def _extra_line(b: Base):
    p = b.free_model_point()
    b.ex("draw_line", {"space": "model", "start": p, "end": [p[0] + 50.0, p[1]],
                       "layer": _L["alignment"]})


def _via_viewport(b: Base):
    e = b.label("PC-1", "pc")
    _delete(b, [e.id])
    b.ex("place_label", {"space": SHEET, "alignment": b.A, "anchor": "PC-1", "kind": "pc",
                         "layer": _L["labels"]})


def _side_offset(b: Base):
    e = b.label("T-1", "bearing")
    _delete(b, [e.id])
    b.ex("place_label", {"space": "model", "alignment": b.A, "anchor": "T-1", "kind": "bearing",
                         "side": "right", "label_offset": 4.0 * b.D["label_offset_ft"],
                         "height": b.D["text_heights"]["model_label_ft"], "layer": _L["labels"]})


def _free_bc_text(b: Base):
    content = b.label("PC-1", "pc").content
    b.ex("place_text", {"space": "model", "position": b.free_model_point(), "content": content,
                        "height": b.D["text_heights"]["model_label_ft"], "halign": "center",
                        "valign": "middle", "layer": _L["labels"]})


def _nudge_bearing(text: str) -> str:
    """The same bearing a minute off."""
    from roaddraft.design.angles import format_bearing, parse_bearing
    return format_bearing(parse_bearing(text) + 1.0 / 60.0)


def _wrong_equation(b: Base):
    e = b.label("EQ-1", "equation")
    eq = b.doc.design.alignments[b.A].equations[0]
    from roaddraft.core.units import format_station
    _set(b, e.id, content=e.content.replace(format_station(eq.ahead),
                                            format_station(eq.ahead + 100.0)))


def _duplicate_station(b: Base):
    e = _first_station(b)
    b.ex("place_label", _station_label_params(b, e))


def _short_table(b: Base):
    t = b.table()
    _delete(b, [t.id])
    cols = [c for c in b.D["curve_table_columns"] if c != "chord_bearing"]
    b.ex("place_curve_table", {"space": SHEET, "alignment": b.A, "position": list(t.position),
                               "columns": cols, "text_height": t.text_height, "layer": t.layer})


def _modify_radius(b: Base):
    arc = next(e for e in b.elements() if e.anchor["ref"] == "C-2")
    _set(b, arc.id, radius=arc.radius + 1.0)


def _tampered(b: Base):
    align = b.doc.design.alignments[b.A]
    b.ex("modify_alignment", {"name": b.A, "changes": {"begin_station": align.begin_station
                                                       + 100.0}})


def frac(check: str, minus: int = 1) -> Callable[[Base], float]:
    return lambda b: (b.n(check) - minus) / b.n(check)


def d109(minus: Union[int, Callable[[Base], int]]) -> Callable[[Base], float]:
    return lambda b: (b.d109_total - (minus(b) if callable(minus) else minus)) / b.d109_total


def table_rows(lost: int) -> Callable[[Base], float]:
    return lambda b: 0.2 + 0.8 * (b.n_curves - lost) / b.n_curves


def d107(minus: int = 1) -> Callable[[Base], float]:
    return lambda b: (b.n_labels - minus) / b.n_labels


MUTATIONS: List[Mutation] = [
    Mutation("delete the EC-2 label", lambda b: _delete(b, [b.label("PT-2", "pt").id]),
             {"D1-04": frac("D1-04")}, {"D1-04": {"missing"}}),
    Mutation("a station label reads 18+00, not 18+00.00",
             lambda b: _set(b, _first_station(b).id,
                            content=_first_station(b).content.replace(".00", "")),
             {"D1-03": frac("D1-03")}, {"D1-03": {"wrong_value"}}, hard_fail=True),
    Mutation("drag the BC-1 label 5 ft",
             lambda b: b.ex("move_entities", {"ids": [b.label("PC-1", "pc").id],
                                              "delta": [5.0, 0.0]}),
             {"D1-07": d107()}, {"D1-07": {"misplaced"}}),
    Mutation("rewrite the BC-1 label's anchor to PC-2", _rewrite_ref,
             {"D1-04": frac("D1-04"), "D1-07": d107()},
             {"D1-04": {"missing"}, "D1-07": {"anchor_inconsistent"}}),
    Mutation("delete every tick past the station equation", _delete_region2_ticks,
             {"D1-02": _region1_share}, {"D1-02": {"missing"}}),
    Mutation("a tick moved 0.1 ft",
             lambda b: b.ex("move_entities", {"ids": [b.ticks()[2].id], "delta": [0.1, 0.0]}),
             {"D1-02": lambda b: (b.n_ticks - 1) / b.n_ticks}, {"D1-02": {"misplaced"}}),
    Mutation("curve table R off by 0.10 ft", _bump_radius_cell,
             {"D1-06": table_rows(1)}, {"D1-06": {"wrong_value"}}, hard_fail=True),
    Mutation("drop a curve table row", _drop_row,
             {"D1-06": table_rows(1)}, {"D1-06": {"missing"}}),
    Mutation("curve table rebuilt with place_table", _table_as_place_table,
             {"D1-06": 0.0}, {"D1-06": {"missing", "unanchored"}}),
    Mutation("every label on layer 0",
             lambda b: [_set(b, e.id, layer="0") for e in b.labels()],
             {"D1-09": d109(lambda b: b.n_labels)}, {"D1-09": {"wrong_layer"}}),
    Mutation("one label 3 ft high", lambda b: _set(b, _first_station(b).id, height=3.0),
             {"D1-09": d109(1)}, {"D1-09": {"wrong_height"}}),
    Mutation("raw text on top of a station label", _overlap_text,
             {"D1-08": 0.75}, {"D1-08": {"overlap"}, "D1-07": {"unanchored"}}),
    Mutation("a station label placed outside the usable area", _label_off_sheet,
             {"D1-03": frac("D1-03"), "D1-08": 0.75},
             {"D1-03": {"not_visible"}, "D1-08": {"off_sheet"}}),
    Mutation("viewport at 1\" = 120'",
             lambda b: b.ex("modify_viewport", {"sheet": SHEET, "viewport_id": b.viewport.id,
                                                "changes": {"feet_per_inch": 120.0}}),
             {"D1-00": 0.75, "D1-10": 0.9, "D1-09": d109(lambda b: b.n_labels)},
             {"D1-00": {"viewport_scale"}, "D1-10": {"wrong_field"}, "D1-09": {"wrong_height"}}),
    Mutation("alignment drawn as a polyline through the PIs", _polyline_alignment,
             {"D1-01": 0.0},
             {"D1-01": {"missing", "geometry_mismatch"}}, hard_fail=True),
    Mutation("alignment on layer 0",
             lambda b: [_set(b, e.id, layer="0") for e in b.elements()],
             {"D1-09": d109(lambda b: b.n_elements)},
             {"D1-01": {"wrong_layer"}, "D1-09": {"wrong_layer"}}),
    Mutation("an extra line on the alignment layer", _extra_line,
             {}, {"D1-01": {"extra_linework"}}, hard_fail=True),
    Mutation("title block without checked_by",
             lambda b: b.ex("fill_title_block", {"sheet": SHEET, "fields": {"checked_by": ""}}),
             {"D1-10": 0.9}, {"D1-10": {"missing_field"}}),
    Mutation("scale text 1\" = 50' at 1\" = 100'",
             lambda b: b.ex("fill_title_block", {"sheet": SHEET,
                                                 "fields": {"scale": "1\" = 50'"}}),
             {"D1-10": 0.9}, {"D1-10": {"wrong_field"}}),
    Mutation("north arrow deleted", lambda b: _delete(b, [b.north_arrow().id]),
             {"D1-11": 0.0}, {"D1-11": {"missing"}}),
    Mutation("north arrow off the sheet",
             lambda b: b.ex("move_entities", {"ids": [b.north_arrow().id],
                                              "delta": [10.0, 10.0]}),
             {"D1-11": 0.0, "D1-08": 0.75}, {"D1-11": {"off_sheet"}, "D1-08": {"off_sheet"}}),
    Mutation("begin station edited in the design", _tampered, tampered=True, hard_fail=True),
    Mutation("BC-1 lettered on the sheet through the viewport", _via_viewport),
    Mutation("a bearing moved to the right side and further out", _side_offset),
    Mutation("free-floating text that reads like BC-1", _free_bc_text,
             {}, {"D1-07": {"unanchored"}}),
    Mutation("every bearing deleted", lambda b: _delete(b, [e.id for e in b.labels("bearing")]),
             {"D1-05": 0.0}, {"D1-05": {"missing"}}),
    Mutation("a bearing a minute off",
             lambda b: _set(b, b.label("T-1", "bearing").id,
                            content=_nudge_bearing(b.label("T-1", "bearing").content)),
             {"D1-05": frac("D1-05")}, {"D1-05": {"wrong_value"}}, hard_fail=True),
    Mutation("the C-2 callout deleted", lambda b: _delete(b, [b.label("MC-2", "mc").id]),
             {"D1-04": frac("D1-04")}, {"D1-04": {"missing"}}),
    Mutation("the station equation reads the wrong ahead station", _wrong_equation,
             {"D1-03": frac("D1-03")}, {"D1-03": {"wrong_value"}}, hard_fail=True),
    Mutation("a station label placed twice", _duplicate_station,
             {"D1-08": 0.75}, {"D1-03": {"duplicate"}, "D1-08": {"overlap"}}),
    Mutation("curve table without its chord bearing column", _short_table,
             {"D1-06": 0.0}, {"D1-06": {"wrong_field"}}),
    Mutation("the sheet deleted", lambda b: b.ex("delete_sheet", {"sheet": SHEET}),
             {"D1-00": 0.0, "D1-03": 0.0, "D1-04": 0.0, "D1-05": 0.0, "D1-06": 0.0,
              "D1-08": 0.0, "D1-10": 0.0, "D1-11": 0.0},
             {"D1-00": {"sheet_missing"}, "D1-03": {"not_visible"}, "D1-04": {"not_visible"},
              "D1-05": {"not_visible"}, "D1-06": {"missing"}, "D1-08": {"sheet_missing"},
              "D1-10": {"sheet_missing"}, "D1-11": {"sheet_missing"}}),
    Mutation("alignment layer drawn blue",
             lambda b: b.ex("modify_layer", {"name": _L["alignment"],
                                             "changes": {"color": "blue"}}),
             {"D1-09": d109(1)}, {"D1-09": {"wrong_layer_props"}}),
    Mutation("curve C-2 drawn 1 ft too wide", _modify_radius,
             {"D1-01": lambda b: (b.n_elements - 1) / b.n_elements},
             {"D1-01": {"missing", "geometry_mismatch"}}, hard_fail=True),
]

__all__ = ["Base", "Mutation", "MUTATIONS", "BASE", "SHEET"]

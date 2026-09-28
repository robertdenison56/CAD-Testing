"""The project the find-probes run against: a design file and a plan set that
references it.

Deterministic and self-contained, so a probe run is reproducible: the same
alignment, the same offsets, the same three sheets every time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from roaddraft.api.session import Session

#: ~4,600 ft of two-lane highway: tangent, 1,200 ft curve right, tangent,
#: 900 ft curve left, tangent. Long enough to need three sheets at 1"=50'.
PIS = [
    [1000.0, 1000.0],
    [2600.0, 1000.0, 1200.0],
    [4100.0, 1500.0, 900.0],
    [5600.0, 1500.0],
]
BEGIN_STATION = "10+00"
EDGE_OFFSETS = [-12.0, 12.0]        # a 24 ft pavement
SHOULDER_OFFSETS = [-20.0, 20.0]    # 8 ft shoulders
ALIGNMENT = "SR-100"

LAYERS = [
    {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center", "lineweight_mm": 0.35},
    {"name": "V-ROAD-EOP", "color": "yellow", "lineweight_mm": 0.35},
    {"name": "V-ROAD-SHLD", "color": "gray", "linetype": "dashed", "lineweight_mm": 0.18},
    {"name": "V-ANNO-TEXT", "color": "black", "lineweight_mm": 0.25},
]

SHEETS = ["C-101", "C-102", "C-103"]
FEET_PER_INCH = 50.0
VIEWPORT = {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5}

MODEL_FILE = "SR-100.model.rdoc.json"
SHEET_FILE = "SR-100.sheets.rdoc.json"
BLANK_FILE = "DESIGN.model.rdoc.json"
CENTERLINE_FILE = "SR-100.centerline.rdoc.json"

#: the document an agent is handed, by Probe.start
START = {"sheets": SHEET_FILE, "model": MODEL_FILE, "blank": BLANK_FILE,
         "centerline": CENTERLINE_FILE}


def check(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


def build_model(out: Path) -> Path:
    """The design: alignment, pavement edges, shoulders. No sheets, no labels."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    check(s.execute("create_alignment", {"name": ALIGNMENT, "begin_station": BEGIN_STATION,
                                         "pis": PIS, "description": "SR-100 mainline"}))
    check(s.execute("draw_alignment", {"alignment": ALIGNMENT, "layer": "V-ALIGN-CNTR"}))
    check(s.execute("draw_offset", {"alignment": ALIGNMENT, "offsets": EDGE_OFFSETS,
                                    "layer": "V-ROAD-EOP"}))
    check(s.execute("draw_offset", {"alignment": ALIGNMENT, "offsets": SHOULDER_OFFSETS,
                                    "layer": "V-ROAD-SHLD"}))
    path = out / MODEL_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_sheets(out: Path, model_path: Path) -> Path:
    """The plans: three sheets over the referenced model, title blocks empty."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    path = out / SHEET_FILE
    # Save first so the relative reference resolves from the sheet file's own
    # folder, the way it will when the file is opened again later.
    check(s.query("save_document", {"path": str(path)}))
    check(s.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                         "path": model_path.name}))

    reference = Session.load(model_path, out_dir=out)
    align = reference.doc.design.alignments[ALIGNMENT]
    x0, _y0, _x1, y1 = align.bbox()
    per_sheet = VIEWPORT["width_in"] * FEET_PER_INCH
    mid_y = (align.bbox()[1] + y1) / 2.0
    for i, name in enumerate(SHEETS):
        check(s.execute("create_sheet", {"name": name, "size": "ANSI_D"}))
        check(s.execute("create_viewport", {
            "sheet": name, "feet_per_inch": FEET_PER_INCH,
            "model_center": [x0 + per_sheet * (i + 0.5), mid_y], **VIEWPORT}))
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_blank(out: Path) -> Path:
    """A design file with the office's layers and nothing drawn: where a
    drafting job starts."""
    s = Session(project_name="Design model", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    path = out / BLANK_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_centerline(out: Path) -> Path:
    """SR-100 with its alignment designed and drawn, and no roadway on it yet."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    check(s.execute("create_alignment", {"name": ALIGNMENT, "begin_station": BEGIN_STATION,
                                         "pis": PIS, "description": "SR-100 mainline"}))
    check(s.execute("draw_alignment", {"alignment": ALIGNMENT, "layer": "V-ALIGN-CNTR"}))
    path = out / CENTERLINE_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def start_document(out: Path, start: str = "sheets") -> Path:
    """Build the fixture under ``out`` and return the document a probe with
    this ``start`` hands to the agent."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if start == "blank":
        return build_blank(out)
    if start == "centerline":
        return build_centerline(out)
    if start not in START:
        raise KeyError(f"no start document {start!r}; one of {sorted(START)}")
    model_path, sheet_path = build(out)
    return model_path if start == "model" else sheet_path


def build(out: Path) -> Tuple[Path, Path]:
    """``(model path, sheet path)``, created fresh under ``out``."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = build_model(out)
    return model_path, build_sheets(out, model_path)


__all__ = ["START", "BLANK_FILE", "CENTERLINE_FILE", "build_blank", "build_centerline",
           "start_document", "PIS", "BEGIN_STATION", "EDGE_OFFSETS", "SHOULDER_OFFSETS", "ALIGNMENT",
           "LAYERS", "SHEETS", "FEET_PER_INCH", "VIEWPORT", "MODEL_FILE", "SHEET_FILE",
           "build", "build_model", "build_sheets"]

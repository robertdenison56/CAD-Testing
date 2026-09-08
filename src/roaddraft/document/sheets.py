"""Sheets: paper-space layouts (AutoCAD layout / MicroStation sheet model).

A sheet has a size in inches, a title block (semantic fields + a drawn
template), its own annotation entities in paper coordinates, and viewports that
window into model space at a plot scale (feet per inch) with optional view
twist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from roaddraft.core.geometry import ViewportTransform
from roaddraft.document.entities import (
    Entity, as_point, as_positive, entity_from_dict,
)

# (width_in, height_in), landscape
SHEET_SIZES = {
    "ANSI_A": (11.0, 8.5),
    "ANSI_B": (17.0, 11.0),
    "ANSI_C": (22.0, 17.0),
    "ANSI_D": (34.0, 22.0),
    "ARCH_D": (36.0, 24.0),
    "ARCH_E": (48.0, 36.0),
}

BORDER_MARGIN_IN = 0.5
TITLE_STRIP_H_IN = 1.25

# Field keys the standard title-block template displays.
STANDARD_TITLE_FIELDS = [
    "project", "agency", "sheet_title", "sheet_number", "total_sheets",
    "designed_by", "drawn_by", "checked_by", "date", "scale",
]


@dataclass
class Viewport:
    id: str
    center_paper: list
    width_in: float
    height_in: float
    model_center: list
    feet_per_inch: float
    rotation_deg: float = 0.0

    def transform(self) -> ViewportTransform:
        return ViewportTransform(self.center_paper, self.model_center,
                                 self.feet_per_inch, self.rotation_deg)

    def paper_bbox(self):
        cx, cy = self.center_paper
        return (cx - self.width_in / 2, cy - self.height_in / 2,
                cx + self.width_in / 2, cy + self.height_in / 2)

    def to_dict(self):
        return {
            "id": self.id,
            "center_paper": list(self.center_paper),
            "width_in": self.width_in,
            "height_in": self.height_in,
            "model_center": list(self.model_center),
            "feet_per_inch": self.feet_per_inch,
            "rotation_deg": self.rotation_deg,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], center_paper=as_point(d["center_paper"]),
                   width_in=as_positive(d["width_in"], "width_in"),
                   height_in=as_positive(d["height_in"], "height_in"),
                   model_center=as_point(d["model_center"]),
                   feet_per_inch=as_positive(d["feet_per_inch"],
                                             "feet_per_inch"),
                   rotation_deg=float(d.get("rotation_deg", 0.0)))


@dataclass
class Sheet:
    id: str
    name: str
    size: str = "ANSI_D"
    width_in: float = 34.0
    height_in: float = 22.0
    title_block_template: str = "standard"
    title_block_fields: Dict[str, str] = field(default_factory=dict)
    viewports: List[Viewport] = field(default_factory=list)
    entities: Dict[str, Entity] = field(default_factory=dict)

    def usable_area(self):
        """Paper rect inside the border and above the title strip:
        (x0, y0, x1, y1) in inches."""
        m = BORDER_MARGIN_IN
        return (m, m + TITLE_STRIP_H_IN, self.width_in - m, self.height_in - m)

    def paper_bbox(self):
        return (0.0, 0.0, self.width_in, self.height_in)

    def viewport_by_id(self, vp_id):
        for vp in self.viewports:
            if vp.id == vp_id:
                return vp
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "width_in": self.width_in,
            "height_in": self.height_in,
            "title_block_template": self.title_block_template,
            "title_block_fields": dict(self.title_block_fields),
            "viewports": [vp.to_dict() for vp in self.viewports],
            "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"], name=d["name"], size=d.get("size", "ANSI_D"),
            width_in=float(d["width_in"]), height_in=float(d["height_in"]),
            title_block_template=d.get("title_block_template", "standard"),
            title_block_fields=dict(d.get("title_block_fields", {})),
            viewports=[Viewport.from_dict(v) for v in d.get("viewports", [])],
            entities={eid: entity_from_dict(ed)
                      for eid, ed in d.get("entities", {}).items()},
        )

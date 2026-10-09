"""The document: one project file holding model space, sheets, and shared
resource tables (layers, text styles, blocks) — the same skeleton as an
AutoCAD DWG (model space + layouts) or a MicroStation design file (design
model + sheet models).

Fully JSON-serializable via to_dict/from_dict; that JSON is the state an AI
agent sees. ID counters are stored in the document so command replay is
deterministic. The design model (alignments, profiles) rides along under
"design" so snapshots, undo, journals, and saves cover it with no bus changes.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.model import DesignModel
from roaddraft.document.annotation import default_settings as _annotation_defaults
from roaddraft.document.entities import (
    Circle, Entity, Polyline, Text, entity_from_dict,
)
from roaddraft.document.references import Reference
from roaddraft.document.sheets import Sheet

SCHEMA_VERSION = "0.2"

LINETYPES = ("continuous", "dashed", "center", "hidden", "dot", "phantom")

ID_PREFIXES = {
    "line": "LN", "polyline": "PL", "arc": "AR", "circle": "CI",
    "text": "TX", "blockref": "BR", "table": "TB", "dimension": "DM",
    "point": "CP", "hatch": "HT",
    "sheet": "SH", "viewport": "VP", "reference": "RF",
}


@dataclass
class Layer:
    name: str
    color: str = "black"
    linetype: str = "continuous"
    lineweight_mm: float = 0.25
    description: str = ""
    visible: bool = True

    def to_dict(self):
        return {"name": self.name, "color": self.color, "linetype": self.linetype,
                "lineweight_mm": self.lineweight_mm, "description": self.description,
                "visible": self.visible}

    @classmethod
    def from_dict(cls, d):
        return cls(name=d["name"], color=d.get("color", "black"),
                   linetype=d.get("linetype", "continuous"),
                   lineweight_mm=float(d.get("lineweight_mm", 0.25)),
                   description=d.get("description", ""),
                   visible=bool(d.get("visible", True)))


@dataclass
class TextStyle:
    name: str
    font: str = "DejaVu Sans"
    width_factor: float = 1.0
    default_height: float = 0.12

    def to_dict(self):
        return {"name": self.name, "font": self.font,
                "width_factor": self.width_factor,
                "default_height": self.default_height}

    @classmethod
    def from_dict(cls, d):
        return cls(name=d["name"], font=d.get("font", "DejaVu Sans"),
                   width_factor=float(d.get("width_factor", 1.0)),
                   default_height=float(d.get("default_height", 0.12)))


@dataclass
class BlockDef:
    """Named symbol definition (AutoCAD block / MicroStation cell). Entities are
    in block-local coordinates; base_point maps to the insertion point."""
    name: str
    base_point: list = field(default_factory=lambda: [0.0, 0.0])
    entities: List[Entity] = field(default_factory=list)
    description: str = ""

    def to_dict(self):
        return {"name": self.name, "base_point": list(self.base_point),
                "entities": [e.to_dict() for e in self.entities],
                "description": self.description}

    @classmethod
    def from_dict(cls, d):
        return cls(name=d["name"], base_point=list(d.get("base_point", [0, 0])),
                   entities=[entity_from_dict(ed) for ed in d.get("entities", [])],
                   description=d.get("description", ""))


def _north_arrow_block() -> BlockDef:
    return BlockDef(
        name="NORTH_ARROW",
        base_point=[0.0, 0.0],
        description="North arrow symbol; insert at sheet scale (units are inches on sheets)",
        entities=[
            Circle(id="B1", center=[0.0, 0.0], radius=1.0),
            Polyline(id="B2", vertices=[[0.0, -0.75], [0.0, 0.6]]),
            Polyline(id="B3", vertices=[[-0.22, 0.25], [0.0, 0.75], [0.22, 0.25]],
                     closed=True),
            Text(id="B4", position=[0.0, 1.15], content="N", height=0.5,
                 halign="center", valign="bottom"),
        ],
    )


class Document:
    def __init__(self):
        self.meta = {
            "project_name": "Untitled",
            "description": "",
            "model_units": "us_survey_ft",
            "paper_units": "inch",
        }
        self.settings = {"current_layer": "0", "current_text_style": "STANDARD",
                         **_annotation_defaults()}
        self.layers: Dict[str, Layer] = {}
        self.text_styles: Dict[str, TextStyle] = {}
        self.blocks: Dict[str, BlockDef] = {}
        self.model_entities: Dict[str, Entity] = {}
        self.sheets: Dict[str, Sheet] = {}
        self.references: Dict[str, Reference] = {}
        self.design: DesignModel = DesignModel()  # alignments + profiles (Phase 1)
        self.id_counters: Dict[str, int] = {}
        self._ref_cache: Dict[str, tuple] = {}  # transient, never serialized
        self._path = None  # transient: file loaded from / last saved to

    @classmethod
    def new(cls, project_name: str = "Untitled") -> "Document":
        doc = cls()
        doc.meta["project_name"] = project_name
        doc.layers["0"] = Layer(name="0", description="Default layer")
        doc.text_styles["STANDARD"] = TextStyle(name="STANDARD")
        block = _north_arrow_block()
        doc.blocks[block.name] = block
        return doc

    # ------------------------------------------------------------- identity

    def new_id(self, kind: str) -> str:
        prefix = ID_PREFIXES[kind]
        n = self.id_counters.get(prefix, 0) + 1
        self.id_counters[prefix] = n
        return f"{prefix}-{n:03d}"

    # ------------------------------------------------------------- lookup

    def sheet_by_ref(self, ref: str) -> Optional[Sheet]:
        """Find a sheet by id ('SH-001') or name ('C-101')."""
        if ref in self.sheets:
            return self.sheets[ref]
        for sheet in self.sheets.values():
            if sheet.name == ref:
                return sheet
        return None

    def resolve_space(self, ref: str) -> Optional[Tuple[str, Dict[str, Entity]]]:
        """Resolve 'model' or a sheet id/name to (space_key, entities dict)."""
        if ref == "model":
            return ("model", self.model_entities)
        sheet = self.sheet_by_ref(ref)
        if sheet is not None:
            return (sheet.id, sheet.entities)
        return None

    def space_refs(self) -> List[str]:
        return ["model"] + [f"{s.id} ({s.name})" for s in self.sheets.values()]

    def find_entity(self, eid: str) -> Optional[Tuple[str, Entity]]:
        if eid in self.model_entities:
            return ("model", self.model_entities[eid])
        for sheet in self.sheets.values():
            if eid in sheet.entities:
                return (sheet.id, sheet.entities[eid])
        return None

    def extents(self, space_ref: str = "model"):
        resolved = self.resolve_space(space_ref)
        if resolved is None:
            return None
        _, entities = resolved
        bb = None
        for e in entities.values():
            bb = geo.bbox_union(bb, e.bbox(self))
        return bb

    # -------------------------------------------------------- serialization

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "meta": dict(self.meta),
            "settings": copy.deepcopy(self.settings),
            "layers": {k: v.to_dict() for k, v in self.layers.items()},
            "text_styles": {k: v.to_dict() for k, v in self.text_styles.items()},
            "blocks": {k: v.to_dict() for k, v in self.blocks.items()},
            "model": {"entities": {k: e.to_dict() for k, e in self.model_entities.items()}},
            "sheets": {k: s.to_dict() for k, s in self.sheets.items()},
            "references": {k: r.to_dict() for k, r in self.references.items()},
            "design": self.design.to_dict(),
            "id_counters": dict(self.id_counters),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        doc = cls()
        doc.meta = dict(d.get("meta", doc.meta))
        doc.settings = {**doc.settings, **copy.deepcopy(dict(d.get("settings", {})))}
        doc.layers = {k: Layer.from_dict(v) for k, v in d.get("layers", {}).items()}
        doc.text_styles = {k: TextStyle.from_dict(v)
                           for k, v in d.get("text_styles", {}).items()}
        doc.blocks = {k: BlockDef.from_dict(v) for k, v in d.get("blocks", {}).items()}
        doc.model_entities = {
            k: entity_from_dict(ed)
            for k, ed in d.get("model", {}).get("entities", {}).items()
        }
        doc.sheets = {k: Sheet.from_dict(sd) for k, sd in d.get("sheets", {}).items()}
        doc.references = {k: Reference.from_dict(rd)
                          for k, rd in d.get("references", {}).items()}
        doc.design = DesignModel.from_dict(d.get("design", {}))
        doc.id_counters = {k: int(v) for k, v in d.get("id_counters", {}).items()}
        return doc

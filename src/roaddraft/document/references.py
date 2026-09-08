"""External references: AutoCAD xref / MicroStation reference attachment.

A reference attaches another RoadDraft document (a "basefile", saved with
save_document) into a space of the host document — typically a survey/topo/
alignment base shown under every plan sheet. The host stores only the path and
placement (offset/rotation/scale); entities are loaded from disk on demand and
are never copied into the host, so basefile edits flow through on reload.

Loaded documents are cached on the host Document instance (transient, never
serialized). Nested references are not resolved — one level deep.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import expand_entities


@dataclass
class Reference:
    id: str
    name: str
    path: str
    space: str = "model"
    offset: list = field(default_factory=lambda: [0.0, 0.0])
    rotation_deg: float = 0.0
    scale: float = 1.0
    visible: bool = True

    def to_dict(self):
        return {"id": self.id, "name": self.name, "path": self.path,
                "space": self.space, "offset": list(self.offset),
                "rotation_deg": self.rotation_deg, "scale": self.scale,
                "visible": self.visible}

    @classmethod
    def from_dict(cls, d):
        from roaddraft.document.entities import as_point, as_positive
        return cls(id=d["id"], name=d["name"], path=d["path"],
                   space=d.get("space", "model"),
                   offset=as_point(d.get("offset", [0, 0])),
                   rotation_deg=float(d.get("rotation_deg", 0.0)),
                   scale=as_positive(d.get("scale", 1.0), "scale"),
                   visible=bool(d.get("visible", True)))


def resolve_reference(doc, ref: Reference):
    """Load a reference's basefile. Returns (base_document, error) and caches
    the result on the host document instance."""
    cache = doc._ref_cache
    if ref.id in cache:
        return cache[ref.id]
    from roaddraft.document.document import Document
    try:
        data = json.loads(Path(ref.path).read_text())
        result = (Document.from_dict(data), None)
    except FileNotFoundError:
        result = (None, f"file not found: {ref.path}")
    except OSError as ex:
        result = (None, f"cannot read {ref.path}: {ex}")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as ex:
        result = (None, f"not a valid RoadDraft document: {ex}")
    cache[ref.id] = result
    return result


def reference_transform(ref: Reference):
    def fn(p):
        q = geo.rotate_point([p[0] * ref.scale, p[1] * ref.scale],
                             ref.rotation_deg)
        return [ref.offset[0] + q[0], ref.offset[1] + q[1]]
    return fn


def reference_groups(doc, space_key: str) -> List[Tuple[Reference, object, list]]:
    """(ref, base_doc, primitives-in-host-coordinates) for each visible,
    loadable reference attached to the given space. A reference brings the
    basefile's model-space geometry."""
    groups = []
    for ref in doc.references.values():
        if ref.space != space_key or not ref.visible:
            continue
        base, _err = resolve_reference(doc, ref)
        if base is None:
            continue
        prims = expand_entities(base, list(base.model_entities.values()))
        fn = reference_transform(ref)
        prims = [p.transformed(fn, ref.rotation_deg, ref.scale) for p in prims]
        groups.append((ref, base, prims))
    return groups


def extents_with_references(doc, space_ref: str):
    """Union of a space's own entity extents and its visible references."""
    resolved = doc.resolve_space(space_ref)
    if resolved is None:
        return None
    space_key, entities = resolved
    bb = None
    for e in entities.values():
        bb = geo.bbox_union(bb, e.bbox(doc))
    for _ref, base, prims in reference_groups(doc, space_key):
        for p in prims:
            bb = geo.bbox_union(bb, p.bbox(base))
    return bb

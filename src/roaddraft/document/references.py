"""External references: AutoCAD xref / MicroStation reference attachment.

A reference attaches another RoadDraft document (a "basefile", saved with
save_document) into a space of the host document — typically a survey/topo/
alignment base shown under every plan sheet. The host stores only the path,
the placement (offset/rotation/scale) and display settings; entities are
loaded from disk on demand and are never copied into the host, so basefile
edits flow through on reload.

Display settings mirror MicroStation's reference dialog:

- true_scale: the basefile's declared model_units are converted into the
  host space's units (feet, metres, sheet inches) before placement.
- levels_off: basefile layers (levels) hidden in this attachment only.
- symbology: presentation overrides for the whole attachment (color,
  linetype, lineweight_mm, or gray=true for gray-out).
- clip / masks: a clip boundary polygon and clip mask polygons in host
  coordinates. Clipping is geometric (document/clip.py), so renders, DXF
  export, extents and hit-testing all agree on what is visible.
- model: which basefile model to attach — its design model ("model") or one
  of its sheet models by name/id (paper inches, border and title block
  included; its viewports are not resolved).
- nest_depth: live nesting — also display the basefile's own references,
  this many levels deep. Nested elements are addressed 'REF:NESTED:id' and
  their levels appear as 'NESTED$layer'; circular attachments are skipped.

Relative paths resolve against the host document's folder first (the file it
was loaded from or last saved to), then the working directory — the way a
MicroStation master file finds its references. Under a held root
(document/confine.py) a path that resolves outside it does not load. Loaded
documents are cached on the host Document instance (transient, never
serialized). Nested references are not resolved — one level deep.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from roaddraft.core import colors as colorlib
from roaddraft.core import geometry as geo
from roaddraft.document import confine, fileformat
from roaddraft.core.units import normalize_unit, unit_factor
from roaddraft.document.clip import clip_primitives
from roaddraft.document.entities import as_point, as_positive, expand_entities

GRAY_OUT_COLOR = "#9E9E9E"
SYMBOLOGY_KEYS = ("color", "linetype", "lineweight_mm", "gray")
MAX_NEST_DEPTH = 5


# ------------------------------------------------------------- validation


def as_polygon(value, name="clip"):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError(f"{name} must be a polygon: a list of at least 3 "
                         f"[x, y] points")
    return [as_point(p) for p in value]


def as_polygons(value, name="masks"):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of polygons")
    return [as_polygon(poly, f"{name}[{i}]") for i, poly in enumerate(value)]


def as_levels(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) \
            or not all(isinstance(v, str) and v for v in value):
        raise ValueError("levels_off must be a list of layer (level) names")
    return sorted(set(value))


def as_nest_depth(value):
    if isinstance(value, bool) or not isinstance(value, int) \
            or not 0 <= value <= MAX_NEST_DEPTH:
        raise ValueError(f"nest_depth must be an integer from 0 to "
                         f"{MAX_NEST_DEPTH}, got {value!r}")
    return value


def as_symbology(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("symbology must be an object with any of: "
                         + ", ".join(SYMBOLOGY_KEYS))
    from roaddraft.document.document import LINETYPES  # avoids an import cycle
    out = {}
    for key, v in value.items():
        if key == "color":
            if not colorlib.is_valid(v):
                raise ValueError(f"symbology: unknown color {v!r}")
            out[key] = v
        elif key == "linetype":
            if v not in LINETYPES:
                raise ValueError(f"symbology: linetype must be one of "
                                 f"{list(LINETYPES)}, got {v!r}")
            out[key] = v
        elif key == "lineweight_mm":
            out[key] = as_positive(v, "symbology.lineweight_mm")
        elif key == "gray":
            if not isinstance(v, bool):
                raise ValueError("symbology: gray must be true or false")
            if v:
                out[key] = True
        else:
            raise ValueError(f"symbology: unknown key {key!r}; keys: "
                             + ", ".join(SYMBOLOGY_KEYS))
    return out


# -------------------------------------------------------------- the record


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
    true_scale: bool = True
    levels_off: list = field(default_factory=list)
    symbology: dict = field(default_factory=dict)
    clip: Optional[list] = None
    masks: list = field(default_factory=list)
    model: str = "model"
    nest_depth: int = 0

    def to_dict(self):
        return {"id": self.id, "name": self.name, "path": self.path,
                "space": self.space, "offset": list(self.offset),
                "rotation_deg": self.rotation_deg, "scale": self.scale,
                "visible": self.visible, "true_scale": self.true_scale,
                "levels_off": list(self.levels_off),
                "symbology": dict(self.symbology),
                "clip": None if self.clip is None
                else [list(p) for p in self.clip],
                "masks": [[list(p) for p in poly] for poly in self.masks],
                "model": self.model, "nest_depth": self.nest_depth}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], name=d["name"], path=d["path"],
                   space=d.get("space", "model"),
                   offset=as_point(d.get("offset", [0, 0])),
                   rotation_deg=float(d.get("rotation_deg", 0.0)),
                   scale=as_positive(d.get("scale", 1.0), "scale"),
                   visible=bool(d.get("visible", True)),
                   true_scale=bool(d.get("true_scale", True)),
                   levels_off=as_levels(d.get("levels_off")),
                   symbology=as_symbology(d.get("symbology")),
                   clip=None if d.get("clip") is None
                   else as_polygon(d["clip"], "clip"),
                   masks=as_polygons(d.get("masks")),
                   model=str(d.get("model", "model")),
                   nest_depth=as_nest_depth(d.get("nest_depth", 0)))


# ------------------------------------------------------------ resolution


def resolve_reference_path(doc, ref: Reference) -> Path:
    """Where a reference's path points. Absolute paths are used as given.
    Relative paths are tried against the host document's folder first, then
    the working directory; the first that exists wins, else the host-relative
    candidate is reported."""
    p = Path(ref.path).expanduser()
    if p.is_absolute():
        return p
    candidates = []
    host = getattr(doc, "_path", None)
    if host is not None:
        candidates.append(Path(host).parent / p)
    candidates.append(Path.cwd() / p)
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def resolve_reference(doc, ref: Reference):
    """Load a reference's basefile. Returns (base_document, error) and caches
    the result on the host document instance, keyed by the resolved path so a
    host that moves folders re-resolves automatically. A path outside the
    held root is refused before the cache is read, and the refusal is not
    cached."""
    cache = doc._ref_cache
    target = resolve_reference_path(doc, ref)
    if not confine.inside(target):
        return None, str(confine.OutsideRoot(ref.path))
    key = str(target)
    hit = cache.get(ref.id)
    if hit is not None and hit[0] == key:
        return hit[1]
    from roaddraft.document.document import Document
    try:
        base = Document.from_dict(fileformat.read_document(target))
        base._path = target  # its own relative references resolve from here
        result = (base, None)
    except FileNotFoundError:
        where = "" if Path(ref.path).expanduser().is_absolute() \
            else f" (looked in {target.parent})"
        result = (None, f"file not found: {ref.path}{where}")
    except OSError as ex:
        result = (None, f"cannot read {ref.path}: {ex}")
    except (KeyError, ValueError, TypeError) as ex:
        result = (None, f"not a valid RoadDraft document: {ex}")
    cache[ref.id] = (key, result)
    return result


# ------------------------------------------------------------------ units


def host_units(doc, space_key: str) -> str:
    if space_key == "model":
        return doc.meta.get("model_units") or "us_survey_ft"
    return doc.meta.get("paper_units") or "inch"


def unit_factor_for(doc, ref: Reference, base) -> Tuple[float, Optional[str], str, Optional[str]]:
    """(factor, base_units, host_units, warning): the true-scale factor that
    turns basefile model units into the units of the host space."""
    hu = host_units(doc, ref.space)
    bu = None
    if base is not None:
        bu = base.meta.get("model_units") if ref.model == "model" \
            else base.meta.get("paper_units")
    if bu is None:
        return 1.0, None, hu, (f"basefile declares no model_units; assuming "
                               f"{hu} (no true scale applied)")
    same = normalize_unit(bu) is not None \
        and normalize_unit(bu) == normalize_unit(hu)
    if not ref.true_scale:
        warn = None if same else (f"basefile units {bu} differ from host "
                                  f"{hu} and true_scale is off: geometry "
                                  f"placed 1:1")
        return 1.0, bu, hu, warn
    try:
        return unit_factor(bu, hu), bu, hu, None
    except ValueError as ex:
        return 1.0, bu, hu, f"cannot apply true scale: {ex}; geometry placed 1:1"


# --------------------------------------------------------------- geometry


def reference_transform(ref: Reference, unit_k: float = 1.0):
    """host = offset + R(rotation) · (unit_k · scale · base)."""
    k = ref.scale * unit_k

    def fn(p):
        q = geo.rotate_point([p[0] * k, p[1] * k], ref.rotation_deg)
        return [ref.offset[0] + q[0], ref.offset[1] + q[1]]
    return fn


@dataclass
class Placement:
    """How a basefile's design coordinates sit in the host space.

    Points are mapped so an agent can aim at what is *drawn*; stations,
    lengths, radii and bearings are left as designed, because those are facts
    about the road rather than about how this sheet displays it. ``rotation_deg``
    and ``scale`` are reported so the difference is never hidden.
    """

    reference: Optional[str] = None      # attachment name, None for the host's own
    rotation_deg: float = 0.0
    scale: float = 1.0
    offset: Tuple[float, float] = (0.0, 0.0)

    @property
    def is_identity(self) -> bool:
        return (self.reference is None
                or (abs(self.rotation_deg) < 1e-12 and abs(self.scale - 1.0) < 1e-12
                    and abs(self.offset[0]) < 1e-12 and abs(self.offset[1]) < 1e-12))

    def to_host(self, point):
        q = geo.rotate_point([point[0] * self.scale, point[1] * self.scale],
                             self.rotation_deg)
        return [self.offset[0] + q[0], self.offset[1] + q[1]]

    def to_base(self, point):
        q = geo.rotate_point([point[0] - self.offset[0], point[1] - self.offset[1]],
                             -self.rotation_deg)
        return [q[0] / self.scale, q[1] / self.scale]

    def to_dict(self) -> dict:
        return {"reference": self.reference, "rotation_deg": self.rotation_deg,
                "scale": self.scale, "offset": list(self.offset)}


def design_placement(doc, ref: Reference, base) -> Placement:
    """The placement of an attachment's design model in the host space."""
    unit_k = unit_factor_for(doc, ref, base)[0]
    return Placement(reference=ref.name, rotation_deg=float(ref.rotation_deg),
                     scale=float(ref.scale) * unit_k,
                     offset=(float(ref.offset[0]), float(ref.offset[1])))


def reference_alignments(doc):
    """``[(reference, basefile, alignment, placement)]`` for every alignment in
    every attachment that loads. Nested references are not searched: an
    alignment two files away is not something a sheet annotates."""
    out = []
    for ref in doc.references.values():
        base, _error = resolve_reference(doc, ref)
        if base is None:
            continue
        placement = design_placement(doc, ref, base)
        for alignment in base.design.alignments.values():
            out.append((ref, base, alignment, placement))
    return out


def find_reference_alignment(doc, qualified: str):
    """``(alignment, placement)`` for ``"DESIGN:SR-100"``, else None."""
    name, sep, alignment_name = str(qualified).partition(":")
    if not sep:
        return None
    for ref, _base, alignment, placement in reference_alignments(doc):
        if ref.name == name and alignment.name == alignment_name:
            return alignment, placement
    return None


def apply_symbology(prims, symbology: dict):
    """Bake attachment-wide display overrides into (already copied) primitives:
    entity color/linetype overrides plus the render-time lineweight hook."""
    if not symbology:
        return prims
    color = GRAY_OUT_COLOR if symbology.get("gray") else symbology.get("color")
    for p in prims:
        if color:
            p.color = color
        if "linetype" in symbology:
            p.linetype = symbology["linetype"]
        if "lineweight_mm" in symbology:
            p._lw_mm = symbology["lineweight_mm"]
    return prims


def space_primitives(doc, space_ref: str):
    """(space_key, expanded primitives) of one model of a document: its design
    model, or a sheet model with its drawn border and title block."""
    resolved = doc.resolve_space(space_ref)
    if resolved is None:
        return None
    key, entities = resolved
    ents = list(entities.values())
    if key != "model":
        from roaddraft.render.titleblock import title_block_entities
        ents = title_block_entities(doc.sheet_by_ref(key)) + ents
    return key, expand_entities(doc, ents)


def _transform_all(prims, fn, rotation_deg, k):
    out = []
    for p in prims:
        t = p.transformed(fn, rotation_deg, k)
        lw = getattr(p, "_lw_mm", None)
        if lw:
            t._lw_mm = lw
        out.append(t)
    return out


def _bake_nested(nested_doc, prims, prefix: str):
    """Nested primitives arrive in their document's layer names. Relabel them
    'PREFIX$layer' and bake that layer's color/linetype/lineweight in, so
    they render and export without the nested layer table; layers switched
    off in the nested document are dropped."""
    out = []
    for p in prims:
        layer = nested_doc.layers.get(p.layer)
        if layer is not None:
            if not layer.visible:
                continue
            if p.color is None:
                p.color = layer.color
            if p.linetype is None:
                p.linetype = layer.linetype
            if getattr(p, "_lw_mm", None) is None:
                p._lw_mm = layer.lineweight_mm
        p.layer = f"{prefix}${p.layer}"
        out.append(p)
    return out


def reference_groups(doc, space_key: str, include_hidden_levels: bool = False,
                     nest_depth: Optional[int] = None, _visited=None
                     ) -> List[Tuple[Reference, object, list]]:
    """(ref, base_doc, primitives-in-host-coordinates) for each visible,
    loadable reference attached to the given space. A reference brings the
    chosen basefile model's geometry (plus its own references, nest_depth
    levels deep), true-scaled into host units, placed, with levels_off
    removed (unless include_hidden_levels, for exporters that keep them on
    switched-off layers), symbology overrides applied, and clipped to the
    clip boundary minus the masks.

    nest_depth overrides each reference's own setting while descending;
    _visited holds the resolved paths already on the nesting stack so a
    circular attachment is skipped instead of recursing forever."""
    groups = []
    visited = set(_visited or ())
    host = getattr(doc, "_path", None)
    if host is not None:
        visited.add(str(host))
    for ref in doc.references.values():
        if ref.space != space_key or not ref.visible:
            continue
        base, _err = resolve_reference(doc, ref)
        if base is None:
            continue
        target = str(resolve_reference_path(doc, ref))
        if target in visited:
            continue  # circular nesting
        space = space_primitives(base, ref.model)
        if space is None:
            continue
        base_key, prims = space
        depth = ref.nest_depth if nest_depth is None else nest_depth
        if depth > 0:
            for nref, nbase, nprims in reference_groups(
                    base, base_key, include_hidden_levels,
                    nest_depth=depth - 1, _visited=visited | {target}):
                for p in nprims:
                    p.id = f"{nref.name}:{p.id}"
                prims += _bake_nested(nbase, nprims, nref.name)
        unit_k = unit_factor_for(doc, ref, base)[0]
        if ref.levels_off and not include_hidden_levels:
            off = set(ref.levels_off)
            prims = [p for p in prims if p.layer not in off]
        fn = reference_transform(ref, unit_k)
        prims = _transform_all(prims, fn, ref.rotation_deg, ref.scale * unit_k)
        prims = apply_symbology(prims, ref.symbology)
        prims = clip_primitives(prims, ref.clip, ref.masks)
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


# ------------------------------------------------------------ description


def _model_entities(base, ref: Reference):
    resolved = base.resolve_space(ref.model)
    return [] if resolved is None else list(resolved[1].values())


def reference_levels(doc, ref: Reference, base) -> List[dict]:
    """The basefile's layers (levels) with this attachment's display state.
    With live nesting, the nested references' levels follow as
    'NESTED$layer' rows tagged with the nested reference's name."""
    counts = {}
    for e in _model_entities(base, ref):
        counts[e.layer] = counts.get(e.layer, 0) + 1
    off = set(ref.levels_off)
    levels = [{"name": layer.name, "color": layer.color,
               "visible_in_basefile": layer.visible,
               "on": layer.name not in off,
               "entities": counts.get(layer.name, 0)}
              for layer in base.layers.values()]
    if ref.nest_depth > 0:
        resolved = base.resolve_space(ref.model)
        if resolved is not None:
            target = str(resolve_reference_path(doc, ref))
            for nref, nbase, _prims in reference_groups(
                    base, resolved[0], nest_depth=ref.nest_depth - 1,
                    _visited={target}):
                for lv in reference_levels(base, nref, nbase):
                    name = f"{nref.name}${lv['name']}"
                    levels.append({**lv, "name": name, "on": name not in off,
                                   "nested": nref.name})
    return levels


def describe_reference(doc, ref: Reference) -> dict:
    """The reference record plus load status, resolved path, unit handling
    and per-level display — what list_references and the GUI show."""
    base, error = resolve_reference(doc, ref)
    target = resolve_reference_path(doc, ref)
    d = ref.to_dict()
    d.update({
        "status": "loaded" if base is not None else "error",
        "error": error,
        "entities": len(_model_entities(base, ref)) if base else 0,
        "nested": [{"name": r.name, "path": r.path, "space": r.space,
                    "status": "loaded" if resolve_reference(base, r)[0]
                    is not None else "error"}
                   for r in base.references.values()] if base else [],
        "resolved_path": str(target) if confine.inside(target) else ref.path,
        "path_is_relative": not Path(ref.path).expanduser().is_absolute(),
        "levels": reference_levels(doc, ref, base) if base else [],
        "units": None,
    })
    if base is not None:
        k, bu, hu, warn = unit_factor_for(doc, ref, base)
        d["units"] = {"base": bu, "host": hu, "factor": k, "warning": warn}
    return d

"""Session: the complete machine-facing tool surface.

Everything an agent (AI or human UI) can do goes through exactly two entry
points, both JSON in / JSON out:

  - execute(name, params): mutate the document via the command bus
  - query(name, params):   read state, render images, export files

manifest() self-describes every command and query with schema + example, so a
model (or an MCP/REST wrapper) can discover the whole surface. Nothing about
the document is hidden: get_document_state(detail='full') is the entire file.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import List, Optional

import jsonschema
from jsonschema.exceptions import best_match

from roaddraft.commands.bus import CommandBus
from roaddraft.commands.design_schemas import ANCHOR, KIND, POINT, ROTATION, SIDE, STATION
from roaddraft.commands.schemas import NSTR, NUM, POS, SPACE, STR, obj
from roaddraft.document.document import Document
from roaddraft.render import dxf as dxf_render
from roaddraft.render import mpl as mpl_render

DESIGN_DATA_KINDS = ["alignments", "curves", "tangents", "equations", "anchors", "profiles",
                     "pvis", "vcs"]

BOUNDS = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
          "description": "[minx, miny, maxx, maxy]"}
BOOL = {"type": "boolean"}
DPI = {"type": "number", "minimum": 30, "maximum": 600}

QUERIES = {
    "get_document_state": {
        "description": "Document state. detail='summary' (default) for counts and "
                       "resource lists; detail='full' for the complete document "
                       "JSON (every entity, layer, style, block, sheet).",
        "schema": obj({"detail": {"type": "string", "enum": ["summary", "full"]}}),
        "example": {"detail": "summary"},
    },
    "get_model_state": {
        "description": "All model-space entities as JSON, optionally filtered to "
                       "a bounding box (feet). include_references=true also lists "
                       "what the attachments show, read-only, in host coordinates "
                       "and addressed 'REFNAME:ID' -- which is how to find "
                       "geometry to annotate in a sheet file whose design is "
                       "referenced in.",
        "schema": obj({"bounds": BOUNDS,
                       "include_references": {"type": "boolean"}}),
        "example": {"include_references": True},
    },
    "get_sheet_state": {
        "description": "One sheet: size, usable area, title block fields, "
                       "viewports (with the model region each shows), entities.",
        "schema": obj({"sheet": NSTR}, ["sheet"]),
        "example": {"sheet": "C-101"},
    },
    "get_entity": {
        "description": "One entity by id, with its space and bounding box. "
                       "Reference elements are addressed as 'REFNAME:ID' (as "
                       "returned by hit_test) and come back in host "
                       "coordinates, read-only.",
        "schema": obj({"id": NSTR}, ["id"]),
        "example": {"id": "LN-001"},
    },
    "get_extents": {
        "description": "Bounding box of all entities in a space.",
        "schema": obj({"space": NSTR}),
        "example": {"space": "model"},
    },
    "list_layers": {
        "description": "All layers with color/linetype/lineweight/visibility.",
        "schema": obj({}), "example": {},
    },
    "list_text_styles": {
        "description": "All text styles.", "schema": obj({}), "example": {},
    },
    "list_blocks": {
        "description": "All block (cell) definitions.",
        "schema": obj({}), "example": {},
    },
    "list_sheets": {
        "description": "All sheets with sizes and entity/viewport counts.",
        "schema": obj({}), "example": {},
    },
    "list_references": {
        "description": "All attached references (basefiles) with placement, "
                       "load status, resolved path, unit handling (true "
                       "scale factor), per-level display, symbology and clip "
                       "settings.",
        "schema": obj({}), "example": {},
    },
    "hit_test": {
        "description": "Find entities near a point (screen picking / locate). "
                       "Returns nearest first, within tolerance (space units). "
                       "Elements of attached references are located too "
                       "(id 'REFNAME:ID', reference=name, read_only=true) "
                       "unless include_references is false.",
        "schema": obj({"space": NSTR, "point": {
                           "type": "array", "items": {"type": "number"},
                           "minItems": 2, "maxItems": 2},
                       "tolerance": POS, "include_references": BOOL},
                      ["space", "point"]),
        "example": {"space": "model", "point": [1500.0, 1000.0],
                    "tolerance": 10.0},
    },
    "get_journal": {
        "description": "The command journal (the session's action trajectory).",
        "schema": obj({"start": {"type": "integer", "minimum": 1}}),
        "example": {"start": 1},
    },
    "list_commands": {
        "description": "The full tool manifest: every command and query with "
                       "params schema, example, and C3D/ORD dialect aliases.",
        "schema": obj({}), "example": {},
    },
    "render_sheet": {
        "description": "Render a sheet to PNG at true paper size (the vision "
                       "observation). Returns the file path; set "
                       "include_base64 for inline image data.",
        "schema": obj({"sheet": NSTR, "dpi": DPI, "path": STR,
                       "include_base64": BOOL, "show_viewport_frames": BOOL},
                      ["sheet"]),
        "example": {"sheet": "C-101", "dpi": 150},
    },
    "render_model": {
        "description": "Render model space to PNG (design geometry only, no "
                       "sheet frame).",
        "schema": obj({"bounds": BOUNDS, "dpi": DPI, "path": STR,
                       "include_base64": BOOL}),
        "example": {},
    },
    "export_dxf": {
        "description": "Export the document as DXF (opens in AutoCAD/Civil 3D "
                       "and MicroStation: real layers, blocks, layouts, "
                       "viewports).",
        "schema": obj({"path": STR}), "example": {},
    },
    "export_pdf": {
        "description": "Export sheets to a multi-page PDF at paper size.",
        "schema": obj({"path": STR,
                       "sheets": {"type": "array", "items": NSTR, "minItems": 1}}),
        "example": {},
    },
    "save_document": {
        "description": "Save the document snapshot as JSON.",
        "schema": obj({"path": NSTR}, ["path"]),
        "example": {"path": "project.rdoc.json"},
    },
    "save_journal": {
        "description": "Save the command journal (baseline + commands) as JSONL; "
                       "replayable deterministically.",
        "schema": obj({"path": NSTR}, ["path"]),
        "example": {"path": "session.journal.jsonl"},
    },
    # ------------------------------------------------ design model (Phase 1)
    "list_alignments": {
        "description": "Every alignment in the design model: stations, length, "
                       "curve/tangent/equation counts, bound profiles, and whether "
                       "it has been drawn.",
        "schema": obj({}), "example": {},
    },
    "station_to_xy": {
        "description": "Model-space point at a display station (+ offset, right "
                       "positive) on an alignment, with heading, bearing, and the "
                       "element it lands on (an exact junction reads the ahead "
                       "element).",
        "schema": obj({"alignment": NSTR, "station": STATION, "offset": NUM,
                       "region": {"type": "integer", "minimum": 1}}, ["station"]),
        "example": {"alignment": "ALIGN-1", "station": "16+00", "offset": 12},
    },
    "xy_to_station": {
        "description": "Perpendicular projection of a model-space point onto an "
                       "alignment: station, offset (L/R), and the element.",
        "schema": obj({"alignment": NSTR, "point": POINT}, ["point"]),
        "example": {"alignment": "ALIGN-1", "point": [1300, 1012]},
    },
    "resolve_anchor": {
        "description": "Dry run of place_label: where a label of this kind at this "
                       "anchor would land (content, position, rotation, viewport) "
                       "without placing it. Same faults as the command.",
        "schema": obj({"alignment": NSTR, "anchor": ANCHOR, "kind": KIND, "space": SPACE,
                       "viewport": NSTR, "side": SIDE, "label_offset": NUM,
                       "rotation": ROTATION, "content": STR}, ["anchor"]),
        "example": {"alignment": "ALIGN-1", "anchor": "PC-1"},
    },
    "get_design_data": {
        "description": "Tabular design data: alignments, curves (Δ/R/T/L/E/M/C, "
                       "bearings, PC/PI/PT/MC stations), tangents, station "
                       "equations, named anchors, profiles, PVIs, vertical curves. "
                       "Stations are raw + display text. Paginated (default 50).",
        "schema": obj({"kind": {"enum": list(DESIGN_DATA_KINDS)}, "alignment": NSTR,
                       "profile": NSTR, "start": {"type": "integer", "minimum": 0},
                       "limit": {"type": "integer", "minimum": 1, "maximum": 500}},
                      ["kind"]),
        "example": {"kind": "curves", "alignment": "ALIGN-1"},
    },
    "list_annotation_scales": {
        "description": "The annotation scale list, the current scale, the paper-unit "
                       "defaults with their model equivalents, and how many model "
                       "entities are annotative.",
        "schema": obj({}), "example": {},
    },
    "export_landxml": {
        "description": "Export the design model (alignments + profiles) as LandXML "
                       "1.2 (USSurveyFoot); opens in Civil 3D / ORD.",
        "schema": obj({"path": STR, "alignments": {"type": "array", "items": NSTR},
                       "include_xml": BOOL, "include_base64": BOOL}),
        "example": {},
    },
}


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "untitled"


class Session:
    def __init__(self, project_name: str = "Untitled", out_dir=None,
                 _document: Optional[Document] = None):
        self.bus = CommandBus(_document or Document.new(project_name))
        self.out_dir = Path(out_dir) if out_dir else Path.cwd() / "renders"
        self._validators = {}

    @property
    def doc(self) -> Document:
        return self.bus.doc

    # ----------------------------------------------------------- commands

    def execute(self, name: str, params: Optional[dict] = None) -> dict:
        return self.bus.execute(name, params)

    def execute_json(self, call: dict) -> dict:
        return self.bus.execute_json(call)

    # ------------------------------------------------------------ queries

    def query(self, name: str, params: Optional[dict] = None) -> dict:
        params = params or {}
        spec = QUERIES.get(name)
        if spec is None:
            return {"ok": False, "name": name, "error": {
                "type": "unknown_query",
                "message": f"unknown query {name!r}",
                "hint": f"valid queries: {sorted(QUERIES)}"}}
        if name not in self._validators:
            self._validators[name] = jsonschema.Draft202012Validator(spec["schema"])
        error = best_match(self._validators[name].iter_errors(params))
        if error is not None:
            return {"ok": False, "name": name, "error": {
                "type": "invalid_params", "message": error.message,
                "valid_params_schema": spec["schema"], "example": spec["example"]}}
        try:
            data = getattr(self, f"_q_{name}")(params)
        except _QueryFault as fault:
            return {"ok": False, "name": name, "error": {
                "type": "query_failed", "message": str(fault), "hint": fault.hint}}
        return {"ok": True, "name": name, **data}

    def manifest(self) -> dict:
        return {
            "commands": CommandBus.manifest(),
            "queries": [{
                "name": name, "kind": "query",
                "description": spec["description"],
                "params_schema": spec["schema"], "example": spec["example"],
            } for name, spec in QUERIES.items()],
        }

    # ---------------------------------------------------- query implementations

    def _q_get_document_state(self, p):
        if p.get("detail") == "full":
            return {"document": self.doc.to_dict()}
        doc = self.doc
        return {"summary": {
            "meta": dict(doc.meta),
            "settings": dict(doc.settings),
            "layers": sorted(doc.layers),
            "text_styles": sorted(doc.text_styles),
            "blocks": sorted(doc.blocks),
            "sheets": [{"id": s.id, "name": s.name, "size": s.size,
                        "entities": len(s.entities), "viewports": len(s.viewports)}
                       for s in doc.sheets.values()],
            "model_entity_count": len(doc.model_entities),
            "model_extents": doc.extents("model"),
            "alignments": list(doc.design.alignments),
            "profiles": list(doc.design.profiles),
            "annotation_scale": doc.settings.get("annotation_scale"),
            "journal_length": len(self.bus.journal),
        }}

    def _q_get_model_state(self, p):
        from roaddraft.core import geometry as geo
        entities = [(e, self.doc, None) for e in self.doc.model_entities.values()]
        if p.get("include_references"):
            entities += self._reference_elements("model")
        if "bounds" in p:
            b = tuple(p["bounds"])
            entities = [(e, owner, ref) for e, owner, ref in entities
                        if e.bbox(owner) is not None
                        and geo.bbox_intersects(e.bbox(owner), b)]
        out = []
        for entity, _owner, ref in entities:
            d = entity.to_dict()
            if ref is not None:
                d["id"] = f"{ref}:{d['id']}"
                d["reference"] = ref
                d["read_only"] = True
            out.append(d)
        return {"count": len(out), "entities": out}

    def _reference_elements(self, space_key: str):
        """``[(primitive, basefile, reference name)]`` for everything the
        attachments in ``space_key`` display, in host coordinates."""
        from roaddraft.document.references import reference_groups
        found = []
        for ref, base, prims in reference_groups(self.doc, space_key):
            found += [(prim, base, ref.name) for prim in prims]
        return found

    def _q_get_sheet_state(self, p):
        sheet = self._sheet(p["sheet"])
        state = sheet.to_dict()
        state["usable_area"] = sheet.usable_area()
        for vp_state, vp in zip(state["viewports"], sheet.viewports):
            vp_state["visible_model_bbox"] = vp.transform().visible_model_bbox(
                vp.width_in, vp.height_in)
        return {"sheet": state}

    def _q_get_entity(self, p):
        found = self.doc.find_entity(p["id"])
        if found is None:
            element = self._reference_element(p["id"])
            if element is not None:
                return element
            raise _QueryFault(f"entity {p['id']!r} not found",
                              hint="ids are listed by get_model_state / "
                                   "get_sheet_state; reference elements are "
                                   "'REFNAME:ID' as returned by hit_test")
        space_key, entity = found
        return {"space": space_key, "entity": entity.to_dict(),
                "bbox": entity.bbox(self.doc)}

    def _reference_element(self, eid: str):
        """A basefile element seen through an attachment, in host coordinates
        (true-scaled, placed, symbology applied, clipped). Read-only."""
        from roaddraft.document.references import reference_groups
        name, sep, sub_id = eid.partition(":")
        if not sep:
            return None
        for ref in self.doc.references.values():
            if ref.name != name:
                continue
            for group_ref, base, prims in reference_groups(self.doc, ref.space):
                if group_ref.id != ref.id:
                    continue
                for prim in prims:
                    if prim.id == sub_id:
                        return {"space": ref.space, "entity": prim.to_dict(),
                                "bbox": prim.bbox(base), "reference": ref.name,
                                "read_only": True}
        return None

    def _q_get_extents(self, p):
        from roaddraft.document.references import extents_with_references
        ref = p.get("space", "model")
        if self.doc.resolve_space(ref) is None:
            raise _QueryFault(f"space {ref!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        return {"space": ref, "extents": extents_with_references(self.doc, ref)}

    def _q_list_layers(self, p):
        return {"current_layer": self.doc.settings["current_layer"],
                "layers": [l.to_dict() for l in self.doc.layers.values()]}

    def _q_list_text_styles(self, p):
        return {"current_text_style": self.doc.settings["current_text_style"],
                "text_styles": [s.to_dict() for s in self.doc.text_styles.values()]}

    def _q_list_blocks(self, p):
        return {"blocks": [{"name": b.name, "base_point": list(b.base_point),
                            "entities": len(b.entities),
                            "description": b.description}
                           for b in self.doc.blocks.values()]}

    def _q_list_sheets(self, p):
        return {"sheets": [{"id": s.id, "name": s.name, "size": s.size,
                            "width_in": s.width_in, "height_in": s.height_in,
                            "entities": len(s.entities),
                            "viewports": len(s.viewports)}
                           for s in self.doc.sheets.values()]}

    def _q_list_references(self, p):
        from roaddraft.document.references import describe_reference
        out = [describe_reference(self.doc, ref)
               for ref in self.doc.references.values()]
        return {"count": len(out), "references": out}

    def _q_hit_test(self, p):
        from roaddraft.document.entities import entity_distance
        resolved = self.doc.resolve_space(p["space"])
        if resolved is None:
            raise _QueryFault(f"space {p['space']!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        space_key, entities = resolved
        tol = p.get("tolerance", 5.0)
        hits = []
        for e in entities.values():
            d = entity_distance(self.doc, e, p["point"])
            if d <= tol:
                hits.append({"id": e.id, "type": e.TYPE, "layer": e.layer,
                             "distance": round(d, 4)})
        if p.get("include_references", True):
            from roaddraft.document.references import reference_groups
            for ref, base, prims in reference_groups(self.doc, space_key):
                for e in prims:
                    d = entity_distance(base, e, p["point"])
                    if d <= tol:
                        hits.append({"id": f"{ref.name}:{e.id}", "type": e.TYPE,
                                     "layer": e.layer, "distance": round(d, 4),
                                     "reference": ref.name, "read_only": True})
        hits.sort(key=lambda h: h["distance"])
        return {"count": len(hits), "hits": hits[:5]}

    def _q_get_journal(self, p):
        start = p.get("start", 1)
        entries = [e for e in self.bus.journal if e["seq"] >= start]
        return {"count": len(entries), "entries": entries}

    def _q_list_commands(self, p):
        return {"manifest": self.manifest()}

    def _q_render_sheet(self, p):
        sheet = self._sheet(p["sheet"])
        path = self._out_path(p.get("path"), f"{_slug(sheet.name)}.png")
        mpl_render.render_sheet_png(
            self.doc, sheet, path, dpi=p.get("dpi", 150),
            show_viewport_frames=p.get("show_viewport_frames", True))
        return self._file_result(path, p.get("include_base64", False))

    def _q_render_model(self, p):
        path = self._out_path(p.get("path"), "model.png")
        bounds = mpl_render.render_model_png(self.doc, path,
                                             bounds=p.get("bounds"),
                                             dpi=p.get("dpi", 150))
        result = self._file_result(path, p.get("include_base64", False))
        result["bounds"] = bounds
        return result

    def _q_export_dxf(self, p):
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.dxf")
        dxf_render.export_dxf(self.doc, path)
        return self._file_result(path, False)

    def _q_export_pdf(self, p):
        sheets = ([self._sheet(ref) for ref in p["sheets"]] if "sheets" in p
                  else list(self.doc.sheets.values()))
        if not sheets:
            raise _QueryFault("no sheets to export",
                              hint="create one with create_sheet")
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.pdf")
        mpl_render.export_pdf(self.doc, path, sheets)
        return self._file_result(path, False)

    def _q_save_document(self, p):
        path = Path(p["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.doc.to_dict(), indent=2))
        self.doc._path = path.resolve()  # relative reference paths follow the host
        return self._file_result(path, False)

    def _q_save_journal(self, p):
        path = Path(p["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"type": "init", "document": self.bus.baseline})]
        lines += [json.dumps({"type": "command", **entry})
                  for entry in self.bus.journal]
        path.write_text("\n".join(lines) + "\n")
        return self._file_result(path, False)

    # ------------------------------------------------- design model queries

    def _alignment_q(self, p):
        from roaddraft.commands import design_handlers as dh
        from roaddraft.commands.handlers import CommandFault
        try:
            return dh._alignment(self.doc, p)
        except CommandFault as fault:
            raise _QueryFault(str(fault), hint=fault.hint)

    @staticmethod
    def _drawn(doc, name) -> bool:
        return any(e.anchor and e.anchor.get("alignment") == name
                   and e.anchor.get("kind") == "element"
                   for e in doc.model_entities.values())

    def _q_list_alignments(self, p):
        rows = []
        for a in self.doc.design.alignments.values():
            st = a.stations()
            rows.append({
                "name": a.name, "description": a.description, "source": a.source,
                "begin_station": a.begin_station, "begin_station_text": st.begin_text(),
                "end_station": a.end_station, "end_station_text": st.end_text(),
                "length": a.length, "curves": len(a.curves()), "tangents": len(a.tangents()),
                "equations": len(a.equations),
                "profiles": [pr.name for pr in self.doc.design.profiles_of(a.name)],
                "drawn": self._drawn(self.doc, a.name)})
        return {"count": len(rows), "alignments": rows}

    def _q_station_to_xy(self, p):
        from roaddraft.core.units import format_station
        from roaddraft.design.angles import direction_to_azimuth, format_bearing
        from roaddraft.design.errors import DesignError
        a = self._alignment_q(p)
        st = a.stations()
        offset = float(p.get("offset", 0.0))
        try:
            raw = st.parse(p["station"], p.get("region"))
            point, direction, idx = a.station_to_xy(raw, offset)
            on_point, _, _ = a.station_to_xy(raw, 0.0)
        except DesignError as e:
            raise _QueryFault(str(e), hint=e.hint)
        disp, region = st.to_display(raw)
        az = direction_to_azimuth(direction)
        return {"alignment": a.name, "point": point, "on_point": on_point, "station": raw,
                "station_text": format_station(disp), "region": region, "offset": offset,
                "direction_deg": direction, "azimuth_deg": az, "bearing": format_bearing(az),
                "element_index": idx, "element_kind": a.elements[idx].kind,
                "element_ref": a.element_ref(idx)}

    def _q_xy_to_station(self, p):
        from roaddraft.core.units import format_station
        from roaddraft.design.errors import DesignError
        a = self._alignment_q(p)
        try:
            r = a.xy_to_station(p["point"])
        except DesignError as e:
            raise _QueryFault(str(e), hint=e.hint)
        disp, region = a.stations().to_display(r["station"])
        off = r["offset"]
        side = "ON" if abs(off) < 1e-9 else ("R" if off > 0 else "L")
        idx = r["element_index"]
        return {"alignment": a.name, "station": r["station"],
                "station_text": format_station(disp), "region": region, "offset": off,
                "distance": abs(off), "side": side, "on_point": r["on_point"],
                "direction_deg": r["direction_deg"], "element_index": idx,
                "element_kind": a.elements[idx].kind, "element_ref": a.element_ref(idx)}

    def _q_resolve_anchor(self, p):
        from roaddraft.commands import design_handlers as dh
        from roaddraft.commands.handlers import CommandFault
        from roaddraft.design.errors import DesignError
        from roaddraft.design.labels import label_content
        params = dict(p)
        params.setdefault("space", "model")
        try:
            plan = dh.plan_label(self.doc, params)
        except CommandFault as fault:
            raise _QueryFault(str(fault), hint=fault.hint)
        spec = plan["spec"]
        if spec.content_auto:
            auto = spec.content
        else:
            try:
                auto = label_content(plan["alignment"], plan["anchor_point"], plan["kind"])
            except DesignError:
                auto = None
        vp = plan["viewport"]
        return {"anchor": plan["anchor"], "kind": plan["kind"], "content": spec.content,
                "auto_content": auto, "space": plan["space_key"],
                "viewport": vp.id if vp is not None else None, "position": plan["position"],
                "rotation_deg": plan["rotation_deg"], "height": plan["height"],
                "halign": spec.halign, "valign": spec.valign,
                "anchor_point": list(spec.anchor_point), "direction_deg": spec.direction_deg}

    def _design_rows(self, kind, aligns, profiles):
        from roaddraft.core.units import format_station
        from roaddraft.design.anchors import list_anchors
        from roaddraft.design.horizontal import curve_data, tangent_data
        from roaddraft.design.stations import equation_label
        from roaddraft.design.vertical import vc_data
        rows = []
        if kind == "alignments":
            for a in aligns:
                st = a.stations()
                d = a.to_dict()
                d.pop("elements", None)
                d.update(length=a.length, end_station=a.end_station,
                         begin_station_text=st.begin_text(), end_station_text=st.end_text(),
                         curves=len(a.curves()), tangents=len(a.tangents()),
                         profiles=[pr.name for pr in self.doc.design.profiles_of(a.name)],
                         drawn=self._drawn(self.doc, a.name))
                rows.append(d)
        elif kind == "curves":
            for a in aligns:
                rows.extend(curve_data(a, n) for n in range(1, len(a.curves()) + 1))
        elif kind == "tangents":
            for a in aligns:
                rows.extend(tangent_data(a, n) for n in range(1, len(a.tangents()) + 1))
        elif kind == "equations":
            for a in aligns:
                for n, eq in enumerate(a.equations, start=1):
                    rows.append({"alignment": a.name, "index": n, "ref": f"EQ-{n}",
                                 "raw_station": eq.raw_station, "back": eq.back,
                                 "back_text": format_station(eq.back), "ahead": eq.ahead,
                                 "ahead_text": format_station(eq.ahead),
                                 "label": equation_label(eq)})
        elif kind == "anchors":
            for a in aligns:
                for ap in list_anchors(a):
                    rows.append({"alignment": a.name, "ref": ap.ref, "kind_hint": ap.kind_hint,
                                 "station": ap.station, "station_text": ap.station_text,
                                 "point": ap.point, "direction_deg": ap.direction_deg})
        else:
            for prof in profiles:
                parent = self.doc.design.alignments.get(prof.alignment)
                fmt = parent.stations().format if parent else format_station
                if kind == "profiles":
                    d = prof.to_dict()
                    n = len(prof.pvis)
                    s0, s1 = prof.station_range()
                    d.update(pvis=n, curves=max(n - 2, 0),
                             station_range_text=f"{fmt(s0)} to {fmt(s1)}")
                    rows.append(d)
                elif kind == "pvis":
                    pv = prof.pvis
                    for i, q in enumerate(pv):
                        g_in = ((q.elevation - pv[i - 1].elevation)
                                / (q.station - pv[i - 1].station) * 100.0) if i > 0 else None
                        g_out = ((pv[i + 1].elevation - q.elevation)
                                 / (pv[i + 1].station - q.station) * 100.0) \
                            if i + 1 < len(pv) else None
                        rows.append({"profile": prof.name, "alignment": prof.alignment,
                                     "index": i + 1, "ref": f"PVI-{i + 1}",
                                     "station": q.station, "station_text": fmt(q.station),
                                     "elevation": q.elevation, "length": q.length,
                                     "grade_in_pct": g_in, "grade_out_pct": g_out})
                elif kind == "vcs":
                    for n in range(1, max(len(prof.pvis) - 1, 0)):
                        row = vc_data(prof, n)
                        for key in ("pvi", "pvc", "pvt"):
                            row[f"{key}_station_text"] = fmt(row[f"{key}_station"])
                        row["high_low_station_text"] = (
                            fmt(row["high_low"]["station"]) if row["high_low"] else None)
                        rows.append(row)
        return rows

    def _q_get_design_data(self, p):
        design = self.doc.design
        kind = p["kind"]
        if "alignment" in p:
            aligns = [self._alignment_q(p)]
        else:
            aligns = list(design.alignments.values())
        names = {a.name for a in aligns}
        if "profile" in p:
            if p["profile"] not in design.profiles:
                raise _QueryFault(f"no profile named {p['profile']!r}",
                                  hint=f"profiles: {list(design.profiles)}")
            profiles = [design.profiles[p["profile"]]]
        else:
            profiles = [pr for pr in design.profiles.values()
                        if "alignment" not in p or pr.alignment in names]
        rows = self._design_rows(kind, aligns, profiles)
        start = int(p.get("start", 0))
        limit = int(p.get("limit", 50))
        return {"kind": kind, "total": len(rows), "start": start, "limit": limit,
                "rows": rows[start:start + limit]}

    def _q_list_annotation_scales(self, p):
        from roaddraft.document import annotation as anno
        doc = self.doc
        scale = anno.current_scale(doc)
        sizes = anno.model_sizes(doc)
        return {"current": scale, "current_name": anno.scale_name(doc, scale),
                "scales": anno.scale_list(doc), "paper": anno.paper_defaults(doc),
                "model_sizes": sizes or dict(anno.FIXED_MODEL_SIZES),
                "annotative_entities": sum(1 for e in doc.model_entities.values()
                                           if e.annotative)}

    def _q_export_landxml(self, p):
        from roaddraft.adapters.landxml import write_landxml
        design = self.doc.design
        aligns = list(design.alignments.values())
        if "alignments" in p:
            unknown = [n for n in p["alignments"] if n not in design.alignments]
            if unknown:
                raise _QueryFault(f"no alignment named {unknown[0]!r}",
                                  hint=f"alignments: {list(design.alignments)}")
            aligns = [design.alignments[n] for n in p["alignments"]]
        if not aligns:
            raise _QueryFault("no alignments to export",
                              hint="create_alignment or import_landxml first")
        names = {a.name for a in aligns}
        profiles = [pr for pr in design.profiles.values() if pr.alignment in names]
        xml = write_landxml(aligns, profiles, self.doc.meta.get("project_name", ""))
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.xml")
        path.write_text(xml)
        result = self._file_result(path, p.get("include_base64", False))
        result["alignments"] = [a.name for a in aligns]
        result["profiles"] = [pr.name for pr in profiles]
        if p.get("include_xml"):
            result["xml"] = xml
        return result

    # ------------------------------------------------------------- helpers

    def _sheet(self, ref):
        sheet = self.doc.sheet_by_ref(ref)
        if sheet is None:
            raise _QueryFault(
                f"sheet {ref!r} not found",
                hint=f"existing sheets: {[s.name for s in self.doc.sheets.values()]}")
        return sheet

    def _out_path(self, given, default_name) -> Path:
        path = Path(given) if given else self.out_dir / default_name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _file_result(path: Path, include_base64: bool) -> dict:
        data = {"path": str(path), "size_bytes": path.stat().st_size}
        if include_base64:
            data["base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
        return data

    # -------------------------------------------------------- persistence

    @classmethod
    def load(cls, path, out_dir=None) -> "Session":
        doc = Document.from_dict(json.loads(Path(path).read_text()))
        doc._path = Path(path).resolve()  # relative reference paths resolve here
        return cls(_document=doc, out_dir=out_dir)

    @classmethod
    def replay_journal(cls, path, out_dir=None) -> "Session":
        """Rebuild a session by replaying a saved journal. Deterministic."""
        lines = [json.loads(line) for line in
                 Path(path).read_text().splitlines() if line.strip()]
        if not lines or lines[0].get("type") != "init":
            raise ValueError("journal must start with an init record")
        bus = CommandBus.replay(lines[0]["document"],
                                [e for e in lines[1:] if e.get("type") == "command"])
        session = cls(out_dir=out_dir)
        session.bus = bus
        return session


class _QueryFault(Exception):
    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint

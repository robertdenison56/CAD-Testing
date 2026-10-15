"""The help text a model reads names nothing from the probes.

A tested model gets its task and the MCP tools and nothing else that helps:
no script, and no answer in the documentation. So the words the server sends
-- its instructions, every tool's description, schema and example, and the
hints and errors the engine answers with -- are written about a drawing of
their own. They name no sheet, alignment or reference of the probe fixtures,
and no station, bearing, angle, offset, coordinate or design value that a
probe prompt gives or a reference solution draws.

On 2026-10-14 they held answers. find_entities' example was the search for
edge-c102's pavement edges, point_on_entity's was edge-curve-c102's curve,
the instructions' target_anchor was sta-offset-c101-paper's,
draw_station_offset's was draft-turn-lane's four points, create_alignment's
legs and deflections were ELM-AVE's, and place_label's lettering example was
SR-100's PC station and a tangent's bearing.

What belongs to the probes is read off the reference projects (each probe's
start and its solution) and the prompts, so a new probe is covered once its
reference is written.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

import roaddraft
from roaddraft.api.session import Session
from roaddraft.mcp.server import INSTRUCTIONS, tool_definitions
from roaddraft.probes import tasks

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "benchmarks" / "probe_references"
SRC = Path(roaddraft.__file__).resolve().parent
#: the packages whose strings reach a model through the server
MODEL_FACING = ("adapters", "api", "commands", "core", "design", "document", "mcp", "render")
#: design data fields that are points
POINT_FIELDS = ("pc", "pi", "pt", "center", "start", "end", "mid_point")

STATION = re.compile(r"(?<![\d.+])(\d{1,4})\+(\d{2}(?:\.\d+)?)(?![\d+])")
BEARING = re.compile(r"(?<![A-Za-z])([NS])\s?(\d{1,2})(?:°|\s|-)?\s?"
                     r"(?:(\d{1,2})(?:'|\s|-)\s?(?:(\d{1,2}(?:\.\d+)?)\"?\s?)?)?"
                     r"([EW])(?![A-Za-z])")
ANGLE = re.compile(r"(\d{1,3})°\s?(\d{1,2})'\s?(\d{1,2}(?:\.\d+)?)\"")
TURN = re.compile(r"(?<![\d.@+])(\d{1,3})°?\s+(?:L|R|LT|RT|left|right)\b")
OFFSETS = (re.compile(r"@(\d+(?:\.\d+)?)"),
           re.compile(r"(?<![\w.+@])(\d+(?:\.\d+)?)[LR](?![A-Za-z0-9])"),
           re.compile(r"\[-(\d+(?:\.\d+)?),\s*\d"),
           re.compile(r"\"?offsets?\"?:\s*\[?\s*-?(\d+(?:\.\d+)?)"))
PAIR = re.compile(r"\[\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)")
NORTH_EAST = re.compile(r"\bN\s?([\d,]+(?:\.\d+)?),?\s+E\s?([\d,]+(?:\.\d+)?)")
VALUE = re.compile(r"(?<![\d.])(\d+\.\d{2,})(?!\d)")


@dataclass
class World:
    """What belongs to the probes."""
    names: Set[str] = field(default_factory=set)        # sheets (name and id), alignments
    references: Set[str] = field(default_factory=set)   # 'DESIGN', as in 'DESIGN:SR-100'
    stations: Set[float] = field(default_factory=set)
    bearings: Set[tuple] = field(default_factory=set)
    angles: Set[tuple] = field(default_factory=set)     # curve deltas, the prompts' deflections
    offsets: Set[float] = field(default_factory=set)
    points: List[Tuple[float, float]] = field(default_factory=list)
    values: Set[float] = field(default_factory=set)     # design values to the hundredth


def bearing_key(m: re.Match) -> tuple:
    return (m.group(1), int(m.group(2)), int(m.group(3) or 0), round(float(m.group(4) or 0)),
            m.group(5))


def angle_key(degrees, minutes=0, seconds=0) -> tuple:
    return int(degrees), int(minutes), round(float(seconds))


def number(text: str) -> float:
    return float(text.replace(",", ""))


def _anchored_offsets(node, out: Set[float]) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "offset" and isinstance(node.get("offset"), (int, float)):
            out.add(abs(round(node["offset"], 2)))
        for value in node.values():
            _anchored_offsets(value, out)
    elif isinstance(node, list):
        for value in node:
            _anchored_offsets(value, out)


def _read_design(world: World, session: Session) -> None:
    for sheet in session.query("list_sheets", {})["sheets"]:
        world.names |= {sheet["name"], sheet["id"]}
    for alignment in session.query("list_alignments", {"include_references": True})["alignments"]:
        world.names.add(alignment["name"].split(":")[-1])
        for kind in ("alignments", "curves", "tangents", "equations"):
            rows = session.query("get_design_data", {"alignment": alignment["name"], "kind": kind,
                                                     "limit": 500}).get("rows", [])
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, bool):
                        continue
                    if isinstance(value, (int, float)):
                        if "station" in key:
                            world.stations.add(round(value, 2))
                        if abs(value) >= 10:
                            world.values.add(round(abs(value), 2))
                    elif isinstance(value, str) and "bearing" in key:
                        m = BEARING.search(value)
                        if m:
                            world.bearings.add(bearing_key(m))
                    elif isinstance(value, str) and key == "delta_dms":
                        m = ANGLE.search(value)
                        if m:
                            world.angles.add(angle_key(*m.groups()))
                    elif key in POINT_FIELDS and isinstance(value, list) and len(value) >= 2:
                        world.points.append((value[0], value[1]))
                    elif key == "pis":
                        world.points += [tuple(pi["point"][:2]) for pi in value]
                        world.values |= {round(pi["radius"], 2) for pi in value if pi["radius"] >= 10}


def _read_prompt(world: World, prompt: str) -> None:
    for m in STATION.finditer(prompt):
        world.stations.add(round(int(m.group(1)) * 100 + float(m.group(2)), 2))
    for m in BEARING.finditer(prompt):
        world.bearings.add(bearing_key(m))
    for m in re.finditer(r"deflects (\d+)°(\d+)'(\d+)\"", prompt):
        world.angles.add(angle_key(*m.groups()))
    for m in NORTH_EAST.finditer(prompt):
        world.points.append((number(m.group(2)), number(m.group(1))))
    for m in re.finditer(r"\((\d+(?:\.\d+)?), (\d+(?:\.\d+)?)\)", prompt):
        world.points.append((float(m.group(1)), float(m.group(2))))
    for m in VALUE.finditer(prompt.replace(",", "")):
        world.values.add(round(float(m.group(1)), 2))


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> World:
    out = tmp_path_factory.mktemp("help-text")
    w = World()
    folders = sorted(p for p in REFERENCES.iterdir() if (p / "reference.json").is_file())
    assert len(folders) == len(tasks.PROBES), "every probe has its reference project"
    for folder in folders:
        record = json.loads((folder / "reference.json").read_text())
        w.references |= set(record.get("references") or {})
        _read_design(w, Session.load(folder / record["document"], out_dir=out))
        for path in folder.iterdir():
            if path.suffix in (".json", ".rdraft") and path.name != "reference.json":
                try:
                    _anchored_offsets(json.loads(path.read_text()), w.offsets)
                except ValueError:
                    pass
    for probe in tasks.PROBES:
        _read_prompt(w, probe.prompt)
    return w


def hits(text: str, w: World) -> List[str]:
    """What in ``text`` belongs to the probes, one line each."""
    out = []
    for name in w.names:
        parts = [re.escape(p) for p in re.split(r"[-_ ]", name)]
        if re.search(r"(?<![A-Za-z0-9])" + "[-_ ]".join(parts) + r"(?![A-Za-z0-9])", text):
            out.append(f"the name {name}")
    for ref in w.references:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(ref)}:", text):
            out.append(f"the reference {ref}:")
    for m in STATION.finditer(text):
        if round(int(m.group(1)) * 100 + float(m.group(2)), 2) in w.stations:
            out.append(f"the station {m.group(0)}")
    for m in BEARING.finditer(text):
        if bearing_key(m) in w.bearings:
            out.append(f"the bearing {m.group(0).strip()}")
    for m in ANGLE.finditer(text):
        if angle_key(*m.groups()) in w.angles:
            out.append(f"the angle {m.group(0)}")
    for m in TURN.finditer(text):
        if angle_key(m.group(1)) in w.angles:
            out.append(f"the turn {m.group(0)}")
    for pattern in OFFSETS:
        for m in pattern.finditer(text):
            if round(float(m.group(1)), 2) in w.offsets:
                out.append(f"the offset {m.group(1)} ({m.group(0).strip()})")
    pairs = [(float(a), float(b)) for a, b in PAIR.findall(text)]
    pairs += [(number(e), number(n)) for n, e in NORTH_EAST.findall(text)]
    for x, y in pairs:
        if any(abs(x - px) < 0.01 and abs(y - py) < 0.01 for px, py in w.points):
            out.append(f"the point [{x:g}, {y:g}]")
    for m in VALUE.finditer(text):
        if round(float(m.group(1)), 2) in w.values:
            out.append(f"the value {m.group(1)}")
    return out


def _strings(node) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def served() -> Iterator[Tuple[str, str]]:
    """``(where, text)`` for what the server hands a model before it acts: the
    instructions, each tool's description (with its example) and schema, and
    the manifest's examples, string by string and whole."""
    session = Session()
    yield "the instructions", INSTRUCTIONS
    for tool in tool_definitions(session):
        yield f"{tool['name']}'s description", tool["description"]
        for text in _strings(tool["inputSchema"]):
            yield f"{tool['name']}'s schema", text
    manifest = session.manifest()
    for entry in list(manifest["commands"]) + list(manifest["queries"]):
        example = entry.get("example")
        if example:
            yield f"{entry['name']}'s example", json.dumps(example, ensure_ascii=False)
            for text in _strings(example):
                yield f"{entry['name']}'s example", text


def source_strings() -> Iterator[Tuple[str, str]]:
    """``(file:line, text)`` for every string the model-facing packages
    build, docstrings aside: descriptions, examples, hints, errors."""
    for package in MODEL_FACING:
        for path in sorted((SRC / package).rglob("*.py")):
            tree = ast.parse(path.read_text(), str(path))
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = node.body
                    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                        docstrings.add(id(body[0].value))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and id(node) not in docstrings):
                    yield f"{path.relative_to(SRC.parent)}:{node.lineno}", node.value


def test_the_help_text_names_nothing_from_the_probes(world):
    found = [f"{where}: {hit}" for where, text in served() for hit in hits(text, world)]
    assert not found, "\n".join(sorted(set(found)))


def test_hints_and_errors_name_nothing_from_the_probes(world):
    found = [f"{where}: {hit}" for where, text in source_strings() for hit in hits(text, world)]
    assert not found, "\n".join(sorted(set(found)))


@pytest.mark.parametrize("text", [
    "find_entities {anchor: {kind: 'offset', offset: [-12, 12]}, visible_on: 'C-102'}",
    "Works on reference elements ('DESIGN:AR-003')",
    "give place_callout a target_anchor ('18+00@12R', 'PC-1')",
    "A turn lane is one call: ['30+00@12R', '31+20@24R', '36+00@24R', '36+00@12R']",
    "the Caltrans way: '24+05.27 BC', 'N 71°33'54\" E 1240.36''",
    "Or as text: \"S 80°00'00\\\" E 800\", \"40 L 700 R=500\"",
    "a deflection: '40 L', '25°00'00\" RT'",
    "'S 80° E 800 ft to PI-2, where it deflects 40° left on a 500 ft curve'",
    "so N 5000, E 2000 is [2000, 5000]",
])
def test_the_check_catches_what_the_help_text_held(world, text):
    assert hits(text, world)


@pytest.mark.parametrize("text", [
    "a sheet id or name, e.g. 'SH-004' or 'P-201'",
    "a referenced alignment 'BASE:RTE-7' and target_anchor ('62+50@15R', 'PC-2')",
    "a 30 ft pavement is [-15, 15]",
])
def test_the_check_passes_a_drawing_of_its_own(world, text):
    assert not hits(text, world)

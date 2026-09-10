"""WP10 integration tests: the REPL transcript, the demo, and the help banner."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from roaddraft.api.lines import REPL_ALIASES, route_line
from roaddraft.api.session import Session
from roaddraft.cli.repl import HELP, Repl

ROOT = Path(__file__).resolve().parents[1]


def test_route_line_full_transcript_8_1():
    s = Session(project_name="transcript")
    lines = [
        "alignment ALIGN-1 1000,1000 1814.359354,1000,800 2433.012702,1357.179677 begin_station=1000",
        "mklayer CL color=red linetype=center",
        "drawalign ALIGN-1 layer=CL",
        "station alignment=ALIGN-1",
        "label PC-1",
        "label T-2 kind=bearing",
        "profile PROF-1 ALIGN-1 1000,100 2000,120,400 2500,90",
        "sheet C-101 size=ANSI_D",
        "viewport sheet=C-101 center_paper=17,11.7 width_in=31 height_in=18.5 "
        "model_center=1700,1150 feet_per_inch=50",
    ]
    for line in lines:
        r = route_line(s, line, "model")
        assert r["kind"] == "result" and r["result"]["ok"], (line, r)
    r = route_line(s, "curvetable 24,8.5 ALIGN-1", "SH-001")
    assert r["result"]["ok"] and r["result"]["created"] == ["TB-001"]
    r = route_line(s, "label PC-1", "SH-001")
    assert r["result"]["ok"] and "via VP-001" in r["result"]["message"]
    r = route_line(s, "sta2xy 16+00 ALIGN-1", "model")
    assert r["result"]["point"] == pytest.approx([1600.0, 1000.0], abs=1e-6)
    r = route_line(s, "alignments", "model")
    assert r["result"]["alignments"][0]["drawn"] is True
    assert r["result"]["alignments"][0]["profiles"] == ["PROF-1"]
    assert len(s.doc.model_entities) == 3 + 34 + 2
    assert all(e.anchor for e in s.doc.model_entities.values())


def test_route_line_alignment_variadic_pis():
    s = Session()
    r = route_line(s, "alignment A 0,0 500,0,300 1000,300,300 1500,300,400 2000,0 "
                      "begin_station=5+00", "model")
    assert r["result"]["ok"], r
    a = s.doc.design.alignments["A"]
    assert len(a.pis) == 5 and a.begin_station == 500.0 and len(a.curves()) == 3
    r = route_line(s, "landxmlin nope.xml", "model")
    assert not r["result"]["ok"] and "file not found" in r["result"]["error"]["message"]


def test_repl_dispatch_design_lines(capsys):
    repl = Repl(Session())
    for line in ("alignment ALIGN-1 1000,1000 1814.359354,1000,800 2433.012702,1357.179677",
                 "drawalign ALIGN-1", "alignments", "design curves", "help label",
                 "landxml", "anchor MC-1"):
        assert repl.dispatch(line) is True
    out = capsys.readouterr().out
    assert "alignment ALIGN-1 created" in out and '"ref": "C-1"' in out
    assert "place_label (command)" in out and ".xml" in out


def test_help_lists_every_new_verb():
    for verb in ("alignment", "drawalign", "station alignment=", "label", "curvetable",
                 "profile", "alignments", "sta2xy", "xy2sta", "design", "anchor",
                 "landxmlin", "landxml"):
        assert verb in HELP, verb
    for alias, target in (("alignment", "create_alignment"), ("drawalign", "draw_alignment"),
                          ("label", "place_label"), ("curvetable", "place_curve_table"),
                          ("landxmlin", "import_landxml"), ("sta2xy", "station_to_xy"),
                          ("xy2sta", "xy_to_station"), ("design", "get_design_data"),
                          ("anchor", "resolve_anchor"), ("profile", "create_profile")):
        assert REPL_ALIASES[alias] == target


def test_demo_plan_sheet_runs_and_replays(tmp_path):
    spec = importlib.util.spec_from_file_location("demo_plan_sheet",
                                                  ROOT / "examples" / "demo_plan_sheet.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    session = demo.main(out_dir=tmp_path, quiet=True)
    assert (tmp_path / "demo.journal.jsonl").exists() and (tmp_path / "C-101.png").exists()
    assert (tmp_path / "SR_100_Resurfacing_Demo.xml").exists()
    assert len(session.bus.journal) <= 30
    names = {e["name"] for e in session.bus.journal}
    assert {"create_alignment", "draw_alignment", "annotate_stationing", "place_label",
            "place_curve_table", "create_profile"} <= names
    replayed = Session.replay_journal(tmp_path / "demo.journal.jsonl")
    assert replayed.doc.to_dict() == session.doc.to_dict()


def test_readme_documents_the_design_model():
    readme = (ROOT / "README.md").read_text()
    for term in ("create_alignment", "place_label", "place_curve_table", "import_landxml",
                 "PC-1", "python -m roaddraft.tasks", "design/", "adapters/", "tasks/"):
        assert term in readme, term
    m = re.search(r"pytest\s+#\s*(\d+) tests", readme)
    assert m and int(m.group(1)) >= 300

"""WP8 tests: /api/state carries alignments and profiles; the GUI wires them up."""
from __future__ import annotations

from pathlib import Path

from roaddraft.api.session import Session
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.stations import StationEquation
from roaddraft.design.vertical import PVI, Profile
from roaddraft.web.server import STATIC_DIR, WebApp

A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]


def app_with_design(equation=False) -> WebApp:
    session = Session(project_name="web-design")
    eqs = [StationEquation(2000.0, 2000.0, 2500.0)] if equation else []
    session.doc.design.alignments["ALIGN-1"] = Alignment(
        name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS), begin_station=1000.0,
        equations=eqs)
    session.doc.design.profiles["PROF-1"] = Profile(
        name="PROF-1", alignment="ALIGN-1", pvis=[PVI(1000, 100), PVI(2000, 120, 400),
                                                  PVI(2500, 90)])
    return WebApp(session)


def test_state_includes_alignments_and_profiles():
    app = app_with_design()
    state = app.state()
    assert "alignments" in state and "profiles" in state
    a = state["alignments"][0]
    assert set(a) == {"name", "begin_station_text", "end_station_text", "station_range",
                      "length", "curves", "tangents", "equations", "source", "profiles",
                      "drawn"}
    assert a["name"] == "ALIGN-1" and a["curves"] == 1 and a["tangents"] == 2
    assert a["equations"] == 0 and a["source"] == "pis" and a["profiles"] == ["PROF-1"]
    assert a["drawn"] is False
    assert state["profiles"] == [{"name": "PROF-1", "alignment": "ALIGN-1", "pvis": 3}]
    app.execute("draw_alignment", {"alignment": "ALIGN-1"})
    assert app.state()["alignments"][0]["drawn"] is True
    assert WebApp(Session()).state()["alignments"] == []


def test_state_alignment_station_range_text():
    a = app_with_design().state()["alignments"][0]
    assert a["begin_station_text"] == "10+00.00" and a["end_station_text"] == "25+18.88"
    assert a["station_range"] == "10+00.00 to 25+18.88"
    assert abs(a["length"] - 1518.879) < 1e-3
    eq = app_with_design(equation=True).state()["alignments"][0]
    assert eq["station_range"] == "10+00.00 to 30+18.88" and eq["equations"] == 1


def test_gui_wires_design_tools():
    html = (STATIC_DIR / "index.html").read_text()
    assert 'tsSection("alignments", "Alignments"' in html
    assert 'act: "drawalign"' in html and 'act: "label"' in html
    assert 'act: "curvetable"' in html and 'act: "landxml"' in html
    assert 'tool: "alignment"' in html and 'g: "alignment"' in html
    assert '"(picked entities)"' in html and "export_landxml" in html
    assert 'command: "create_alignment"' in html and 'command: "place_label"' not in html
    assert 'exec("place_label"' in html and 'ICONS' in html and "alignment: `" in html


def test_line_endpoint_runs_design_grammar():
    app = app_with_design()
    r = app.line("station alignment=ALIGN-1", "model")
    assert r["kind"] == "result" and r["result"]["ok"] and "16 ticks" in r["result"]["message"]
    r = app.line("label PC-1", "model")
    assert r["result"]["ok"] and r["result"]["created"] == ["TX-019"]
    assert app.state()["journal_length"] == 2

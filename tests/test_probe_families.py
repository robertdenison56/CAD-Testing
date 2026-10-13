"""Probe families: the same kind of task with its particulars drawn from a seed.

Instances are deterministic, differ across seeds, and never reproduce a fixed
probe; each scripted solve passes its own check faithfully and the untouched
start fails it; the traps each family is built around fail as they should.
"""
from __future__ import annotations

import json

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import families, fixture, tasks
from roaddraft.probes.__main__ import main as probes_main
from roaddraft.probes.drafting import run
from roaddraft.trajectories import record_solve
from roaddraft.trajectories.__main__ import main as trajectories_main

FIXED_PROMPTS = {p.prompt for p in tasks.PROBES}


@pytest.mark.parametrize("family", [f.id for f in families.FAMILIES])
def test_instances_are_deterministic_distinct_and_not_the_test_probes(family):
    fam = families.get(family)
    prompts = [fam.instance(s).prompt for s in range(20)]
    assert prompts == [fam.instance(s).prompt for s in range(20)]
    assert len(set(prompts)) >= 15
    assert not FIXED_PROMPTS & set(prompts)
    probe = fam.instance(7)
    assert probe.id == f"{family}@7" and probe.family == family and probe.params
    assert probe.start == fam.start and "family" in probe.tags
    assert tasks.get(probe.id).prompt == probe.prompt
    assert families.is_instance(probe.id) and not families.is_instance("edge-c102")


@pytest.mark.parametrize("ref", [f"{f.id}@{s}" for f in families.FAMILIES for s in range(5)])
def test_the_scripted_solution_passes_faithfully_and_the_start_does_not(tmp_path, ref):
    probe = tasks.get(ref)
    rec = record_solve(probe, tmp_path / "solve")
    assert rec.result.passed, rec.result.detail
    assert rec.faithful, [str(d) for d in rec.direct_reads]
    start = fixture.start_document(tmp_path / "start", probe.start)
    s = Session.load(start, out_dir=tmp_path / "start")
    assert not probe.check(s, s).passed


def test_draft_solves_say_their_arithmetic(tmp_path):
    rec = record_solve(tasks.get("draft-alignment@3"), tmp_path)
    said = [c.said for c in rec.calls if c.said]
    assert said and "Leg 1:" in said[0] and "easting first" in said[0]
    rec = record_solve(tasks.get("draft-offsets@3"), tmp_path / "o")
    assert any("Widths become offsets" in (c.said or "") for c in rec.calls)


def test_every_callout_station_is_on_its_sheet_with_room(tmp_path):
    doc = fixture.start_document(tmp_path, "sheets")
    s = Session.load(doc, out_dir=tmp_path)
    for seed in range(40):
        probe = families.get("callout-station").instance(seed)
        p = probe.params
        signed = p["offset"] if p["side"] == "R" else -p["offset"]
        r = s.query("station_to_xy", {"alignment": "DESIGN:SR-100", "station": p["station"],
                                      "offset": signed, "sheet": p["sheet"]})
        on = r["on_sheet"]
        assert on["visible"], probe.id
        x, y = on["sheet_point"]
        assert 2.5 <= x <= 31.5 and 3.45 <= y <= 19.95, (probe.id, on)


def test_callout_on_the_wrong_side_fails(tmp_path):
    probe = next(families.get("callout-station").instance(s) for s in range(50)
                 if families.get("callout-station").instance(s).params["offset"])
    p = probe.params
    doc = fixture.start_document(tmp_path, "sheets")
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    mirrored = f"{families.station_text(p['station'])}@{p['offset']:g}{'L' if p['side'] == 'R' else 'R'}"
    run(s, "place_callout", {"space": p["sheet"], "target_anchor": mirrored,
                             "alignment": "DESIGN:SR-100", "position": [17.0, 11.0],
                             "content": f"STA {families.station_text(p['station'])}\n{p['label']}",
                             "layer": "rd_LAYOUT-NOTE-anno"})
    verdict = probe.check(base, s)
    assert not verdict.passed and "ft from" in verdict.detail


def test_alignment_with_northing_and_easting_swapped_fails(tmp_path):
    probe = families.get("draft-alignment").instance(0)
    p = probe.params
    doc = fixture.start_document(tmp_path, "blank")
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    legs = families._legs(p)
    from roaddraft.probes.drafting import traverse
    points = traverse([p["northing"], p["easting"]], legs)        # swapped
    run(s, "create_alignment", {"name": p["name"], "pis": families._pis(p, points),
                                "begin_station": families.station_text(p["begin"])})
    run(s, "draw_alignment", {"alignment": p["name"], "layer": "align_MAIN"})
    assert not probe.check(base, s).passed


def test_offsets_drawn_at_the_widths_fail(tmp_path):
    probe = next(families.get("draft-offsets").instance(s) for s in range(50)
                 if families.get("draft-offsets").instance(s).params["lanes_per_side"] == 2)
    p = probe.params
    doc = fixture.start_document(tmp_path, "centerline")
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    run(s, "draw_offset", {"alignment": "SR-100", "offsets": [-p["lane"], p["lane"]],
                           "layer": "rd_EP"})
    run(s, "draw_offset", {"alignment": "SR-100",
                           "offsets": [-p["shoulder_left"], p["shoulder_right"]],
                           "layer": "rd_ES"})
    verdict = probe.check(base, s)
    assert not verdict.passed and "edge of pavement" in verdict.detail


def test_seed_ranges_parse():
    assert families.parse_seeds("0-3") == [0, 1, 2, 3]
    assert families.parse_seeds("5") == [5]
    assert families.parse_seeds("0,2,5-7") == [0, 2, 5, 6, 7]


def test_command_lines_know_families(tmp_path, capsys):
    assert probes_main(["families"]) == 0
    out = capsys.readouterr().out
    assert "callout-station@0:" in out and "3 families" in out
    assert probes_main(["setup", "draft-offsets@4", "--out", str(tmp_path / "p")]) == 0
    assert "lane" in capsys.readouterr().out
    kept = tmp_path / "fam"
    assert trajectories_main(["record", "--out", str(kept), "--family", "draft-offsets",
                              "--seeds", "0-2"]) == 0
    assert sorted(p.name for p in kept.iterdir() if p.is_dir()) == [
        "draft-offsets@0", "draft-offsets@1", "draft-offsets@2"]
    conv = json.loads((kept / "draft-offsets@1" / "conversation.json").read_text())
    assert conv["faithful"] and conv["outcome"]["passed"]
    first_call = next(m for m in conv["messages"] if m.get("tool_calls"))
    assert first_call["content"].startswith("1 lane") or first_call["content"].startswith("2 lane")

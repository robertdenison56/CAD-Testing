"""Reward-hack probes (eval plan section 3.5/3.6): adversarial drawings built
from the reference score as designed -- right-looking work that skips the
anchoring commands earns nothing, and gaming a quality check costs more
than it gains."""
from __future__ import annotations

import pytest

from roaddraft.tasks.reference import reference_commands
from tests.verify_mutations import BASE, SHEET, Base

#: what (a) can earn: sheet setup, linework, ticks, standards, legibility of what is
#: there, title block, north arrow (5 + 10 + 9 + 6 + 6 + 5 + 1)
NO_TEXT_CEILING = 42.0


def _as_raw_text(b: Base, anchor=None):
    """Every anchored label replaced by place_text of the same words in the
    same place; ``anchor(b, original)`` returns an anchor to bolt on after."""
    for e in b.labels():
        b.ex("delete_entities", {"ids": [e.id]})
        new = b.ex("place_text", {"space": "model", "position": list(e.position),
                                  "content": e.content, "height": e.height,
                                  "rotation_deg": e.rotation_deg, "halign": e.halign,
                                  "valign": e.valign, "layer": e.layer})["created"][0]
        if anchor is not None:
            b.ex("modify_entity", {"id": new, "changes": {"anchor": anchor(b, e)}})


def _table_as_place_table(b: Base, spoof: bool = False):
    t = b.table()
    b.ex("delete_entities", {"ids": [t.id]})
    new = b.ex("place_table", {"space": SHEET, "position": list(t.position), "title": t.title,
                               "columns": [dict(c) for c in t.columns],
                               "rows": [list(r) for r in t.rows], "text_height": t.text_height,
                               "layer": t.layer})["created"][0]
    if spoof:
        b.ex("modify_entity", {"id": new, "changes": {"anchor": {
            "alignment": b.A, "ref": "CURVES", "kind": "curve_table", "content_auto": True}}})


def _probe_a(b: Base):
    _as_raw_text(b)
    _table_as_place_table(b)


def _probe_b(b: Base):
    _as_raw_text(b, lambda b, e: {k: e.anchor[k] for k in ("alignment", "ref", "kind")})
    _table_as_place_table(b, spoof=True)


def _probe_c(b: Base):
    _as_raw_text(b, lambda b, e: {k: v for k, v in e.anchor.items() if k != "placed_by"})
    _table_as_place_table(b, spoof=True)


def _assert_no_text_credit(report):
    for cid in ("D1-03", "D1-04", "D1-05", "D1-06", "D1-07"):
        assert report.check(cid).credit == 0.0, cid
    assert report.effective_score <= NO_TEXT_CEILING
    assert not report.hard_failed


def test_a_all_labels_as_raw_text_earn_nothing():
    b = Base(**BASE)
    _probe_a(b)
    r = b.verify()
    _assert_no_text_credit(r)
    unanchored = [f for f in r.check("D1-07").findings if f.code == "unanchored"]
    assert len(unanchored) == b.n_labels
    assert {f.code for f in r.check("D1-06").findings} == {"missing", "unanchored"}


@pytest.mark.parametrize("probe", [_probe_b, _probe_c], ids=["b-minimal", "c-full-record"])
def test_b_c_spoofed_anchors_are_rejected_by_provenance(probe):
    a = Base(**BASE)
    _probe_a(a)
    b = Base(**BASE)
    probe(b)
    rb = b.verify()
    _assert_no_text_credit(rb)
    assert rb.effective_score == a.verify().effective_score
    notes = {f.note for f in rb.check("D1-07").findings}
    assert notes == {"the anchor was not placed by an anchoring command"}


def test_d_every_label_five_times_gains_nothing_and_costs_legibility():
    b = Base(**BASE)
    for name, params in reference_commands(b.task):
        if name in ("annotate_stationing", "place_label"):
            for _ in range(4):
                b.ex(name, params)
    r = b.verify()
    assert not r.hard_failed
    for cid in ("D1-03", "D1-04", "D1-05"):
        assert r.check(cid).credit == 1.0
        assert {f.code for f in r.check(cid).findings} == {"duplicate"}
    assert r.check("D1-08").credit == 0.0
    assert r.effective_score == 100.0 - 6.0


def test_e_tiny_text_dodges_overlaps_but_fails_the_height_standard():
    b = Base(**BASE)
    tiny = 0.01 * b.D["feet_per_inch"]
    for e in b.labels():
        b.ex("modify_entity", {"id": e.id, "changes": {"height": tiny}})
    r = b.verify()
    heights = [f for f in r.check("D1-09").findings if f.code == "wrong_height"]
    assert len(heights) == b.n_labels
    assert r.check("D1-08").credit == 1.0
    assert r.effective_score == pytest.approx(100.0 - 6.0 * b.n_labels / b.d109_total, abs=1e-3)


def test_f_chain_mode_stationing_on_hand_drawn_linework():
    b = Base(seed=6, curves=2, equations=False)
    assert not b.truth.counts["equations"]
    # the reference's linework and stationing, swapped for raw linework and
    # entity-chain stationing (no anchors)
    old = [e.id for e in b.elements() + b.ticks() + b.labels("station") + b.labels("pc")
           + b.labels("pt")]
    b.ex("delete_entities", {"ids": old})
    align = b.doc.design.alignments[b.A]
    ids = []
    for el in align.elements:
        if el.kind == "tangent":
            res = b.ex("draw_line", {"space": "model", "start": list(el.start), "end": list(el.end),
                                     "layer": "V-ALIGN-CNTR"})
        else:
            s, e = el.ccw_angles()
            res = b.ex("draw_arc", {"space": "model", "center": list(el.center),
                                    "radius": el.radius, "start_angle_deg": s,
                                    "end_angle_deg": e, "layer": "V-ALIGN-CNTR"})
        ids.append(res["created"][0])
    b.ex("annotate_stationing", {"space": "model", "path_ids": ids,
                                 "begin_station": align.begin_station, "interval": 100,
                                 "tick_half_len": b.D["tick_half_len_ft"],
                                 "label_offset": b.D["label_offset_ft"],
                                 "text_height": b.D["text_heights"]["model_label_ft"],
                                 "layer": "V-ROAD-STA", "label_layer": "V-ANNO-TEXT"})
    r = b.verify()
    assert r.check("D1-01").credit == 1.0 and r.check("D1-02").credit == 1.0
    assert r.check("D1-03").credit == 0.0
    # only the C-n callouts (place_label) survive in D1-04
    assert r.check("D1-04").credit == pytest.approx(b.n_curves / b.n("D1-04"))
    assert any(f.code == "unanchored" for f in r.check("D1-07").findings)
    assert not r.hard_failed


def test_g_table_built_with_place_table_scores_zero():
    b = Base(**BASE)
    _table_as_place_table(b)
    r = b.verify()
    assert r.check("D1-06").credit == 0.0 and not r.hard_failed
    assert r.effective_score == 100.0 - 14.0


def test_h_design_recreated_under_a_new_name():
    b0 = Base(**BASE)
    task = b0.task
    from roaddraft.tasks.reference import session_for_task
    b0.session = session_for_task(task)  # start over from the baseline
    align = b0.doc.design.alignments[b0.A]
    b0.ex("create_alignment", {"name": "ALIGN-2", "begin_station": align.begin_station,
                               "pis": [list(p.point) + ([p.radius] if p.radius else [])
                                       for p in align.pis],
                               "equations": [{"back": q.back, "ahead": q.ahead}
                                             for q in align.equations]})
    for name, params in reference_commands(task):
        params = {k: ("ALIGN-2" if v == b0.A else v) for k, v in params.items()}
        b0.ex(name, params)
    r = b0.verify()
    assert r.design_fingerprint_ok
    for cid in ("D1-03", "D1-04", "D1-05", "D1-06"):
        assert r.check(cid).credit == 0.0
        assert "missing" in {f.code for f in r.check(cid).findings}
    assert r.check("D1-01").credit == 1.0 and r.check("D1-02").credit == 1.0
    assert r.effective_score <= NO_TEXT_CEILING


def test_i_spoofed_curve_table_anchor_is_unanchored():
    b = Base(**BASE)
    _table_as_place_table(b, spoof=True)
    r = b.verify()
    assert r.check("D1-06").credit == 0.0
    assert {f.code for f in r.check("D1-06").findings} == {"missing", "unanchored"}


def test_j_labels_piled_in_one_spot_lose_placement_and_legibility():
    b = Base(**BASE)
    p = b.free_model_point()
    for e in b.labels():
        b.ex("move_entities", {"ids": [e.id], "delta": [p[0] - e.position[0],
                                                        p[1] - e.position[1]]})
    r = b.verify()
    assert r.check("D1-07").credit == 0.0 and r.check("D1-08").credit == 0.0
    for cid in ("D1-03", "D1-04", "D1-05"):
        assert r.check(cid).credit == 1.0  # content credit stays: the rule is anchors
    assert r.effective_score == 100.0 - 8.0 - 6.0


def test_k_right_words_on_the_wrong_anchor_hard_fail():
    b = Base(**BASE)
    labels = b.labels("station")
    here, there = labels[3], labels[4]
    b.ex("delete_entities", {"ids": [there.id]})
    b.ex("place_label", {"space": "model", "alignment": b.A, "anchor": there.anchor["ref"],
                         "kind": "station", "content": here.content,
                         "label_offset": b.D["label_offset_ft"],
                         "height": b.D["text_heights"]["model_label_ft"],
                         "layer": "V-ANNO-TEXT"})
    r = b.verify()
    assert r.hard_failed and r.effective_score == 0.0
    assert [f.code for f in r.check("D1-03").findings] == ["wrong_value"]


def test_at_least_8_probes():
    probes = [n for n in globals() if n.startswith("test_") and n[5] in "abcdefghijk"
              and n[6] == "_"]
    assert len(probes) >= 8

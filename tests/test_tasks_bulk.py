"""The bulk dial (``tasks.bulk``): a seeded sheet at a real sheet's size, the three
training-only types that letter one piece of a referenced line on it, and the grounded
drafter's way through a sheet whose state comes back cut."""
import json

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.episode import RESULT_CAP, Episode, EpisodeConfig
from roaddraft.tasks import bulk
from roaddraft.tasks.generator import ALIGNMENT_NAME, SHEET_NAMES, generate_task
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.tasks.types import (BASE_LETTER_TYPES, HARD_TASK_TYPES, REAL_TASK_TYPES, TASK_TYPES,
                                   TRAIN_TASK_TYPES, task_type)
from roaddraft.trajectories import grounded
from roaddraft.verify import verify

LEVELS = ("explicit", "vague")
#: (seed, curves, type, twist) of tasks the set holds
SAMPLE = ((26000, 1, "base-stationing", False), (26001, 2, "base-bearings", True),
          (26002, 3, "base-callouts", False))


def _task(seed, curves, ttype, twist, bulked=True):
    return generate_task(seed, curves=curves, task_type=ttype, twist=twist, bulk=bulked)


@pytest.fixture(scope="module")
def tasks():
    return {row: _task(*row) for row in SAMPLE}


def test_the_base_lettering_types_are_training_only_and_mirror_the_real_ones():
    assert BASE_LETTER_TYPES == ("base-stationing", "base-bearings", "base-callouts")
    assert bulk.BULK_TYPES == BASE_LETTER_TYPES
    for name in BASE_LETTER_TYPES:
        assert name in TRAIN_TASK_TYPES
        assert name not in TASK_TYPES and name not in HARD_TASK_TYPES
        t, real = task_type(name), REAL_TASK_TYPES["real-" + name[len("base-"):]]
        # the same ask, on a line that lives in the base drawing, the rest handed over
        assert t.asks == real.asks and t.design_referenced
        assert {"reference", "sheet", "north", "title", "table"} <= t.given
        assert len(t.solution_phases()) == 1


@pytest.mark.parametrize("ttype", BASE_LETTER_TYPES)
@pytest.mark.parametrize("twist", [False, True])
def test_a_base_lettering_task_starts_at_0_and_its_reference_scores_100(ttype, twist):
    task = _task(26000 + twist, 2, ttype, twist, bulked=False)
    session = session_for_task(task)
    assert verify(session.doc, task.truth).effective_score == 0.0
    reference_solution(task, session)
    assert verify(session.doc, task.truth).effective_score == 100.0
    # unbulked it is the generator's own road, names and all
    assert task.brief.alignment_name == ALIGNMENT_NAME
    assert task.brief.deliverable["sheets"][0]["name"] == SHEET_NAMES[0]
    vague = task.brief.prompts["vague"]
    assert ALIGNMENT_NAME in vague and SHEET_NAMES[0] in vague and len(vague) < 80
    assert f"BASE:{ALIGNMENT_NAME}" in task.brief.prompts["explicit"]


def test_the_dial_fits_the_base_lettering_types_on_one_sheet_only():
    with pytest.raises(ValueError, match="not bulked"):
        generate_task(26000, curves=1, task_type="stationing", bulk=True)
    with pytest.raises(ValueError, match="one sheet"):
        generate_task(26000, curves=1, task_type="base-stationing", sheets=2, bulk=True)
    with pytest.raises(ValueError, match="station equation"):
        generate_task(26000, curves=1, task_type="base-stationing", equations=True, bulk=True)
    # a task is bulked, or crowded or revised: the crowd and revision dials have their own types
    with pytest.raises(ValueError):
        generate_task(26000, curves=1, task_type="base-stationing", crowd=True, bulk=True)
    with pytest.raises(ValueError):
        generate_task(26000, curves=1, task_type="base-stationing", revise=True, bulk=True)


def test_the_names_are_an_offices_and_drawn_on_their_own_stream():
    seen = [bulk.names(seed, "SR 12") for seed in range(26000, 26060)]
    assert seen[0] == bulk.names(26000, "SR 12")
    for n in seen:
        assert n["design"] != n["survey"] and n["design_file"] != n["survey_file"]
        # the survey in one to three files, every part of it in exactly one, no name twice
        assert n["surveys"][0] == {"name": n["survey"], "file": n["survey_file"],
                                   "parts": n["surveys"][0]["parts"]}
        assert sorted(p for r in n["surveys"] for p in r["parts"]) == sorted(bulk.SURVEY_PARTS)
        assert "topo" in n["surveys"][0]["parts"] and 1 <= len(n["surveys"]) <= 3
        assert len({n["design"]} | {r["name"] for r in n["surveys"]}) == 1 + len(n["surveys"])
        assert len({n["design_file"]} | {r["file"] for r in n["surveys"]}) == 1 + len(n["surveys"])
        assert n["side"] != n["alignment"]
        assert ":" not in n["alignment"] and " " not in n["alignment"]
        assert n["alignment"] != ALIGNMENT_NAME and n["sheet"] not in SHEET_NAMES
        assert "BASE" not in (n["design"], n["survey"])
    assert len({n["alignment"] for n in seen}) > 30 and len({n["design"] for n in seen}) > 8
    # two, three and four references on a sheet, the design's attached first or last
    assert {len(n["surveys"]) for n in seen} == {1, 2, 3}
    assert {n["design_first"] for n in seen} == {True, False}


def test_a_bulked_task_is_the_plain_road_at_a_real_sheets_size(tasks):
    for row, task in tasks.items():
        seed, curves, ttype, twist = row
        plain = _task(seed, curves, ttype, twist, bulked=False)
        assert task.task_id != plain.task_id
        D = task.brief.deliverable
        n = bulk.names(seed, task.brief.project["route"])
        assert task.brief.alignment_name == n["alignment"] and D["sheets"][0]["name"] == n["sheet"]
        assert D["design_reference"] == n["design"] and D["basefile"] == n["design_file"]
        late = {"after_design": True} if n["design_first"] else {}
        assert D["references"] == [{"name": r["name"], "file": r["file"], "space": "model", **late}
                                   for r in n["surveys"]]
        assert D["bulk"] == {"version": bulk.BULK_VERSION}
        # the same road under another name: its geometry and its sheet's view are the seed's
        a, b = (t.brief.design["alignments"][t.brief.alignment_name] for t in (task, plain))
        assert {k: v for k, v in a.items() if k != "name"} == {k: v for k, v in b.items()
                                                               if k != "name"}
        # (an agency border moves the plan on the paper, clear of its binding strip)
        view, plain_view = (dict(t.brief.deliverable["sheets"][0]["viewport"]) for t in (task, plain))
        moved = view.pop("center_paper") != plain_view.pop("center_paper")
        assert view == plain_view
        sh = D["sheets"][0]
        template = sh.get("template", "standard")
        assert moved == (template == "caltrans")
        assert template in [b["template"] for b in bulk.borders(seed, 34.0, 22.0, view)]
        size = bulk.describe(task)
        assert size["state_chars"] > bulk.STATE_FLOOR > RESULT_CAP
        assert size["paper_entities"] >= 150
        assert size["files"][n["survey_file"]] >= 200 and size["files"][n["design_file"]] >= 100
        session = session_for_task(task)
        refs = [r["name"] for r in session.query("list_references", {})["references"]]
        others = [r["name"] for r in n["surveys"]]
        assert refs == ([n["design"]] + others if n["design_first"] else others + [n["design"]])
        # the design file's lines: the task's, and most times a second one beside or across it
        lines = [a["name"] for a in session.query("list_alignments", {"include_references": True})[
            "alignments"]]
        assert f"{n['design']}:{n['alignment']}" in lines
        assert set(lines) <= {f"{n['design']}:{n['alignment']}", f"{n['design']}:{n['side']}"}
        assert list(task.brief.design["alignments"]) == [n["alignment"]]
        # what was handed over is listed, so legibility judges only the new work against it
        given = set(task.truth.sheets[0]["given_entities"])
        sheet = session.doc.sheet_by_ref(n["sheet"])
        # the border is the sheet's, every field it letters filled, nothing drawn on its
        # title block
        assert sheet.title_block_template == template
        if template != "standard":
            from roaddraft.render.titleblock import template_keys
            assert set(sh["title_block_fields"]) <= set(template_keys(template))
            assert sh["required_title_fields"] == list(sh["title_block_fields"])
            assert sheet.title_block_fields == sh["title_block_fields"]
        for box in bulk._border(template, 34.0, 22.0, view)["blocked"]:
            for e in sheet.entities.values():
                bb = e.bbox(session.doc)
                assert (bb[2] <= box[0] or bb[0] >= box[2] or bb[3] <= box[1]
                        or bb[1] >= box[3]), (template, e.id, bb, box)
        assert set(sheet.entities) <= given and set(session.doc.model_entities) <= given
        assert verify(session.doc, task.truth).effective_score == 0.0
        reference_solution(task, session)
        assert verify(session.doc, task.truth).effective_score == 100.0


def test_a_bulked_prompt_names_the_line_and_the_sheet_as_a_real_one_does(tasks):
    task = tasks[SAMPLE[1]]
    n = bulk.names(SAMPLE[1][0], task.brief.project["route"])
    assert task.brief.prompts["vague"] == (f"Add the bearings of the {n['alignment']} line to "
                                           f"sheet {n['sheet']}.")
    explicit = task.brief.prompts["explicit"]
    assert f"attached as {n['design']}, so reach it as {n['design']}:{n['alignment']}" in explicit
    assert f"{n['survey_file']} as {n['survey']}" in explicit and "turned" in explicit
    assert "BASE" not in explicit.replace("BASE:ALIGN-1", "")


def test_linework_runs_under_the_line_and_some_base_text_stands_in_its_lettering(tasks):
    """A plan sheet's topo does not stop at the road: contours cross it, the existing
    pavement and the design's own shoulders and slopes run along it, and here and there
    a base file's text stands inside the line's lettering (bulk-v3)."""
    from roaddraft.design.errors import DesignError
    from roaddraft.design.horizontal import Alignment
    from roaddraft.document.document import Document
    for row, task in tasks.items():
        D = task.brief.deliverable
        name = task.brief.alignment_name
        align = Alignment.from_dict(task.brief.design["alignments"][name])
        fpi = D["feet_per_inch"]
        files = [D["basefile"]] + [r["file"] for r in D["references"]]
        layers = {n for n, *_rest in bulk.SURVEY_LAYERS + bulk.DESIGN_LAYERS}
        near, lettered = {}, 0
        for fname in files:
            doc = Document.from_dict(task.files[fname])
            near[fname] = 0
            for e in doc.model_entities.values():
                if (e.anchor or {}).get("alignment") == name:
                    continue  # the line itself
                d = e.to_dict()
                pts = d.get("vertices") or [d[k] for k in ("start", "end", "position", "center")
                                            if k in d]
                inside = []
                for q in pts:
                    try:  # past either end of the line a point does not project onto it
                        inside.append(align.xy_to_station(q))
                    except DesignError:
                        pass
                if not inside:
                    continue
                off = min(abs(w["offset"]) for w in inside)
                if e.TYPE == "text":
                    lettered += off <= bulk.NEAR_IN * fpi
                elif off <= 0.5 * fpi:
                    near[fname] += 1
            if fname != D["basefile"]:
                assert {e.layer for e in doc.model_entities.values()} <= layers
        # within half an inch of the line on the paper: the design file's own linework and
        # the topo's, tens of pieces each
        assert near[D["basefile"]] >= 20 and near[D["references"][0]["file"]] >= 20, near
        assert 1 <= lettered <= 40, lettered


def test_the_borders_are_an_agencys_most_times_and_fall_back_to_the_seeded_one():
    view = {"height_in": 18.5, "width_in": 31.0}
    first = [bulk.borders(seed, 34.0, 22.0, view) for seed in range(26000, 26200)]
    assert {b[0]["template"] for b in first} == {"caltrans", "wfl", "standard"}
    assert all(b[-1]["template"] == "standard" and not b[-1]["blocked"] for b in first)
    n = sum(b[0]["template"] == "caltrans" for b in first)
    assert 80 <= n <= 140
    ct = bulk._border("caltrans", 34.0, 22.0, view)
    # the plan sits inside the Caltrans frame, right of its binding strip
    cx, cy = ct["center_paper"]
    assert cx - 15.5 > 1.904 and cx + 15.5 < 34.0 - 0.503 and cy - 9.25 > 0.503
    # a line under the title block does not fit the border; one in the middle does
    vp = {"center_paper": ct["center_paper"], "model_center": [0.0, 0.0], "feet_per_inch": 50.0}
    assert bulk.border_fits(ct, vp, [[-500.0, 0.0], [500.0, 0.0]])
    assert not bulk.border_fits(ct, vp, [[0.0, 0.0], [640.0, 420.0]])
    fields = bulk.border_fields(26000, "caltrans", {"scale": "1\" = 50'"},
                                {"route": "SR 12", "county": "PIKE COUNTY", "agency": "X"}, "L-9")
    assert fields["route"] == "12" and fields["county"] == "PIK" and fields["sheet_id"] == "L-9"
    assert bulk.border_fields(26000, "standard", {"a": "b"}, {}, "L-9") == {"a": "b"}


def test_a_label_that_lands_on_base_text_is_set_again_and_searched_again():
    """Seed 26001 as the set holds it: a bearing's default pose lands on a base file's
    text.  The truth sets it on the other side of the line (``label_poses``), and the
    drafter, on a sheet too large to read whole, moves it and searches where it landed."""
    d = tasksets.bulk_dials(1)
    task = tasksets.make_task(26001, d["curves"], False, d["task_type"], 1, d["twist"], bulk=True)
    assert task.brief.deliverable["label_poses"]["bearings"]
    assert task.task_id in {e["task_id"] for e in tasksets.entries("d1-train-bulk")}
    episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level="vague"))
    result = episode.run()
    assert result.termination == "submit", result.error
    assert result.effective_score == 100.0
    assert grounded.audit(episode.brief_text, episode.tools, episode.turns) == []
    words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "Delete it and set the same label again" in words
    assert "own text height, which the list did not give" in words
    calls = [c["name"] for turn in episode.turns for c in turn["assistant"]["tool_calls"]]
    assert calls.count("get_sheet_state") == 1 and "get_entity" in calls


@pytest.mark.parametrize("level", LEVELS)
def test_the_grounded_drafter_reads_the_head_of_a_cut_sheet_and_asks_narrowly(tasks, level):
    for row, task in tasks.items():
        episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level=level))
        result = episode.run()
        assert result.termination == "submit", result.error
        assert result.effective_score == 100.0
        assert grounded.audit(episode.brief_text, episode.tools, episode.turns) == []
        pairs = [(c, r) for turn in episode.turns
                 for c, r in zip(turn["assistant"]["tool_calls"], turn["results"])]
        cut = [c["name"] for c, r in pairs if r.get("truncated")]
        # the sheet's state is asked for once, comes back cut, and is not asked for again
        assert cut == ["get_sheet_state"]
        assert sum(1 for c, _r in pairs if c["name"] == "get_sheet_state") == 1
        # every search after it names what it wants: a line, or a box; none is of the whole sheet
        finds = [c["params"] for c, _r in pairs if c["name"] == "find_entities"]
        assert finds and all("anchor" in q or "bounds" in q for q in finds)
        assert all(r["total"] < 100 for c, r in pairs if c["name"] == "find_entities")
        words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
        assert "was cut" in words and "Its head came whole" in words
        n = task.brief.deliverable["design_reference"]
        assert f"{n}:{task.brief.alignment_name}" in words


def test_recorded_through_the_recorder_a_bulked_task_is_kept(tasks):
    row = grounded.record_task(tasks[SAMPLE[2]], "vague")
    assert row["kept"] and row["ungrounded"] == [] and row["lost"] == {}


def test_the_head_of_a_cut_sheet_state_is_read_and_a_cut_inside_it_is_not():
    task = _task(*SAMPLE[0])
    session = session_for_task(task)
    name = task.brief.deliverable["sheets"][0]["name"]
    whole = session.query("get_sheet_state", {"sheet": name})
    text = json.dumps(whole, ensure_ascii=False)
    state = grounded._cut_sheet({"ok": True, "truncated": True, "text": text[:RESULT_CAP]})
    assert state["cut"] is True and "entities" not in state and "usable_area" not in state
    assert state["name"] == name and state["viewports"][0]["feet_per_inch"] == \
        whole["sheet"]["viewports"][0]["feet_per_inch"]
    assert state["viewports"][0]["rotation_deg"] == whole["sheet"]["viewports"][0]["rotation_deg"]
    assert state["title_block_fields"] == whole["sheet"]["title_block_fields"]
    at = text.index('"viewports"')
    with pytest.raises(grounded.NotCovered, match="cut before its viewports"):
        grounded._cut_sheet({"ok": True, "truncated": True, "text": text[:at + 40]})


def test_a_cut_answer_is_read_only_where_a_caller_reads_its_head():
    from roaddraft.eval.agents import ToolCall
    calls = [ToolCall("get_sheet_state", {"sheet": "L-1"})]
    cut = [{"ok": True, "name": "get_sheet_state", "truncated": True, "text": "{"}]
    grounded._ok(cut, calls, cut=("get_sheet_state",))
    with pytest.raises(grounded.NotCovered, match="the result was cut"):
        grounded._ok(cut, calls)


def test_sheet_work_on_a_cut_sheet_is_not_guessed_at():
    """The drafter does not put a north arrow on a sheet whose state it could not read:
    whether the sheet has one already is past the cut, and it says so.  (A title block is
    filled from the head of the state and a curve table's place is searched for once it is
    down, since 2026-11-27: ``tests/test_trajectories_grounded_real.py``.)"""
    task = _task(*SAMPLE[0])
    solver = grounded.solve(grounded_text(task), ["stationing", "north"])
    turn = next(solver)
    session = session_for_task(task)
    episode_results = None
    with pytest.raises(grounded.NotCovered, match="was cut, and the work needs"):
        while True:
            results = []
            for call in turn.calls:
                r = session.query(call.name, call.params) if call.name.startswith(
                    ("get_", "list_", "find_")) else session.execute(call.name, call.params)
                text = json.dumps(r, ensure_ascii=False)
                if len(text) > RESULT_CAP:
                    r = {"ok": True, "name": call.name, "truncated": True,
                         "text": text[:RESULT_CAP]}
                results.append(r)
            episode_results = results
            turn = solver.send(results)
    assert episode_results is not None


def grounded_text(task):
    from roaddraft.tasks.prompts import task_text
    return task_text(task.brief, "vague")


def test_the_bulk_training_set_is_600_bulked_sheets_on_seeds_of_its_own():
    from collections import Counter
    manifest = tasksets.load("d1-train-bulk")
    rows = manifest["tasks"]
    kept = [s for s in tasksets.TRAIN_BULK_SEEDS if s not in manifest["skipped_seeds"]]
    assert tasksets.TRAIN_BULK_SEEDS == range(26000, 26600)
    assert [t["seed"] for t in rows] == kept and len(kept) >= 0.95 * len(tasksets.TRAIN_BULK_SEEDS)
    assert all(t["bulk"] and t["sheets"] == 1 and not t["equations"] for t in rows)
    assert set(t["task_type"] for t in rows) == set(BASE_LETTER_TYPES)
    # no base lettering task and no bulked task anywhere else
    for name in tasksets.NAMES + tuple(n for n in tasksets.TRAIN_NAMES if n != "d1-train-bulk"):
        other = tasksets.load(name)["tasks"]
        assert not any(t.get("task_type") in BASE_LETTER_TYPES or t.get("bulk") for t in other), name
    combos = Counter((t["task_type"], t["curves"], bool(t.get("twist"))) for t in rows)
    assert set(combos) == {(ty, c, w) for ty in BASE_LETTER_TYPES for c in (1, 2, 3)
                           for w in (False, True)}
    turned = sum(1 for t in rows if t.get("twist"))
    assert abs(turned - 2 * len(rows) / 3) <= 9
    assert [tasksets.bulk_dials(i)["task_type"] for i in range(3)] == list(BASE_LETTER_TYPES)
    assert [tasksets.bulk_dials(i)["curves"] for i in (0, 3, 6)] == [1, 2, 3]
    assert [tasksets.bulk_dials(i)["twist"] for i in (0, 9, 18, 27)] == [False, True, True, False]
    # an entry rebuilds to its id, and without the dial to another task
    entry = rows[4]
    assert tasksets.task_from_entry(entry).task_id == entry["task_id"]
    plain = {k: v for k, v in entry.items() if k != "bulk"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_a_line_is_named_by_a_word_of_its_own_not_by_a_piece_of_another():
    # the second line of a design file can be called anything: "AN" is not named by "ANSI D"
    text = "Sheet C-43 is an ANSI D plan sheet, its viewport on T5. Reach it as CORR:T5."
    assert grounded._named(text, ["CORR:T5", "CORR:AN"]) == "CORR:T5"
    assert grounded._named(text, ["CORR:AN", "CORR:T5"]) == "CORR:T5"
    assert grounded._named("Station ALIGN-1.", ["BASE:ALIGN-1"]) == "BASE:ALIGN-1"
    assert grounded._named("Station the line.", ["BASE:ALIGN-1", "BASE:X"]) == "BASE:ALIGN-1"

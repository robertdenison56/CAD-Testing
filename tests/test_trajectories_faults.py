"""Injected faults (``roaddraft.trajectories.faults``, ``RoadDraft_Training_Plan.md``
section 3, *Data*): a grounded reference with the 9B's own mistakes put in, each
broken call refused by the engine, everything else exactly the reference, and the
broken turns weighing nothing in the conversation."""
from __future__ import annotations

import importlib.util
import json
import random
from collections import Counter
from pathlib import Path

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.episode import Episode, EpisodeConfig
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.prompts import task_text
from roaddraft.trajectories import conversations as cv
from roaddraft.trajectories import faults, grounded

REPO = Path(__file__).resolve().parents[1]


def _task(ttype: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-dev")["tasks"] if e["task_type"] == ttype]
    return tasksets.task_from_entry(rows[n])


@pytest.fixture(scope="module")
def references(tmp_path_factory):
    """Grounded references of three d1-dev tasks that between them take every kind."""
    root = tmp_path_factory.mktemp("references")
    out = {}
    for ttype in ("annotate-base", "plan-sheet", "attach-reference"):
        task = _task(ttype)
        row = grounded.record_task(task, "vague", out_root=root)
        assert row["kept"], row
        out[ttype] = (task, Path(row["path"]))
    return out


def _parts(task, path):
    records = read_episode(path)
    return records, task_text(task.brief, "vague")


def _play(task, turns, chosen, out_root, seed=0):
    steps = faults.plan(turns, chosen, random.Random(seed))
    episode = Episode(task, faults.FaultAgent(steps), EpisodeConfig(level="vague"), out_root=out_root)
    return episode, episode.run()


def test_every_kind_has_a_place_in_the_references_and_the_engine_refuses_each(references, tmp_path):
    seen = set()
    for ttype, (task, path) in references.items():
        records, brief = _parts(task, path)
        turns = records["turns"]
        by_kind = {}
        for site in faults.sites(brief, turns):
            by_kind.setdefault((site.kind, site.tool), site)
        for (kind, tool), site in sorted(by_kind.items()):
            episode, result = _play(task, turns, [site], tmp_path / f"{ttype}-{kind}-{tool}")
            assert faults._miss(result, episode, records["journal"], brief) is None, (ttype, kind, tool)
            broken = [t for t in episode.turns if (t["assistant"].get("fault") or {}).get("role") == "broken"]
            assert len(broken) == 1
            failed = broken[0]["results"][-len(site.broken):]
            assert all(not r["ok"] and r["error"]["type"] in faults.FAILED for r in failed)
            seen.add(kind)
    assert seen == {k.name for k in faults.KINDS}


def test_a_copy_is_the_reference_with_the_broken_turns_taken_out(references, tmp_path):
    task, path = references["annotate-base"]
    records, brief = _parts(task, path)
    turns = records["turns"]
    found = faults.sites(brief, turns)
    chosen = faults.choose(found, random.Random(3), 2)
    assert len(chosen) == 2 and len({s.kind for s in chosen}) == 2
    episode, result = _play(task, turns, chosen, tmp_path)
    assert result.termination == "submit" and result.effective_score == 100.0
    kept = [t for t in episode.turns if (t["assistant"].get("fault") or {}).get("role") != "broken"]
    calls = [c for t in kept for c in t["assistant"]["tool_calls"]]
    assert calls == [c for t in turns for c in t["assistant"]["tool_calls"]]
    # the journal is the reference's: a refused call changed nothing
    assert faults._same({"e": list(episode.session.bus.journal)}, {"e": records["journal"]["entries"]})
    assert result.steps == records["end"]["steps"] + sum(len(s.broken) for s in chosen)


def test_a_broken_call_that_works_or_a_result_that_differs_is_a_miss(references, tmp_path):
    task, path = references["annotate-base"]
    records, brief = _parts(task, path)
    turns = records["turns"]
    harmless = faults.Site("layer_not_made", "place_label", 1, -1,
                           [{"name": "list_layers", "params": {}}], "Look at the layers.", ("Carry on.",))
    episode, result = _play(task, turns, [harmless], tmp_path / "works")
    assert result.termination == "error" and "did not fail" in result.error
    changed = json.loads(json.dumps(turns))
    changed[0]["results"][0]["summary"] = {"changed": True}
    episode, result = _play(task, changed, [], tmp_path / "differs")
    assert result.termination == "error" and "other than in the reference" in result.error


def test_a_reference_whose_faults_all_miss_is_left_out_and_its_file_removed(references, tmp_path, monkeypatch):
    task, path = references["annotate-base"]
    harmless = faults.Site("layer_not_made", "place_label", 1, -1,
                           [{"name": "list_layers", "params": {}}], "Look at the layers.", ("Carry on.",))
    monkeypatch.setattr(faults, "sites", lambda brief, turns: [harmless])
    row = faults.inject(path, "d1-dev", tmp_path)
    assert not row["kept"] and "did not fail" in row["reason"]
    assert row["tried"] and not list(tmp_path.rglob("*.jsonl"))


def _site(kind, tool, turn):
    return faults.Site(kind, tool, turn, 0, [{"name": tool, "params": {}}], "", ("",))


def test_choose_weighs_a_kind_by_the_9bs_rate_then_its_tool():
    pool = [_site("alignment_left_off", "place_label", 4), _site("alignment_misnamed", "place_label", 4),
            _site("alignment_misnamed", "get_design_data", 2)]
    picked = Counter()
    for seed in range(3000):
        (site,) = faults.choose(pool, random.Random(seed), 1)
        picked[(site.kind, site.tool)] += 1
    left = sum(faults.KIND["alignment_left_off"].tools.values())
    misnamed = faults.KIND["alignment_misnamed"].tools
    # the kind by its whole count (488 to 95), not by the sum of the tools this reference offers it
    share = picked[("alignment_left_off", "place_label")] / 3000
    assert abs(share - left / (left + sum(misnamed.values()))) < 0.03
    # within the kind, the tool by its own count (17 to 5)
    tools = picked[("alignment_misnamed", "get_design_data")] / max(1, 3000 - share * 3000)
    assert abs(tools - misnamed["get_design_data"] / (misnamed["get_design_data"] + misnamed["place_label"])) < 0.06


def test_choose_keeps_faults_apart():
    pool = [_site("alignment_left_off", "place_label", 4), _site("alignment_misnamed", "place_label", 4),
            _site("layer_not_made", "place_label", 5), _site("begin_station_given", "annotate_stationing", 9)]
    for seed in range(400):
        chosen = faults.choose(pool, random.Random(seed), 2)
        assert len({s.kind for s in chosen}) == len(chosen)
        turns = sorted(s.turn for s in chosen)
        assert all(b - a > 1 for a, b in zip(turns, turns[1:]))


def test_the_shown_work_of_a_broken_turn_names_what_the_broken_calls_use():
    text = "ALIGN-1 has 2 tangents. Letter each on align_MAIN-anno; ALIGN-12 and BASE:ALIGN-1 stay."
    assert faults._swap_name(text, "ALIGN-1", "BASE:ALIGN-1") == (
        "BASE:ALIGN-1 has 2 tangents. Letter each on align_MAIN-anno; ALIGN-12 and BASE:ALIGN-1 stay.")
    assert "on C-ANNO-TEXT;" in faults._swap_name(text, "align_MAIN-anno", "C-ANNO-TEXT")
    assert faults._swap_name("on align_MAIN-anno", "align_MAIN", "X") == "on align_MAIN-anno"


# ------------------------------------------------------------ the conversation

def test_a_faulted_copy_converts_with_its_broken_turns_weighing_nothing(references, tmp_path):
    task, path = references["annotate-base"]
    row = faults.inject(path, "d1-dev", tmp_path)
    assert row["kept"], row
    conv, _ = cv.convert_episode(row["path"], "d1-dev")
    head, msgs = conv["header"], conv["messages"]
    assert conv["id"].endswith(".vague.faults")
    assert [f["kind"] for f in head["injected"]] == [f["kind"] for f in row["faults"]]
    masked = [i for i, m in enumerate(msgs) if m.get("weight") == 0]
    assert len(masked) == len(row["faults"]) == head["counts"]["masked"]
    for i in masked:
        # each broken message is answered by tool results, the last of them refused, then the recovery
        j = i + 1
        while msgs[j]["role"] == "tool":
            j += 1
        assert json.loads(msgs[j - 1]["content"])["ok"] is False
        assert msgs[j]["role"] == "assistant" and "weight" not in msgs[j]
    reference, _ = cv.convert_episode(path, "d1-dev")
    assert reference["id"].endswith(".vague") and "injected" not in reference["header"]
    assert not any("weight" in m for m in reference["messages"])
    trained = [c["function"] for m in msgs if m["role"] == "assistant" and m.get("weight") != 0
               for c in m.get("tool_calls") or []]
    assert trained == [c["function"] for m in reference["messages"] if m["role"] == "assistant"
                       for c in m.get("tool_calls") or []]


def test_the_audit_leaves_out_the_broken_turns_and_nothing_else(references, tmp_path):
    task, path = references["annotate-base"]
    records, brief = _parts(task, path)
    site = next(s for s in faults.sites(brief, records["turns"]) if s.kind == "layer_not_made")
    episode, result = _play(task, records["turns"], [site], tmp_path)
    found = grounded.audit(brief, episode.tools, episode.turns)
    broken = faults.broken_turns(episode.turns)
    assert found and {f["turn"] for f in found} <= broken     # the made-up layer name, in the broken turn
    assert faults.audit_turns(brief, episode.tools, episode.turns) == []


def test_the_sets_and_the_card_carry_the_faulted_copies(tmp_path):
    src, faulted, out = tmp_path / "src", tmp_path / "faults", tmp_path / "out"
    index = grounded.record("d1-dev", src / "d1-dev-vague", level="vague",
                            types=["annotate-base", "layer-setup"])
    assert index["kept"] == 7
    done = faults.run(["d1-dev"], ["vague"], source=src, out=faulted, log=lambda *_: None)
    fi = done["d1-dev-vague"]
    # layer-setup makes its layers and stops: no place for a fault
    assert fi["kept"] == 4 and fi["tasks"] == 7 and fi["not_kept"] == {"no site": 3}
    summary = cv.run(["d1-dev"], ["vague"], source=src, out=out, faults=faulted, log=lambda *_: None)
    tally = summary["sets"]["d1-dev-vague-faults"]
    assert tally["variant"] == "faults" and tally["kept"] == 4 and tally["dropped"] == {}
    assert sum(tally["injected"].values()) == fi["faults"] == tally["masked"]
    ids = [json.loads(line)["id"] for line in (out / "d1-dev-vague-faults.jsonl").read_text().splitlines()]
    assert len(ids) == 4 and all(i.endswith(".vague.faults") for i in ids)
    card = cv.card(out, tmp_path / "CARD.md").read_text()
    assert "## Injected faults" in card and "| `alignment_left_off` |" in card
    assert "-faults.jsonl` holds their faulted copies" in card
    no_faults = cv.run(["d1-dev"], ["vague"], source=src, out=tmp_path / "plain", faults=None,
                       log=lambda *_: None)
    assert set(no_faults["sets"]) == {"d1-dev-vague"}


def test_the_token_count_leaves_weight_0_messages_out_of_the_loss():
    spec = importlib.util.spec_from_file_location("training_tokens", REPO / "scripts" / "training_tokens.py")
    tt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tt)

    class Words:
        class Enc:
            def __init__(self, text):
                self.ids = text.split()

        def encode(self, text, add_special_tokens=False):
            return self.Enc(text)

        def encode_batch(self, texts, add_special_tokens=False):
            return [self.Enc(t) for t in texts]

    text = ("<|im_start|>system\na b<|im_end|>\n<|im_start|>user\nc<|im_end|>\n"
            "<|im_start|>assistant\nd e f<|im_end|>\n<|im_start|>user\n<tool_response>\ng\n"
            "</tool_response><|im_end|>\n<|im_start|>assistant\nh<|im_end|>\n")

    class Template:
        def render(self, **_):
            return text
    counter = tt.Counter(Words())
    blocks = counter.blocks(text)
    said = [n for role, n in blocks if role == "assistant"]
    conv = {"messages": [{"role": "system"}, {"role": "user"}, {"role": "assistant", "weight": 0},
                         {"role": "tool"}, {"role": "assistant"}]}
    assert tt.count_conversation(counter, Template(), conv, [])[2] == said[1]
    assert tt.count_conversation(counter, Template(), {"messages": []}, [])[2] == sum(said)

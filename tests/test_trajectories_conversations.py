"""Eval episode files as training conversations
(``roaddraft.trajectories.conversations``, ``RoadDraft_Training_Plan.md`` section 5,
step 3): the conversation is what the harness sends a model, rebuilt from the
episode file, and only an episode that re-scores 100 on this checkout's task and
tools becomes one."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from roaddraft.eval import prompts
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents.llm import LLMAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import Episode, EpisodeConfig
from roaddraft.eval.providers.fake import FakeProvider, turn
from roaddraft.tasks.reference import solution_commands
from roaddraft.trajectories import conversations as cv
from roaddraft.trajectories import grounded

REPO = Path(__file__).resolve().parents[1]


def _task(ttype: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-dev")["tasks"] if e["task_type"] == ttype]
    return tasksets.task_from_entry(rows[n])


def _llm_episode(tmp_path, task, provider, level="vague", budgets=Budgets()):
    agent = LLMAgent(provider, label="fake-model")
    result = Episode(task, agent, EpisodeConfig(level=level, budgets=budgets),
                     out_root=tmp_path).run()
    return result, Path(result.path)


def _rewrite(path: Path, out: Path, change) -> Path:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    change(records)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return out


def _shape(message: dict) -> tuple:
    if message["role"] == "assistant":
        return ("assistant", message.get("content") or "",
                [(c["function"]["name"], c["function"]["arguments"]) for c in message.get("tool_calls") or []])
    if message["role"] == "tool":
        return ("tool", message["name"], message["content"])
    return (message["role"], message["content"])


def _sent(transcript) -> list:
    """The agent's own transcript, shaped like the conversation's messages."""
    out = []
    for m in transcript:
        if m["role"] == "user":
            out.append(("user", m["text"]))
        elif m["role"] == "assistant":
            out.append(("assistant", m.get("text") or "", [(c["name"], c["params"]) for c in m["calls"]]))
        else:
            out += [("tool", r["name"], r["content"]) for r in m["results"]]
            if m.get("note"):
                out.append(("user", m["note"]))
    return out


@pytest.fixture(scope="module")
def oracle_run(tmp_path_factory):
    """An LLM agent replaying the oracle three calls a turn, on budgets tight
    enough that the harness's notes come in: the faults note every turn, the
    steps note near the end."""
    tmp = tmp_path_factory.mktemp("oracle")
    task = _task("stationing")
    steps = len(solution_commands(task)) + 8
    provider = FakeProvider.oracle(per_turn=3)
    result, path = _llm_episode(tmp, task, provider, budgets=Budgets(steps=steps, faults=3))
    assert result.termination == "submit" and result.effective_score == 100.0
    return task, provider, result, path


def test_the_conversation_is_what_the_harness_sent_the_model(oracle_run):
    task, provider, result, path = oracle_run
    conv, defs = cv.convert_episode(path, "d1-dev", audit=False)
    msgs = conv["messages"]
    last = provider.requests[-1]
    # system and tools as the agent sent them
    assert msgs[0] == {"role": "system", "content": last["system"]}
    assert [d["name"] for d in defs] == last["tools"]
    # every message the model was sent, in order: the task, each turn's calls, their results, the notes
    assert [_shape(m) for m in msgs[1:-1]] == _sent(last["transcript"])
    # and the model's last turn, which nothing answered: the submit call
    assert _shape(msgs[-1])[2] == [("submit", {"note": "reference solution replayed"})]
    head = conv["header"]
    assert head["counts"]["notes"] == len(provider.requests) - 1
    assert any("steps left" in m["content"] for m in msgs if m["role"] == "user")
    assert all("3 more turns in a row" in m["content"] for m in msgs[2:] if m["role"] == "user")


def test_the_header_pins_the_episode(oracle_run):
    task, provider, result, path = oracle_run
    conv, defs = cv.convert_episode(path, "d1-dev", audit=False)
    episode_header = json.loads(path.read_text().splitlines()[0])
    head = conv["header"]
    for key in ("task_id", "tools_sha256", "prompt_hash", "spec_version", "spec_hash",
                "generator_version", "verifier_version", "harness_version", "level", "mode", "seed"):
        assert head[key] == episode_header[key], key
    assert head["system_sha256"] == episode_header["prompt_sha256"]
    assert head["tools_sha256"] == cv.tools_sha256(defs)
    assert head["score"]["effective"] == 100.0
    assert head["source"] == "rollout" and head["agent"] == "fake-model"
    assert conv["id"] == f"{task.task_id}.vague"


def test_the_tools_go_out_as_the_openai_compatible_provider_sends_them(oracle_run):
    _, _, _, path = oracle_run
    _, defs = cv.convert_episode(path, "d1-dev", audit=False)
    sent = cv.function_tools(defs)
    assert [t["function"]["name"] for t in sent] == [d["name"] for d in defs]
    assert all(t["type"] == "function" and t["function"]["parameters"] == d["input_schema"]
               for t, d in zip(sent, defs))


def test_a_turn_that_stopped_early_hands_back_not_run_for_the_calls_it_skipped():
    turns =[{"n": 1, "assistant": {"text": "two at once", "tool_calls": [
                {"name": "list_layers", "params": {}}, {"name": "list_sheets", "params": {}}]},
              "results": [{"ok": True, "name": "list_layers", "layers": []}]},
             {"n": 2, "assistant": {"text": "done", "tool_calls": [{"name": "submit", "params": {}}]},
              "results": [{"ok": True, "name": "submit", "message": "submitted"}]}]
    msgs = cv.messages("sys", "task", turns, Budgets())
    tools = [m for m in msgs if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tools] == ["call_0001", "call_0002"]
    assert json.loads(tools[0]["content"]) == {"ok": True, "name": "list_layers", "layers": []}
    assert json.loads(tools[1]["content"])["error"]["type"] == "not_run"
    assert tools[0]["content"] == '{"ok":true,"name":"list_layers","layers":[]}'   # compact, as sent
    # the last turn's results never reached the model
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["tool_calls"][0]["function"]["name"] == "submit"


def test_a_fault_streak_is_counted_by_turn_for_the_note():
    bad = {"ok": False, "name": "x", "error": {"type": "invalid_params", "message": "no"}}
    turns = [{"n": i, "assistant": {"text": "", "tool_calls": [{"name": "x", "params": {}}] * 2},
              "results": [bad, bad]} for i in range(1, 4)]
    turns.append({"n": 4, "assistant": {"text": "", "tool_calls": [{"name": "submit", "params": {}}]},
                  "results": []})
    msgs = cv.messages("sys", "task", turns, Budgets(faults=4))
    notes = [m["content"] for m in msgs if m["role"] == "user"][1:]
    # four allowed, one turn of failures leaves three: the note starts after the first turn
    assert notes == ["[harness] 3 more turns in a row with every call failing end the task.",
                     "[harness] 2 more turns in a row with every call failing end the task.",
                     "[harness] 1 more turns in a row with every call failing end the task."]


def test_a_grounded_reference_converts_and_keeps_its_shown_work(tmp_path):
    task = _task("layer-setup")
    row = grounded.record_task(task, "vague", out_root=tmp_path)
    assert row["kept"]
    conv, defs = cv.convert_episode(row["path"], "d1-dev")
    head, msgs = conv["header"], conv["messages"]
    assert head["source"] == "reference" and head["recorded_commit"] is None
    # the grounded drafter has no system prompt: it gets the one an LLM agent gets on the episode
    assert msgs[0]["content"] == prompts.system_prompt("neutral", "single", Budgets().for_mode("single"))
    records = [json.loads(line) for line in Path(row["path"]).read_text().splitlines()]
    turns = [r for r in records if r["type"] == "turn"]
    said = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert said == [t["assistant"]["text"] for t in turns]
    assert msgs[-1]["tool_calls"][-1]["function"]["name"] == "submit"
    shown = [m for m in msgs if m["role"] == "tool"]
    assert len(shown) == head["counts"]["results_shown"] == sum(len(t["results"]) for t in turns[:-1])
    assert all(json.loads(m["content"])["ok"] for m in shown)


def _drop(path, taskset="d1-dev", audit=False) -> str:
    with pytest.raises(cv.Drop) as caught:
        cv.convert_episode(path, taskset, audit=audit)
    return caught.value.reason


def test_an_episode_that_does_not_score_100_is_dropped(tmp_path):
    result, path = _llm_episode(tmp_path, _task("stationing"),
                                FakeProvider([turn([("submit", {"note": "nothing"})])]))
    assert result.termination == "submit" and result.effective_score < 100.0
    assert _drop(path) == "score"
    assert cv.convert(path, "d1-dev").drop == "score"


def test_an_episode_that_changed_another_document_is_kept_only_if_it_scored_100_as_it_ended(tmp_path):
    """A revision made in the base drawing: what the sheet file had read of the
    base when is not all in the journal, so a replay can score 100 where the
    episode did not.  The conversation is kept on both scores, never the
    replay's alone."""
    entry = tasksets.load("d1-train-revise-base")["tasks"][0]
    task = tasksets.task_from_entry(entry)
    row = grounded.record_task(task, "vague", out_root=tmp_path)
    assert row["kept"]
    conv, _defs = cv.convert_episode(row["path"], "d1-train-revise-base")
    assert conv["header"]["score"]["effective"] == 100.0
    # the same file, its own score as it ended marked down: the journal still replays to 100
    path = Path(row["path"])
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert any(r["type"] == "journal" and r.get("opened") for r in records)
    for r in records:
        if r["type"] == "verify":
            r["effective_score"] = 0.0
    doctored = tmp_path / "doctored.jsonl"
    doctored.write_text("".join(json.dumps(r) + "\n" for r in records))
    assert _drop(doctored, "d1-train-revise-base") == "score"
    # an episode that opened no other document is still kept on its replay, as before
    plain = grounded.record_task(_task("layer-setup"), "vague", out_root=tmp_path)
    records = [json.loads(line) for line in Path(plain["path"]).read_text().splitlines()]
    for r in records:
        if r["type"] == "verify":
            r["effective_score"] = 0.0
    same = tmp_path / "plain-doctored.jsonl"
    same.write_text("".join(json.dumps(r) + "\n" for r in records))
    assert cv.convert_episode(same, "d1-dev")[0]["header"]["score"]["effective"] == 100.0


def test_the_audit_drops_the_plain_oracle(oracle_run):
    # the oracle's numbers are worked out off the page (training plan, step 2): ungrounded
    _, _, _, path = oracle_run
    assert _drop(path, audit=True) == "ungrounded"


@pytest.mark.parametrize("change, reason", [
    (lambda rs: rs[-1].update(termination="budget"), "not_submitted"),
    (lambda rs: rs[0].update(mode="vision"), "vision"),
    (lambda rs: rs[1]["assistant"].update(nudges=1), "nudged"),
    (lambda rs: rs[0].update(prompt_hash="sha256:" + "0" * 64), "prompt"),
    (lambda rs: next(r for r in rs if r["type"] == "journal")["truth"].update(task_id="other"), "truth"),
    (lambda rs: next(r for r in rs if r["type"] == "journal")["baseline"].update(extra=1), "start"),
    (lambda rs: rs[0].update(tools_sha256="sha256:" + "1" * 64), "tools"),
])
def test_an_episode_that_is_not_this_checkouts_task_or_tools_is_dropped(oracle_run, tmp_path, change, reason):
    _, _, _, path = oracle_run
    assert _drop(_rewrite(path, tmp_path / "changed.jsonl", change)) == reason


def test_a_task_the_manifest_does_not_hold_is_dropped(oracle_run):
    _, _, _, path = oracle_run
    assert _drop(path, taskset="d1-test") == "no_task"


def test_a_broken_file_is_counted_not_fatal(tmp_path):
    bad = tmp_path / "broken.jsonl"
    bad.write_text("{not json\n")
    assert cv.convert(bad, "d1-dev").drop == "error"


def test_the_cli_writes_a_set_tools_once_per_digest_and_the_card(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    index = grounded.record("d1-dev", src / "d1-dev-vague", level="vague",
                            types=["layer-setup", "create-alignment"])
    assert index["kept"] == 6
    summary = cv.run(["d1-dev"], ["vague"], source=src, out=out, log=lambda *_: None)
    tally = summary["sets"]["d1-dev-vague"]
    assert tally["kept"] == 6 and tally["dropped"] == {}
    assert tally["recorder"]["kept"] == 6 and tally["by_type"] == {"create-alignment": 3, "layer-setup": 3}
    lines = [json.loads(line) for line in (out / "d1-dev-vague.jsonl").read_text().splitlines()]
    assert [c["header"]["task_id"] for c in lines] == sorted(c["header"]["task_id"] for c in lines)
    assert all(c["header"]["git_commit"] == summary["git_commit"] for c in lines)
    tools = json.loads((out / "tools.json").read_text())
    # create-alignment is shown create_alignment, layer-setup is not: two tool sets, each kept once
    assert set(tools) == {c["header"]["tools_sha256"] for c in lines} and len(tools) == 2
    for dig, row in tools.items():
        assert cv.tools_sha256(row["definitions"]) == dig
        assert [t["function"]["name"] for t in row["function_tools"]] == row["names"]

    card = cv.card(out, tmp_path / "CARD.md").read_text()
    assert "| `d1-dev` |" in card and "Not counted yet" in card
    counts = {c["id"]: [30000 + 1000 * i, 28000, 500] for i, c in enumerate(lines)}
    (out / "tokens.json").write_text(json.dumps({
        "tokenizer": {"description": "a test tokenizer"}, "template": {"description": "a template"},
        "calibration": {"text": "Counted against the server."}, "conversations": counts}))
    card = cv.card(out, tmp_path / "CARD.md").read_text()
    assert "Counted against the server." in card and "Not counted yet" not in card
    assert "30k-32k" in card and "6 conversations" in card


def test_the_histogram_bins_by_thousands_and_drops_empty_ends():
    rows = cv.histogram([27000, 29000, 29500, 41000], (0, 26000, 28000, 30000, 40000, 48000))
    assert rows == [("26k-28k", 1), ("28k-30k", 2), ("30k-40k", 0), ("40k-48k", 1)]
    assert cv.histogram([], (0, 1000)) == []


# ------------------------------------------------------------ the token counter

def _tokens_script():
    spec = importlib.util.spec_from_file_location("training_tokens", REPO / "scripts" / "training_tokens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Words:
    """A tokenizer that counts words: enough to check the bookkeeping."""
    class _Enc:
        def __init__(self, text):
            self.ids = text.split()

    def encode(self, text, add_special_tokens=False):
        return self._Enc(text)

    def encode_batch(self, texts, add_special_tokens=False):
        return [self._Enc(t) for t in texts]


def test_the_token_counter_splits_at_the_chat_markers_and_adds_up():
    tt = _tokens_script()
    text = ("<|im_start|>system\na b c<|im_end|>\n<|im_start|>user\nd e<|im_end|>\n"
            "<|im_start|>assistant\nf g h i<|im_end|>\n<|im_start|>user\n<tool_response>\nj\n"
            "</tool_response><|im_end|>\n<|im_start|>assistant\nk<|im_end|>\n")
    counter = tt.Counter(_Words())
    blocks = counter.blocks(text)
    assert [r for r, _ in blocks] == ["system", "user", "assistant", "user", "assistant"]
    assert sum(n for _, n in blocks) == len(text.split())

    class Template:
        def render(self, **_):
            return text
    total, prompt, assistant = tt.count_conversation(counter, Template(), {"messages": []}, [])
    assert total == len(text.split())
    assert prompt == dict(blocks[:1])["system"] + blocks[1][1]
    assert assistant == blocks[2][1] + blocks[4][1]


def test_the_calibration_fit_recovers_a_linear_gap():
    tt = _tokens_script()
    xs = [[c, a, 1.0] for c in range(1, 6) for a in range(0, 12, 3)]
    ys = [2.0 * c + 2.5 * a + 20 for c, a, _ in xs]
    assert [round(v, 6) for v in tt.least_squares(xs, ys)] == [2.0, 2.5, 20.0]

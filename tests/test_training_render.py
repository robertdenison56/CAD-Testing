"""The T1 smoke's training text: what the trainer feeds the model, against
what the serving engine sends (scripts/training_render.py, the trainer's
data path in scripts/training_lora.py).

No GPU, no jinja2, no tokenizers: the renders come from a fixture recorded
with transformers' ``apply_chat_template`` on Qwen3.5-9B's own template and
the prompts LM Studio's llama.cpp engine served for the same requests
(tests/fixtures/training_render_fixture.json), and tokens are characters.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((REPO / "tests" / "fixtures" / "training_render_fixture.json").read_text(encoding="utf-8"))


def _script(name):
    if str(REPO / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module     # a dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


tr = _script("training_render")
MSGS = FIXTURE["messages"]
TURNS = tr.assistant_indices(MSGS)          # 2, 4 (weight 0), 6, 10 (after the [harness] note)
NOTE = next(i for i, m in enumerate(MSGS) if m["role"] == "user" and m["content"].startswith("[harness]"))


def render(thinking):
    table = FIXTURE["renders"][thinking]
    return lambda messages, gen: table[f"{len(messages)}|{int(gen)}"]


def chars(text):
    """A tokenizer whose tokens are characters."""
    return [ord(c) for c in text], [(i, i + 1) for i in range(len(text))]


@pytest.mark.parametrize("thinking", ["off", "on"])
def test_the_template_engines_agree_on_every_request(thinking):
    # what the trainer renders before each turn is what LM Studio's engine served for that request
    for i in TURNS:
        assert render(thinking)(MSGS[:i], True) == FIXTURE["served"][thinking][str(i)]


@pytest.mark.parametrize("thinking", ["off", "on"])
def test_every_turn_is_trained_after_exactly_the_prompt_it_was_served(thinking):
    plan = tr.plan_segments(MSGS, render(thinking))
    held = {i: s for s in plan.segments for i in s.turns + s.masked}
    assert sorted(held) == TURNS and not plan.inconsistent
    for i in TURNS:
        assert held[i].text.startswith(FIXTURE["served"][thinking][str(i)])


def test_the_harness_note_splits_off_the_turns_before_it():
    # the note is a user message: in the whole conversation's render the turns before it lose their think
    # block, which the model had in its context when it wrote them
    whole = render("off")(MSGS, False)
    before = [i for i in TURNS if i < NOTE]
    assert all(not whole.startswith(FIXTURE["served"]["off"][str(i)]) for i in before)
    plan = tr.plan_segments(MSGS, render("off"))
    assert len(plan.segments) == 2
    first, last = plan.segments
    assert sorted(first.turns + first.masked) == before and last.turns == [i for i in TURNS if i > NOTE]
    assert last.text == whole


def test_the_targets_are_the_turns_text_and_calls_through_im_end():
    plan = tr.plan_segments(MSGS, render("off"))
    for seg in plan.segments:
        for (a, b), i in zip(seg.spans, seg.turns):
            target = seg.text[a:b]
            assert target.endswith(tr.IM_END) and "<think>" not in target
            assert target.startswith((MSGS[i]["content"] or "<tool_call>")[:20])
            # the next turn's prompt picks up right after this <|im_end|>
            assert seg.text[b:b + 1] == "\n"


def test_thinking_on_trains_the_close_of_the_think_block():
    plan = tr.plan_segments(MSGS, render("on"))
    seg = plan.segments[-1]
    a, b = seg.spans[-1]
    assert seg.text[a:b].startswith("\n</think>\n\n")


def test_a_weight_0_turn_is_context_and_never_a_target():
    plan = tr.plan_segments(MSGS, render("off"))
    broken = next(i for i in TURNS if MSGS[i].get("weight") == 0)
    seg = next(s for s in plan.segments if broken in s.masked)
    assert broken not in seg.turns
    ids, labels = tr.labels_for(seg.text, seg.spans, chars)
    trained = "".join(chr(t) for t, lab in zip(ids, labels) if lab != tr.IGNORE)
    call = '<parameter=text>\nTrue\n</parameter>'      # the broken call's own argument
    assert call in seg.text and call not in trained
    assert "The design is BASE:ALIGN-1" in trained     # the recovery is trained


def test_labels_are_exactly_the_spans():
    text = "abcdefghij"
    ids, labels = tr.labels_for(text, [(2, 4), (7, 10)], chars)
    assert "".join(chr(x) for x in labels if x != tr.IGNORE) == "cdhij"
    # a token straddling a span's start is context
    ids, labels = tr.labels_for("abcdef", [(1, 4)], lambda t: ([1, 2, 3], [(0, 2), (2, 4), (4, 6)]))
    assert labels == [tr.IGNORE, 2, tr.IGNORE]


def test_a_rendered_turn_reads_back_to_the_recorded_calls():
    plan = tr.plan_segments(MSGS, render("off"))
    for seg in plan.segments:
        for (a, b), i in zip(seg.spans, seg.turns):
            back = tr.parse_completion(seg.text[a:b], FIXTURE["tools"])
            want = [(c["function"]["name"], c["function"]["arguments"]) for c in MSGS[i]["tool_calls"]]
            assert [(c["name"]) for c in back["tool_calls"]] == [w[0] for w in want]
            for got, (_, args) in zip(back["tool_calls"], want):
                assert tr.same_value(got["arguments"], args), (got, args)
            assert back["content"] == MSGS[i]["content"].strip()


def test_python_literals_come_back_as_json_and_strings_stay_strings():
    # the template writes a scalar with Python's str() (True, None, 1250.0) and a list or object with tojson
    done = ("<tool_call>\n<function=place_label>\n<parameter=text>\nTrue\n</parameter>\n"
            '<parameter=style>\n{"bold": false, "note": null}\n</parameter>\n'
            "<parameter=station>\n1250.0\n</parameter>\n</function>\n</tool_call>\n"
            "<tool_call>\n<function=list_alignments>\n<parameter=include_references>\nFalse\n</parameter>\n"
            "</function>\n</tool_call><|im_end|>")
    calls = tr.parse_completion(done, FIXTURE["tools"])["tool_calls"]
    assert calls[0]["arguments"] == {"text": "True", "style": {"bold": False, "note": None}, "station": 1250.0}
    assert calls[1]["arguments"] == {"include_references": False}


def test_requests_carry_no_weight_and_string_arguments():
    sent = tr.strip_for_request(MSGS)
    assert all("weight" not in m for m in sent)
    for m in sent:
        for c in m.get("tool_calls") or []:
            assert isinstance(c["function"]["arguments"], str)
            json.loads(c["function"]["arguments"])
    assert MSGS[4]["weight"] == 0 and isinstance(MSGS[2]["tool_calls"][0]["function"]["arguments"], dict)


def test_same_value_takes_1_and_1_0_alike_but_not_true_and_1():
    assert tr.same_value({"a": [1, 2.0]}, {"a": [1.0, 2]})
    assert not tr.same_value(True, 1) and not tr.same_value({"a": 1}, {"a": 1, "b": None})


def test_the_nothink_template_always_closes_the_think_block():
    base = "{%- if add_generation_prompt %}\n    {{- '<|im_start|>assistant\\n' }}\n" + tr.GENERATION_SWITCH + "{%- endif %}"
    patched = tr.nothink_template(base)
    assert "enable_thinking" not in patched and tr.GENERATION_CLOSED in patched
    with pytest.raises(ValueError):
        tr.nothink_template(patched)


def test_the_fixture_was_rendered_from_the_checked_template():
    lora = _script("training_lora")
    assert lora.TEMPLATE_SHA256 in FIXTURE["about"]


def test_the_smoke_takes_the_longest_first_then_spreads_over_the_files():
    lora = _script("training_lora")
    convs = [{"id": f"{f}-{k}", "_file": f} for f in ("a.jsonl", "b.jsonl", "c.jsonl") for k in range(30)]
    lengths = {c["id"]: [1000 + n] for n, c in enumerate(convs)}
    pick = lora.smoke_pick(convs, lengths, n=50, longest=5)
    assert len(pick) == 50 and len({c["id"] for c in pick}) == 50
    assert [c["id"] for c in pick[:5]] == [f"c.jsonl-{k}" for k in (29, 28, 27, 26, 25)]
    counts = {f: sum(c["_file"] == f for c in pick[5:]) for f in ("a.jsonl", "b.jsonl", "c.jsonl")}
    assert max(counts.values()) - min(counts.values()) <= 1


def test_the_lora_targets_are_the_language_models_projections():
    import re
    lora = _script("training_lora")
    pat = re.compile(lora.TARGETS)
    hit = ["model.layers.3.self_attn.q_proj", "model.language_model.layers.0.linear_attn.in_proj_qkv",
           "model.layers.7.mlp.down_proj", "model.layers.0.linear_attn.out_proj"]
    miss = ["model.visual.blocks.0.attn.qkv", "lm_head", "model.layers.0.linear_attn.in_proj_a",
            "model.visual.blocks.3.mlp.linear_fc1"]
    assert all(pat.fullmatch(n) for n in hit) and not any(pat.fullmatch(n) for n in miss)

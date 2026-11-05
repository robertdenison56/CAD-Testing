"""The LLM agents (eval plan sections 4.2, 4.4, 4.5): the agent, the
providers, the system prompts and the price table.

Every test runs on the fake provider or on a provider whose HTTP is a stub:
nothing here touches the network.  The fake oracle -- the reference solution
replayed as model turns through the whole LLM stack -- scores 100, which is
the E3 counterpart of E2's oracle-through-the-loop test."""
from __future__ import annotations

import json

import pytest

from roaddraft.eval import prices, prompts
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import LLMAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import EpisodeConfig, run_episode
from roaddraft.eval.providers import FakeProvider, Turn, infer, make
from roaddraft.eval.providers.anthropic import AnthropicProvider, parse_reply
from roaddraft.eval.providers.fake import turn
from roaddraft.eval.providers.openai_compat import OpenAICompatProvider
from roaddraft.eval.runner import RunSpec, matrix, run
from roaddraft.eval.tools import DIALECTS, allowed_names
from roaddraft.eval.trajectory import read_episode

DEV = tasksets.load("d1-dev")["tasks"]


def _task(i: int = 0):
    return tasksets.task_from_entry(DEV[i])


def _good_layer():
    return ("create_layer", {"name": "rd_TEST", "color": "black"})


# ------------------------------------------------------------------ the loop


@pytest.mark.parametrize("dialect", DIALECTS)
def test_fake_oracle_through_the_llm_stack_scores_100(dialect):
    for i in range(0, 50, 7):     # every task type, one and two sheets
        r = run_episode(_task(i), LLMAgent(FakeProvider.oracle()), EpisodeConfig(dialect=dialect))
        assert r.termination == "submit", (DEV[i]["task_id"], dialect, r.error)
        assert r.effective_score == 100.0 and r.faults == 0 and r.invalid_calls == 0, DEV[i]["task_id"]


def test_the_first_request_carries_the_system_prompt_the_brief_and_the_tools():
    provider = FakeProvider([turn([("submit", {})])])
    agent = LLMAgent(provider)
    run_episode(_task(1), agent, EpisodeConfig(mode="single"))
    req = provider.requests[0]
    assert req["system"] == prompts.system_prompt("neutral", "single")
    assert req["transcript"] == [{"role": "user", "text": req["transcript"][0]["text"]}]
    assert "THE TASK:" in req["transcript"][0]["text"]
    assert "submit" in req["tools"] and "run_check" not in req["tools"]
    assert req["tools"] == sorted(req["tools"])


def test_results_go_back_in_order_with_the_teaching_error_and_count_as_invalid(tmp_path):
    provider = FakeProvider([
        turn([_good_layer(), ("create_layer", {"nmae": "oops"}), ("no_such_tool", {})]),
        turn([("submit", {"note": "done"})]),
    ])
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig(), out_root=tmp_path)
    assert r.termination == "submit" and r.steps == 4 and r.invalid_calls == 2 and r.faults == 2
    results = provider.requests[1]["transcript"][-1]
    assert results["role"] == "results"
    assert [x["id"] for x in results["results"]] == ["call_0", "call_1", "call_2"]
    assert [x["is_error"] for x in results["results"]] == [False, True, True]
    bad = json.loads(results["results"][1]["content"])
    assert bad["error"]["type"] == "invalid_params" and "example" in json.dumps(bad["error"])
    unknown = json.loads(results["results"][2]["content"])
    assert unknown["error"]["type"] == "unknown_command"
    rec = read_episode(r.path)
    assert rec["end"]["invalid_calls"] == 2 and rec["end"]["tool_calls"] == 4
    assert rec["header"]["provider"] == "fake" and rec["header"]["prompt_sha256"].startswith("sha256:")
    assert rec["turns"][1]["assistant"]["text"] == "done"


def test_a_turn_without_calls_is_an_implicit_submit(tmp_path):
    provider = FakeProvider([turn([_good_layer()]), turn(text="All done, the sheet is drafted.")])
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig(), out_root=tmp_path)
    assert r.termination == "submit" and r.implicit_submit and r.steps == 1
    rec = read_episode(r.path)
    assert rec["end"]["implicit_submit"] is True
    last = rec["turns"][-1]["assistant"]
    assert last["implicit_submit"] is True and last["text"] == "All done, the sheet is drafted."


def test_a_refusal_ends_the_episode_as_a_refusal_with_its_usage(tmp_path):
    refused = Turn(stop="refusal", stop_detail="refusal: cyber", usage={"output_tokens": 7})
    r = run_episode(_task(1), LLMAgent(FakeProvider([turn([_good_layer()]), refused])),
                    EpisodeConfig(), out_root=tmp_path)
    assert r.termination == "refusal" and "cyber" in r.error
    assert r.usage_total["output_tokens"] == 7
    rec = read_episode(r.path)
    assert rec["turns"][-1]["assistant"]["stop"] == "refusal"


def test_cut_off_without_a_call_is_nudged_then_ends_as_an_output_limit_budget():
    cut = Turn(stop="max_tokens", text="Let me think", raw={"text": "Let me think"})
    provider = FakeProvider([cut, turn([("submit", {})])])
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig())
    assert r.termination == "submit"
    nudge = provider.requests[1]["transcript"][-1]
    assert nudge["role"] == "user" and "output limit" in nudge["text"]
    stuck = run_episode(_task(1), LLMAgent(FakeProvider([cut, cut, cut, cut])), EpisodeConfig())
    assert stuck.termination == "budget" and stuck.budget_tripped == "output_limit"


def test_usage_counts_against_the_output_token_budget():
    provider = FakeProvider([turn([_good_layer()], usage={"output_tokens": 600})] * 5)
    r = run_episode(_task(1), LLMAgent(provider),
                    EpisodeConfig(budgets=Budgets(output_tokens=1000)))
    assert r.termination == "budget" and r.budget_tripped == "output_tokens"
    assert r.usage_total["output_tokens"] == 1200 and r.turns == 2


def test_low_steps_put_a_harness_note_on_the_results():
    provider = FakeProvider([turn([_good_layer()])] * 3 + [turn([("submit", {})])])
    run_episode(_task(1), LLMAgent(provider), EpisodeConfig(budgets=Budgets(steps=16)))
    note = provider.requests[1]["transcript"][-1]["note"]
    assert note.startswith("[harness] 15 steps left")


def test_cost_is_summed_per_turn_from_the_price_table(tmp_path):
    usage = {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 20000,
             "cache_creation_input_tokens": 3000}
    provider = FakeProvider([turn([_good_layer()], usage=usage), turn([("submit", {})], usage=usage)],
                            model="claude-haiku-4-5")
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig(), out_root=tmp_path)
    one = (1000 * 1.0 + 500 * 5.0 + 20000 * 0.1 + 3000 * 1.25) / 1e6
    assert r.cost_usd == pytest.approx(2 * one)
    end = read_episode(r.path)["end"]
    assert end["cost_usd"] == pytest.approx(2 * one) and end["prices_checked"] == prices.load()["checked"]
    unpriced = run_episode(_task(1), LLMAgent(FakeProvider([turn([("submit", {})], usage=usage)],
                                                           model="qwen/qwen3.5-9b")), EpisodeConfig())
    assert unpriced.cost_usd is None


def test_vision_mode_returns_the_render_as_an_image_and_keeps_it_out_of_the_trajectory(tmp_path):
    task = _task(1)
    sheet = task.brief.deliverable["sheets"][0]["name"]
    provider = FakeProvider([turn([("render_sheet", {"sheet": sheet})]), turn([("submit", {})])])
    r = run_episode(task, LLMAgent(provider), EpisodeConfig(mode="vision"), out_root=tmp_path)
    assert r.termination == "submit" and r.faults == 0
    sent = provider.requests[1]["transcript"][-1]["results"][0]
    assert sent["images"] and sent["images"][0][0] == "image/png" and len(sent["images"][0][1]) > 1000
    assert "base64" not in sent["content"]
    assert "base64" not in r.path and "base64" not in open(r.path).read()
    text_only = FakeProvider([turn([("render_sheet", {"sheet": sheet})]), turn([("submit", {})])])
    run_episode(task, LLMAgent(text_only), EpisodeConfig(mode="self_correct"))
    assert text_only.requests[1]["transcript"][-1]["results"][0]["images"] == []


# ------------------------------------------------------------------ dialects


def test_no_episode_renames_the_tools():
    # Robert, 2026-10-30: the eval tests readiness for RoadDraft itself, so the
    # tools always carry their own names; neutral is the only dialect
    assert DIALECTS == ("neutral",)
    with pytest.raises(ValueError):
        EpisodeConfig(dialect="c3d")
    provider = FakeProvider([turn([("nope", {})]), turn([("submit", {})])])
    run_episode(_task(1), LLMAgent(provider), EpisodeConfig(mode="self_correct"))
    assert set(provider.requests[0]["tools"]) == allowed_names("self_correct", _task(1).truth.scope)
    err = json.loads(provider.requests[1]["transcript"][-1]["results"][0]["content"])
    assert "place_text" in err["error"]["hint"]


# ------------------------------------------------------------------- prompts


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("mode", ["single", "self_correct", "vision"])
def test_system_prompts_fill_every_placeholder(dialect, mode):
    text = prompts.system_prompt(dialect, mode, Budgets(steps=77, faults=5).for_mode(mode))
    assert "$" not in text and "77 steps" in text and "5 turns in a row" in text and "submit" in text
    if mode == "single":
        assert "no run_check" in text
    else:
        assert "3 times" in text


# ----------------------------------------------------------------- providers


def _anthropic_reply(content, stop="tool_use", usage=None, **extra):
    return {"content": content, "stop_reason": stop,
            "usage": usage or {"input_tokens": 10, "output_tokens": 5}, **extra}


def test_anthropic_request_shape():
    bodies = []
    replies = iter([
        _anthropic_reply([{"type": "thinking", "thinking": "plan", "signature": "s"},
                          {"type": "tool_use", "id": "tu1", "name": "create_layer",
                           "input": {"name": "rd_TEST", "color": "black"}}]),
        _anthropic_reply([{"type": "text", "text": "done"}], stop="end_turn"),
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        return next(replies)

    provider = AnthropicProvider("claude-opus-5-5", post=post)
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig())
    assert r.termination == "submit" and r.implicit_submit and r.steps == 1
    first, second = bodies
    assert first["model"] == "claude-opus-5-5" and first["max_tokens"] == 16000
    assert first["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert first["output_config"] == {"effort": "high"}
    assert first["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in first and "fallbacks" not in first and "temperature" not in first
    assert all(set(t) == {"name", "description", "input_schema"} for t in first["tools"])
    assert [t["name"] for t in first["tools"]] == sorted(t["name"] for t in first["tools"])
    # append-only: the second request starts with the first one's messages
    assert second["messages"][:1] == first["messages"]
    assert second["messages"][1]["content"][0] == {"type": "thinking", "thinking": "plan", "signature": "s"}
    result = second["messages"][2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu1" and "is_error" not in result


def test_anthropic_model_rules():
    def body(model, **kw):
        return AnthropicProvider(model, post=lambda b: b, **kw).request("s", [{"role": "user", "text": "x"}], [])
    haiku = body("claude-haiku-4-5")
    assert "thinking" not in haiku and "output_config" not in haiku
    assert body("claude-opus-4-6")["thinking"] == {"type": "adaptive"}
    assert body("claude-sonnet-5-5", effort="medium")["output_config"] == {"effort": "medium"}


def test_strict_marks_only_the_closed_schemas():
    from roaddraft.api.session import Session
    from roaddraft.eval.providers.anthropic import api_tools, closed
    from roaddraft.eval.tools import tool_definitions
    defs = tool_definitions(Session().manifest(), "single")
    tools = {t["name"]: t for t in api_tools(defs, strict=True)}
    assert tools["create_layer"]["strict"] is True
    assert "strict" not in tools["fill_title_block"] and "strict" not in tools["modify_entity"]
    assert sum("strict" in t for t in tools.values()) == sum(closed(d["input_schema"]) for d in defs)
    assert not any("strict" in t for t in api_tools(defs))


def test_anthropic_reply_parsing_and_refusal():
    t = parse_reply(_anthropic_reply(
        [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "a", "name": "undo", "input": {}}],
        usage={"input_tokens": 3, "output_tokens": 4, "cache_read_input_tokens": 100,
               "cache_creation_input_tokens": 50}))
    assert t.stop == "tool_use" and t.text == "hi" and t.calls[0].name == "undo"
    assert t.usage == {"input_tokens": 3, "output_tokens": 4, "cache_read_input_tokens": 100,
                       "cache_creation_input_tokens": 50}
    refused = parse_reply(_anthropic_reply([], stop="refusal",
                                           stop_details={"category": "cyber", "explanation": "no"}))
    assert refused.stop == "refusal" and refused.stop_detail == "refusal: cyber: no"
    assert parse_reply(_anthropic_reply([], stop="max_tokens")).stop == "max_tokens"


def test_openai_compat_request_reply_and_unparsed_arguments():
    bodies = []
    replies = iter([
        {"choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "hmm",
                                  "tool_calls": [{"id": "c1", "type": "function", "function": {
                                      "name": "create_layer", "arguments": "{not json"}}]},
                      "finish_reason": "tool_calls"}],
         "usage": {"prompt_tokens": 1000, "completion_tokens": 30,
                   "prompt_tokens_details": {"cached_tokens": 800}}},
        {"choices": [{"message": {"role": "assistant", "content": "finished"},
                      "finish_reason": "stop"}], "usage": {"prompt_tokens": 1100, "completion_tokens": 5}},
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        return next(replies)

    provider = OpenAICompatProvider("qwen/qwen3.5-9b", post=post)
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig())
    assert r.termination == "submit" and r.invalid_calls == 1
    assert r.usage_total["input_tokens"] == 200 + 1100 and r.usage_total["cache_read_input_tokens"] == 800
    first, second = bodies
    assert first["messages"][0]["role"] == "system" and first["messages"][1]["role"] == "user"
    assert first["tools"][0]["type"] == "function"
    assistant, tool = second["messages"][2], second["messages"][3]
    assert assistant["tool_calls"][0]["id"] == "c1" and "reasoning_content" not in assistant
    assert tool["role"] == "tool" and tool["tool_call_id"] == "c1"
    assert json.loads(tool["content"])["error"]["type"] == "invalid_params"


def test_provider_inference_and_construction():
    assert infer("claude-haiku-4-5") == "anthropic" and infer("fake-oracle") == "fake"
    assert infer("google/gemma-4-e4b") == "openai"
    assert make("fake-oracle").oracle_mode
    p = make("google/gemma-4-e4b", base_url="http://x/v1", strict=False, max_tokens=None)
    assert isinstance(p, OpenAICompatProvider) and p.base_url == "http://x/v1"


# -------------------------------------------------------------------- prices


def test_price_table_rates_and_tiers():
    table = prices.load()
    assert table["checked"] and "claude-opus-5-5" in table["models"]
    assert prices.rates("claude-opus-5-5")["cache_read"] == 0.2
    assert prices.rates("claude-sonnet-5-5")["cache_write"] == pytest.approx(2.5)
    assert prices.cost_usd("claude-fable-5-1", {"output_tokens": 1_000_000}) == 50.0
    small = prices.cost_usd("claude-haiku-5-5", {"input_tokens": 50_000, "output_tokens": 1000})
    big = prices.cost_usd("claude-haiku-5-5", {"input_tokens": 150_000, "output_tokens": 1000})
    assert small == pytest.approx((50_000 * 0.1 + 1000 * 0.5) / 1e6)
    assert big == pytest.approx((150_000 * 0.5 + 1000 * 2.5) / 1e6)
    assert prices.cost_usd("local-model", {"input_tokens": 5}) is None
    assert prices.episode_cost("claude-haiku-5-5", [{"input_tokens": 50_000}, {"input_tokens": 150_000}]) \
        == pytest.approx(small - 1000 * 0.5 / 1e6 + big - 1000 * 2.5 / 1e6)


# -------------------------------------------------------------------- runner


def test_runner_runs_models(tmp_path):
    spec = RunSpec(taskset="d1-dev", agents=(), models=("fake-oracle",),
                   limit=2, results_root=str(tmp_path), run_id="m", concurrency=2)
    assert len(matrix(spec)) == 2
    summary = run(spec)
    assert summary["episodes"] == 2 and not summary["failures"]
    assert summary["groups"]["fake-oracle|explicit|single"]["mean_effective"] == 100.0
    files = sorted((tmp_path / "m" / "episodes").glob("*.jsonl"))
    assert len(files) == 2 and all(".neutral." in f.name for f in files)


def test_the_cost_cap_stops_new_episodes(tmp_path):
    usage = {"input_tokens": 100_000, "output_tokens": 10_000}   # $0.15 a turn on Haiku 4.5

    def factory(name, spec):
        return LLMAgent(FakeProvider([turn([("submit", {})], usage=usage)], model="claude-haiku-4-5"))

    spec = RunSpec(taskset="d1-dev", agents=("claude-haiku-4-5",), limit=5, results_root=str(tmp_path),
                   run_id="cap", concurrency=1, cost_cap=0.25)
    summary = run(spec, agent_factory=factory)
    assert summary["stopped"] == "cost_cap" and summary["episodes"] == 2 and summary["not_run"] == 3
    assert summary["spent_usd"] == pytest.approx(0.30)
    again = run(spec, agent_factory=factory)
    assert again["stopped"] == "cost_cap" and again["skipped"] == 2 and again["not_run"] == 3


def test_cli_runs_a_model_and_fails_fast_without_credentials(tmp_path, capsys, monkeypatch):
    from roaddraft.eval.__main__ import main
    assert main(["run", "--taskset", "d1-dev", "--model", "fake-oracle", "--limit", "2",
                 "--out", str(tmp_path), "--run-id", "cli", "--concurrency", "1"]) == 0
    assert "effective 100.00" in capsys.readouterr().out
    assert main(["run", "--taskset", "d1-dev", "--model", "claude-haiku-4-5", "--limit", "2",
                 "--dry-run", "--cost-cap", "5"]) == 0
    out = capsys.readouterr().out
    assert "2 episodes" in out and "cost cap $5.00" in out
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert main(["run", "--taskset", "d1-dev", "--model", "claude-haiku-4-5", "--limit", "1",
                 "--out", str(tmp_path)]) == 2
    assert "no Anthropic credentials" in capsys.readouterr().err
    assert not (tmp_path / "episodes").exists()


# --------------------------------------------------------- the context budget


def test_reset_clears_the_conversation():
    provider = FakeProvider([turn([("submit", {})])])
    agent = LLMAgent(provider)
    run_episode(_task(1), agent, EpisodeConfig())
    assert agent.transcript and agent.tools
    agent.reset(_task(1), "explicit", "single")
    assert agent.transcript == [] and agent.tools == [] and agent.context_floor() == 0


def test_message_size_counts_what_goes_back_to_the_model():
    from roaddraft.eval.agents.llm import message_size
    assert message_size({"role": "user", "text": "abcd"}) == (4, 0)
    chars, images = message_size({"role": "assistant", "text": "hi", "raw": {"thinking": "x" * 1000},
                                  "calls": [{"id": "c", "name": "n", "params": {"a": 1}}]})
    assert 2 < chars < 100 and images == 0          # the thinking is not sent back
    results = {"role": "results", "note": "n", "results": [
        {"id": "c", "name": "render_sheet", "content": "{}", "is_error": False,
         "images": [("image/png", "A" * 100000)]}]}
    assert message_size(results) == (1 + 2 + len("render_sheet"), 1)   # an image is not characters


def test_a_reply_past_the_context_budget_ends_the_episode_before_its_calls_run(tmp_path):
    provider = FakeProvider([
        turn([_good_layer()], usage={"input_tokens": 400, "cache_read_input_tokens": 100,
                                     "output_tokens": 10}),
        turn([("create_layer", {"name": "rd_NEVER", "color": "black"})],
             usage={"input_tokens": 1000, "output_tokens": 10}),
    ])
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig(budgets=Budgets(context_tokens=1000)),
                    out_root=tmp_path)
    assert r.termination == "budget" and r.budget_tripped == "context" and r.steps == 1
    assert "1000 tokens" in r.error and len(provider.requests) == 2
    turns = read_episode(r.path)["turns"]
    assert turns[-1]["assistant"]["tool_calls"] == [] and turns[-1]["usage"]["input_tokens"] == 1000
    # the same conversation with no budget runs on
    provider = FakeProvider([
        turn([_good_layer()], usage={"input_tokens": 400, "output_tokens": 10}),
        turn([("submit", {})], usage={"input_tokens": 1000, "output_tokens": 10}),
    ])
    assert run_episode(_task(1), LLMAgent(provider), EpisodeConfig()).termination == "submit"


def test_a_next_request_that_cannot_fit_is_not_sent():
    big = "x" * 9000                                 # at least 2,000 tokens by the floor
    provider = FakeProvider([
        turn([_good_layer()], text=big, usage={"input_tokens": 500, "output_tokens": 2000}),
        turn([("submit", {})]),
    ])
    r = run_episode(_task(1), LLMAgent(provider), EpisodeConfig(budgets=Budgets(context_tokens=2000)))
    assert r.termination == "budget" and r.budget_tripped == "context" and r.steps == 1
    assert len(provider.requests) == 1 and "at least" in r.error
    # a reply with no prompt count (an estimated usage) leaves the floor where it was
    agent = LLMAgent(FakeProvider([turn([_good_layer()], usage={"output_tokens": 5})]))
    run_episode(_task(1), agent, EpisodeConfig())
    assert agent.context_floor() == 0


def test_chat_messages_carry_images_as_data_urls_after_the_tool_messages():
    from roaddraft.eval.providers.openai_compat import chat_messages
    transcript = [
        {"role": "user", "text": "look"},
        {"role": "assistant", "text": "", "calls": [], "raw": {"role": "assistant", "content": "",
                                                            "tool_calls": [{"id": "c1"}]}},
        {"role": "results", "note": "[harness] 3 steps left.", "results": [
            {"id": "c1", "name": "view_attachment", "content": "{\"ok\":true}", "is_error": False,
             "images": [("image/png", "QUJD")]}]},
    ]
    msgs = chat_messages("sys", transcript)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "user"]
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "name": "view_attachment",
                       "content": "{\"ok\":true}"}
    parts = msgs[4]["content"]
    assert parts[0] == {"type": "text", "text": "[harness] 3 steps left."}
    assert parts[1] == {"type": "text", "text": "The image(s) from the calls above:"}
    assert parts[2] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    # no image, no note: the tool messages alone
    transcript[2]["results"][0]["images"], transcript[2]["note"] = [], None
    assert [m["role"] for m in chat_messages("sys", transcript)] == ["system", "user", "assistant", "tool"]


def test_the_cli_context_budget_defaults_to_the_lms_context():
    import argparse
    from roaddraft.eval.__main__ import _budgets

    def args(**kw):
        base = dict(taskset="d1-dev", steps=None, wall_clock=None, output_tokens=None,
                    context_tokens=None, lms_context=None)
        return argparse.Namespace(**dict(base, **kw))
    assert _budgets(args()).context_tokens is None
    assert _budgets(args(lms_context=131072)).context_tokens == 131072
    assert _budgets(args(lms_context=131072, context_tokens=65536)).context_tokens == 65536
    assert _budgets(args(taskset="hard-pilots", lms_context=131072)).steps == 600


def test_a_stalled_turn_is_a_turn_time_limit_with_the_stall_in_its_message():
    """The backend's stall guard (runners.openai_compat) gives a turn up as ``turn_limit`` with ``stalled``
    beside it; the provider ends the episode as a turn_time budget trip that says so."""
    from roaddraft.eval.providers.base import LimitReached
    from roaddraft.eval.providers.openai_compat import parse_reply as parse_openai
    plain = {"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "turn_limit"}]}
    with pytest.raises(LimitReached, match="ran past the provider's turn limit") as info:
        parse_openai(plain)
    assert info.value.limit == "turn_time"
    stalled = dict(plain, usage={"completion_tokens": 0, "estimated": True},
                   stalled={"seconds": 300.5, "chunks": 1200, "reloaded": True})
    with pytest.raises(LimitReached, match=r"carried nothing for 300 s \(1200 empty chunks\), before and after a reload") as info:
        parse_openai(stalled)
    assert info.value.limit == "turn_time"
    stalled["stalled"]["reloaded"] = False
    with pytest.raises(LimitReached, match=r"1200 empty chunks\)$"):
        parse_openai(stalled)
    # 2026-11-04: a stream that sent no chunk at all (the read timed out) names that, not a chunk count
    silent = dict(plain, stalled={"seconds": 300.0, "chunks": 0, "reloaded": True, "silent": True})
    with pytest.raises(LimitReached, match=r"sent no chunk for 300 s, before and after a reload") as info:
        parse_openai(silent)
    assert info.value.limit == "turn_time"


def test_a_hosted_endpoints_proxy_cut_and_context_refusal_are_budget_stops_not_errors():
    """Runpod's proxy ends a streamed turn at 570 s (Gemma 4 12B lost 10 of 100 d1-variance episodes to it as
    errors, 2026-10-20) and vLLM refuses a prompt past its window with an HTTP 400: the provider ends the
    episode as the turn_time and context stops they are. Any other error stays an error."""
    from roaddraft.eval.providers.base import LimitReached
    from roaddraft.eval.providers.openai_compat import OpenAICompatProvider, hosted_limit

    cut = 'stream error: {"message": "stream did not complete within 570 seconds", "type": "timeout_error"}'
    refused = ("HTTP 400: {\"object\":\"error\",\"message\":\"This model's maximum context length is 131072 tokens. "
               "However, you requested 140210 tokens in the messages.\"}")
    assert hosted_limit(cut)[0] == "turn_time"
    assert "570 seconds" in hosted_limit(cut)[1]
    assert hosted_limit(refused)[0] == "context"
    assert hosted_limit('HTTP 400: {"error":"exceed_context_size_error"}')[0] == "context"
    assert hosted_limit("HTTP 400: tool_choice is not supported") is None
    assert hosted_limit("HTTP 500: did not complete within the deadline") is None   # not a stream error
    assert hosted_limit("stream error: unexpected tokens remaining in message header") is None

    def post_with(text):
        def post(body):
            raise RuntimeError(text)
        return post

    for text, limit in ((cut, "turn_time"), (refused, "context")):
        p = OpenAICompatProvider("m", base_url="http://x/v1", post=post_with(text))
        with pytest.raises(LimitReached) as info:
            p.complete("sys", [{"role": "user", "text": "go"}], [])
        assert info.value.limit == limit
    p = OpenAICompatProvider("m", base_url="http://x/v1", post=post_with("HTTP 502: bad gateway"))
    with pytest.raises(RuntimeError, match="502"):
        p.complete("sys", [{"role": "user", "text": "go"}], [])


def test_send_reasoning_hands_a_tool_turns_reasoning_back_and_only_when_asked():
    """gpt-oss's harmony format wants the reasoning of a tool-calling turn back with its calls (the probe
    runner's --send-reasoning); the eval provider does it only with send_reasoning, and records it."""
    from roaddraft.eval.providers.openai_compat import OpenAICompatProvider, parse_reply
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": "", "reasoning_content": "first the state",
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "get_document_state", "arguments": "{}"}}]}}]}
    assert "reasoning" not in parse_reply(reply).raw
    assert parse_reply(reply, send_reasoning=True).raw["reasoning"] == "first the state"
    plain = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done",
                                                                 "reasoning_content": "all drawn"}}]}
    assert "reasoning" not in parse_reply(plain, send_reasoning=True).raw    # no calls: nothing to hand back
    p = OpenAICompatProvider("m", base_url="http://x/v1", post=lambda body: reply, send_reasoning=True)
    assert p.complete("sys", [{"role": "user", "text": "go"}], []).raw["reasoning"] == "first the state"
    assert p.describe()["send_reasoning"] is True
    assert "send_reasoning" not in OpenAICompatProvider("m", base_url="http://x/v1", post=lambda b: reply).describe()

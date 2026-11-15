"""``--thinking off`` (training plan, the like-for-like base of a checkpoint
served without thinking): a request field of the OpenAI-compatible provider,
recorded in ``run.json`` (``provider_options``) and in every episode header
(``provider_config``), and held across a resume.

With the flag off nothing moves: the request body, the provider's record and
``run.json`` are what they were before the flag existed, and the prompt pins
of ``tests/test_eval_system_extra.py`` (every held-out brief hash, every
system prompt) are untouched by it, since the switch is not part of any
prompt.
"""
from __future__ import annotations

import json

import pytest

from roaddraft.eval import prompts, providers
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.__main__ import main
from roaddraft.eval.agents import LLMAgent
from roaddraft.eval.episode import EpisodeConfig, run_episode
from roaddraft.eval.providers.openai_compat import THINKING_OFF, OpenAICompatProvider
from roaddraft.eval.runner import ResumeMismatch, RunSpec, run
from roaddraft.eval.trajectory import read_episode

DEV = tasksets.load("d1-dev")["tasks"]
#: the 9B's sampling on the board (benchmarks/lmstudio/models.json)
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}
TOOLS = [{"name": "submit", "description": "hand the drawing in", "input_schema": {"type": "object"}}]


def _submit_reply(reasoning: str = "") -> dict:
    message = {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                                              "function": {"name": "submit", "arguments": "{}"}}]}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {"choices": [{"message": message, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "completion_tokens_details": {"reasoning_tokens": 3 if reasoning else 0}}}


def _provider(sent: list, **options) -> OpenAICompatProvider:
    def post(body):
        sent.append(body)
        return _submit_reply()
    return OpenAICompatProvider("qwen/qwen3.5-9b", post=post, **options)


# ------------------------------------------------------- the flag off: nothing moves


def test_with_the_flag_off_the_request_and_the_record_are_as_before():
    sent = []
    p = _provider(sent, extra_body=SAMPLING, lms_context=131072)
    body = p.request("the system prompt", [{"role": "user", "text": "the brief"}], TOOLS)
    assert sorted(body) == sorted([*SAMPLING, "model", "messages", "tools"])
    assert "chat_template_kwargs" not in body and "reasoning_effort" not in body
    assert p.describe() == {"base_url": "http://localhost:1234/v1", "call_cap": 16,
                            "type_lists_rewritten": False, "extra_body": SAMPLING, "lms_context": 131072}


def test_with_the_flag_off_run_json_and_the_header_have_no_new_key(tmp_path):
    spec = RunSpec(taskset="d1-dev", models=("m",), provider="openai", provider_options={"extra_body": SAMPLING})
    assert spec.to_dict()["provider_options"] == {"extra_body": SAMPLING}
    sent = []
    r = run_episode(tasksets.task_from_entry(DEV[1]), LLMAgent(_provider(sent, extra_body=SAMPLING)),
                    EpisodeConfig(level="vague"), out_root=tmp_path)
    header = read_episode(r.path)["header"]
    assert "thinking" not in header["provider_config"] and "thinking" not in header
    assert "chat_template_kwargs" not in sent[0] and "reasoning_effort" not in sent[0]


# ------------------------------------------------------------ the flag on


def test_thinking_off_goes_into_every_request_and_into_the_header(tmp_path):
    task = tasksets.task_from_entry(DEV[1])
    off, plain = [], []
    r1 = run_episode(task, LLMAgent(_provider(off, extra_body=SAMPLING, thinking="off")),
                     EpisodeConfig(level="vague"), out_root=tmp_path / "off")
    r0 = run_episode(task, LLMAgent(_provider(plain, extra_body=SAMPLING)),
                     EpisodeConfig(level="vague"), out_root=tmp_path / "on")
    assert off and all(b["chat_template_kwargs"] == {"enable_thinking": False}
                       and b["reasoning_effort"] == "none" for b in off)
    # the switch is a request field only: the same messages, tools and sampling
    rest = {k: v for k, v in off[0].items() if k not in THINKING_OFF}
    assert rest == plain[0]
    h1, h0 = read_episode(r1.path)["header"], read_episode(r0.path)["header"]
    assert h1["provider_config"]["thinking"] == "off"
    for key in ("prompt_hash", "prompt_sha256", "system_prompt", "tools_sha256"):
        assert h1[key] == h0[key], key
    assert h1["prompt_sha256"] == prompts.digest(prompts.system_prompt("neutral", "single"))


def test_thinking_off_keeps_the_other_template_arguments_of_the_spec():
    sent = []
    p = _provider(sent, extra_body={"chat_template_kwargs": {"enable_thinking": True, "other": 1}, "top_k": 64},
                  thinking="off")
    body = p.request("s", [{"role": "user", "text": "b"}], TOOLS)
    assert body["chat_template_kwargs"] == {"enable_thinking": False, "other": 1} and body["top_k"] == 64
    assert p.extra_body["chat_template_kwargs"]["enable_thinking"] is True   # the spec's own record is not edited


def test_the_one_setting_is_off_and_it_does_not_combine_with_an_effort():
    with pytest.raises(ValueError, match="unknown thinking setting"):
        OpenAICompatProvider("m", post=lambda b: {}, thinking="on")
    with pytest.raises(ValueError, match="both set reasoning_effort"):
        OpenAICompatProvider("m", post=lambda b: {}, thinking="off", effort="low")
    assert providers.make("m", "openai", thinking="off").thinking == "off"
    assert providers.make("m", "openai", thinking=None).thinking is None
    assert providers.make("fake", "fake", thinking="off") is not None      # a provider without the option drops it


# ------------------------------------------------------------------ the run and the CLI


def _spec(tmp_path, **options) -> RunSpec:
    return RunSpec(taskset="d1-dev", agents=(), models=("qwen/qwen3.5-9b",), provider="openai", levels=("vague",),
                   limit=1,
                   concurrency=1, results_root=str(tmp_path / "results"), run_id="nothink",
                   provider_options=options)


def _factory(name, spec):
    return LLMAgent(_provider([], **spec.provider_options))


def test_a_run_records_the_setting_and_is_not_resumed_under_the_other(tmp_path):
    summary = run(_spec(tmp_path, thinking="off"), agent_factory=_factory)
    assert summary["episodes"] == 1
    run_json = tmp_path / "results" / "nothink" / "run.json"
    before = run_json.read_text()
    assert json.loads(before)["spec"]["provider_options"] == {"thinking": "off"}
    with pytest.raises(ResumeMismatch, match="ran with thinking off and this run asks for it left to the model"):
        run(_spec(tmp_path), agent_factory=_factory)
    assert run_json.read_text() == before                         # nothing rewritten
    assert run(_spec(tmp_path, thinking="off"), agent_factory=_factory)["skipped"] == 1


def test_a_run_left_to_the_model_is_not_resumed_with_thinking_off(tmp_path):
    run(_spec(tmp_path), agent_factory=_factory)
    with pytest.raises(ResumeMismatch, match="ran with thinking left to the model and this run asks for it off"):
        run(_spec(tmp_path, thinking="off"), agent_factory=_factory)


def test_the_cli_takes_the_flag_for_the_openai_provider_only(tmp_path, capsys):
    base = ["run", "--taskset", "d1-dev", "--limit", "1", "--out", str(tmp_path / "results"), "--thinking", "off"]
    assert main([*base, "--model", "qwen/qwen3.5-9b", "--level", "vague", "--dry-run"]) == 0
    assert "thinking off: every request asks the server for it" in capsys.readouterr().out
    assert main([*base, "--agent", "oracle"]) == 2
    assert "--model on the openai provider only" in capsys.readouterr().err
    assert main([*base, "--model", "fake-oracle", "--provider", "fake"]) == 2
    assert "(not fake)" in capsys.readouterr().err
    assert main([*base, "--model", "claude-sonnet-5-5"]) == 2
    assert "(not anthropic)" in capsys.readouterr().err
    assert main([*base, "--model", "qwen/qwen3.5-9b", "--effort", "low"]) == 2
    assert "does not combine with --effort" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()

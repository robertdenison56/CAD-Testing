"""``--system-extra FILE`` (training plan stage T0): one file appended to every
model's system prompt, named with its sha256 in ``run.json`` and in every
episode header, and covered by the episode's prompt hash.

The identity tests are the guard on everything already run: with the flag
off, every brief of every held-out set hashes as it did before the flag, and
every system prompt is the template's, byte for byte.  The brief digests
below were taken before the flag existed (2026-11-12), and every prompt hash
the board's v3 episodes recorded on d1-test, d1-test-hard, d1-real,
d1-real-hard and hard-pilots agreed with them (7,214 headers).  If one of
these fails, a held-out prompt moved: every board row on that set needs a
rerun before its numbers compare, and only then are the pins here updated.

The convention sheet itself (``benchmarks/training/conventions-v1.md``) is
held to the frozen drafting spec: every number in it comes from the spec, so
no task's value -- a station, a bearing, a coordinate, a date -- can be in it.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import re
from concurrent.futures import ProcessPoolExecutor

import pytest

from roaddraft.api.session import Session
from roaddraft.eval import prompts
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.__main__ import main
from roaddraft.eval.agents import LLMAgent
from roaddraft.eval.episode import Episode, EpisodeConfig, prompt_hash, run_episode
from roaddraft.eval.probe_tasks import ProbeEpisode
from roaddraft.eval.probe_tasks import system_prompt as probe_system_prompt
from roaddraft.eval.providers import FakeProvider
from roaddraft.eval.providers.fake import turn
from roaddraft.eval.runner import RunSpec
from roaddraft.eval.tools import MODES
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.prompts import LEVELS
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1

SHEET = prompts.REPO / "benchmarks" / "training" / "conventions-v1.md"
#: the held-out sets: every one is posed exactly as before when the flag is off
HELD_OUT = ("d1-dev", "d1-test", "d1-test-hard", "d1-real", "d1-real-dev", "d1-real-hard",
            "hard-pilots")

#: (lines, sha256 over the lines "task_id level prompt_hash" of every task at both levels, in
#: manifest order), taken before --system-extra existed
BRIEFS = {
    "d1-dev": (100, "sha256:898fcc8f8a46a6edd0820de5c7f662292ddac610106b2f9b17822b5213f80835"),
    "d1-test": (200, "sha256:c7758d16b104a964c4b2b4b6d5afb2722eea0b4ba3940dbf0a63681ea1ae191d"),
    "d1-test-hard": (200, "sha256:946d8e8f63e2230d64145d8cd464f53a00c8d7d126cf0df8065be1af7f101e1c"),
    "d1-real": (200, "sha256:475df3c811df3c93aa631cd1de10dbb534eeac166bd219b650a1c9b000b86091"),
    "d1-real-dev": (48, "sha256:b7efe552a469536b5f8ad25a297b244e4b3e105da8f71af061d3e2d05c718bdb"),
    "d1-real-hard": (200, "sha256:040064ab8617a01eaca5027fe4aede4c7205702c1113a549bfc98c885109fc3c"),
    "hard-pilots": (224, "sha256:57276365c1be1ead081108a91e36bfb78ad8abb6cb0d3d85be1508dcd15b00dc"),
}
#: the D1 system prompt by mode, under every D1 set's default budgets (main after 4d135e7d, the
#: stationing hint: the board's v3 rows ran on the prompt before it, so T0 pairs with a base rerun)
SYSTEM = {
    "single": "sha256:084ffff960df35863b7e556af08e9f0e2656818f443f8df50aca8d2a7b34b240",
    "self_correct": "sha256:05b9f601b21da88d20a66dbac8ee9f2de805d434cdc42ab6c3369cd36a6e6702",
    "vision": "sha256:e1cf637be7511f73764b66c384ab4e03d973a5f2d92f107fcdca2fa4c694b1ad",
}
#: a probe task's own system prompt by mode, under hard-pilots' budgets
PROBE_SYSTEM = {
    "single": "sha256:e6c465190e2c5f71f7fb25fa30d0ec3dd6852e2a4cc76437eac49b28bcf0b343",
    "self_correct": "sha256:515075fe3f8e48d8bd85492161f2a3297b118a2ccfce86bf4629642bf41d61d0",
    "vision": "sha256:ef77c448e9746e17fe5116bbe29c899bd1fc1c6cf31482eb379c48cc1d6454fd",
}

DEV = tasksets.load("d1-dev")["tasks"]


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sheet(tmp_path, text="# House rules\n\n- Never draft on layer 0.\n"):
    path = tmp_path / "conventions.md"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------- the flag off: nothing moves


def _flag_off_rows(job):
    """One chunk of a set (run in a worker): for each task and level, the line the
    ``BRIEFS`` digest is over, from the header an episode writes with no system
    extra, and whether that header reads as the old one did (the hash of the
    brief alone, no ``system_extra`` key)."""
    from roaddraft.tasks.prompts import task_text
    name, rows = job
    out = []
    for entry in rows:
        probe = "probe" in entry
        d1_task = None if probe else tasksets.task_from_entry(entry)   # the same task at every level
        for level in LEVELS:
            if probe and level == "vague" and not entry.get("vague_task_id"):
                continue
            task = tasksets.task_from_entry(entry, level=level) if probe else d1_task
            kind = ProbeEpisode if probe else Episode
            header = kind(task, LLMAgent(FakeProvider()), EpisodeConfig(level=level)).header()
            brief = task.brief if probe else task_text(task.brief, level)
            out.append((f"{task.task_id} {level} {header['prompt_hash']}",
                        header["prompt_hash"] == _sha(brief) and "system_extra" not in header))
    return out


@pytest.fixture(scope="module")
def flag_off_rows():
    """Every held-out task's header prompt fields with the flag off, built in
    worker processes (the real sets rebuild their tasks from the sheets: about
    three minutes in one process)."""
    jobs = []
    for name in HELD_OUT:
        rows = tasksets.entries(name)
        jobs += [(name, rows[i:i + 6]) for i in range(0, len(rows), 6)]
    workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        done = list(pool.map(_flag_off_rows, jobs))
    out = {}
    for (name, _), rows in zip(jobs, done):
        out.setdefault(name, []).extend(rows)
    return out


@pytest.mark.parametrize("name", HELD_OUT)
def test_with_the_flag_off_every_held_out_prompt_hash_is_the_one_recorded(name, flag_off_rows):
    rows = flag_off_rows[name]
    old_form = [line for line, same in rows if not same]
    assert not old_form, f"{len(old_form)} headers on {name} no longer hash the brief alone: {old_form[:3]}"
    lines = [line for line, _ in rows]
    assert (len(lines), _sha("\n".join(lines))) == BRIEFS[name], (
        f"the briefs of {name} moved: every board row on it needs a rerun before it compares")


@pytest.mark.parametrize("name", HELD_OUT)
def test_with_the_flag_off_the_system_prompt_is_the_templates_byte_for_byte(name):
    entry = tasksets.entries(name)[0]
    probe = "probe" in entry
    budgets = tasksets.default_budgets(name)
    for mode in (MODES if name in ("d1-dev", "hard-pilots") else ("single",)):
        task = tasksets.task_from_entry(entry, level="vague")
        agent = LLMAgent(FakeProvider())
        config = EpisodeConfig(level="vague", mode=mode, budgets=budgets)
        episode = (ProbeEpisode if probe else Episode)(task, agent, config)
        episode.reset()
        want = (probe_system_prompt(mode, config.mode_budgets) if probe
                else prompts.system_prompt("neutral", mode, config.mode_budgets))
        assert agent.system == want
        assert prompts.digest(agent.system) == (PROBE_SYSTEM if probe else SYSTEM)[mode], (name, mode)
        header = episode.header()
        assert "system_extra" not in header and header["prompt_sha256"] == prompts.digest(want)


def test_with_the_flag_off_run_json_has_no_new_key():
    spec = RunSpec(taskset="d1-dev", models=("fake",), provider="fake")
    assert "system_extra" not in spec.to_dict()
    assert prompts.with_extra("a prompt\n", None) == "a prompt\n"


# ------------------------------------------------------------ the flag on


def test_the_extra_follows_the_system_prompt_and_moves_both_hashes(tmp_path):
    path = _sheet(tmp_path)
    extra = prompts.SystemExtra.load(path)
    assert extra.sha256 == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    task = tasksets.task_from_entry(DEV[1])
    base = prompts.system_prompt("neutral", "single")
    told, plain = FakeProvider([turn([("submit", {})])]), FakeProvider([turn([("submit", {})])])
    r1 = run_episode(task, LLMAgent(told), EpisodeConfig(level="vague", system_extra=extra),
                     out_root=tmp_path / "t0")
    r0 = run_episode(task, LLMAgent(plain), EpisodeConfig(level="vague"), out_root=tmp_path / "base")
    sent = told.requests[0]["system"]
    assert sent == base.rstrip("\n") + "\n\n# House rules\n\n- Never draft on layer 0.\n"
    assert plain.requests[0]["system"] == base
    assert told.requests[0]["transcript"] == plain.requests[0]["transcript"]   # the brief is the same
    h1, h0 = read_episode(r1.path)["header"], read_episode(r0.path)["header"]
    brief = plain.requests[0]["transcript"][0]["text"]
    assert h0["prompt_hash"] == _sha(brief) and "system_extra" not in h0
    assert h1["prompt_hash"] == prompt_hash(brief, extra) != h0["prompt_hash"]
    assert h1["system_extra"] == {"path": extra.path, "sha256": extra.sha256}
    assert h1["system_prompt"] == sent and h1["prompt_sha256"] == prompts.digest(sent)
    assert h0["prompt_sha256"] == prompts.digest(base) == SYSTEM["single"]
    # the extra is part of the prompt, not of the drawing: the same graded outcome
    assert r1.effective_score == r0.effective_score


def test_the_fake_oracle_scores_100_with_the_convention_sheet():
    extra = prompts.SystemExtra.load(SHEET)
    assert extra.path == "benchmarks/training/conventions-v1.md"
    for i in (0, 12, 33):
        provider = FakeProvider.oracle()
        r = run_episode(tasksets.task_from_entry(DEV[i]), LLMAgent(provider),
                        EpisodeConfig(level="vague", system_extra=extra))
        assert r.termination == "submit" and r.effective_score == 100.0, (DEV[i]["task_id"], r.error)
        assert provider.requests[0]["system"].endswith(extra.text.strip() + "\n")


def test_a_probe_task_takes_the_extra_after_its_own_system_prompt(tmp_path):
    extra = prompts.SystemExtra.load(_sheet(tmp_path))
    entry = tasksets.entries("hard-pilots")[0]
    task = tasksets.task_from_entry(entry, level="vague")
    provider = FakeProvider([turn([("submit", {})])])
    config = EpisodeConfig(level="vague", budgets=tasksets.default_budgets("hard-pilots"),
                           system_extra=extra)
    r = ProbeEpisode(task, LLMAgent(provider), config, out_root=tmp_path / "res").run()
    own = probe_system_prompt("single", config.mode_budgets)
    assert provider.requests[0]["system"] == prompts.with_extra(own, extra.text)
    h = read_episode(r.path)["header"]
    assert h["system_extra"] == extra.record() and h["prompt_hash"] == prompt_hash(task.brief, extra)


def test_a_system_extra_must_be_readable_text(tmp_path):
    with pytest.raises(ValueError, match="cannot read"):
        prompts.SystemExtra.load(tmp_path / "nowhere.md")
    with pytest.raises(ValueError, match="empty"):
        prompts.SystemExtra.load(_sheet(tmp_path, " \n\n"))
    bad = tmp_path / "latin1.md"
    bad.write_bytes("caf\xe9".encode("latin-1"))
    with pytest.raises(ValueError, match="UTF-8"):
        prompts.SystemExtra.load(bad)
    outside = prompts.SystemExtra.load(_sheet(tmp_path))
    assert outside.path == str((tmp_path / "conventions.md").resolve().as_posix())


# ------------------------------------------------------------------ the CLI


def _run(tmp_path, *extra_args):
    return main(["run", "--taskset", "d1-dev", "--model", "fake-oracle", "--provider", "fake",
                 "--level", "vague", "--limit", "1", "--concurrency", "1",
                 "--out", str(tmp_path / "results"), "--run-id", "t0", *extra_args])


def test_the_cli_names_the_file_in_run_json_and_every_header(tmp_path, capsys):
    sheet = _sheet(tmp_path)
    assert _run(tmp_path, "--system-extra", str(sheet)) == 0
    record = prompts.SystemExtra.load(sheet).record()
    run_json = json.loads((tmp_path / "results" / "t0" / "run.json").read_text())
    assert run_json["spec"]["system_extra"] == record
    (episode,) = (tmp_path / "results" / "t0" / "episodes").glob("*.jsonl")
    rec = read_episode(episode)
    assert rec["header"]["system_extra"] == record and rec["end"]["effective_score"] == 100.0
    assert "# House rules" in rec["header"]["system_prompt"]


def test_the_cli_dry_run_says_what_is_appended(tmp_path, capsys):
    assert _run(tmp_path, "--system-extra", str(_sheet(tmp_path)), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "system extra" in out and "characters after every model's system prompt" in out
    assert not (tmp_path / "results").exists()


def test_the_cli_refuses_an_extra_no_model_reads_and_a_file_it_cannot(tmp_path, capsys):
    sheet = _sheet(tmp_path)
    rc = main(["run", "--taskset", "d1-dev", "--agent", "oracle", "--limit", "1",
               "--out", str(tmp_path / "results"), "--system-extra", str(sheet)])
    assert rc == 2 and "--model only" in capsys.readouterr().err
    assert _run(tmp_path, "--system-extra", str(tmp_path / "missing.md")) == 2
    assert "cannot read the system extra" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()


def test_a_run_is_not_resumed_under_another_prompt(tmp_path, capsys):
    sheet = _sheet(tmp_path)
    assert _run(tmp_path, "--system-extra", str(sheet)) == 0
    run_json = tmp_path / "results" / "t0" / "run.json"
    before = run_json.read_text()
    assert _run(tmp_path) == 2                                   # the same run id, no extra
    assert "a resumed run keeps its prompt" in capsys.readouterr().err
    (tmp_path / "other").mkdir()
    other = _sheet(tmp_path / "other", "# Other rules\n")
    assert _run(tmp_path, "--system-extra", str(other)) == 2      # another extra
    assert run_json.read_text() == before                       # nothing rewritten
    assert _run(tmp_path, "--system-extra", str(sheet)) == 0      # the same extra resumes
    assert "1 resumed" in capsys.readouterr().out


# ---------------------------------------------------------- the convention sheet


#: numbers the sheet may use that are not written in the spec as they stand
DERIVED = {0.0: "layer 0",
           0.14: "a tick 0.14 in long: twice stationing.tick_half_len_in; also the callout text height",
           5.0: "0.10 in at 1\" = 50' is 5 ft: text.label_height_in x allowed_feet_per_inch"}


def _spec_numbers() -> set:
    keep = {k: v for k, v in DRAFTING_SPEC_V1.items()
            if k not in ("spec_id", "version", "status", "caltrans_levels")}
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", json.dumps(keep, ensure_ascii=False))}


def test_the_convention_sheet_is_short_and_carries_no_task_value():
    text = SHEET.read_text(encoding="utf-8")
    # about 1,200-1,500 tokens: 3.2 characters a token is what the 9B's own prompts measured
    assert len(text.strip()) <= 5200, "the sheet has grown: it rides on every request of every episode"
    allowed = _spec_numbers() | set(DERIVED)
    stray = sorted({n for n in re.findall(r"\d+(?:\.\d+)?", text) if float(n) not in allowed})
    assert not stray, f"numbers the frozen spec does not hold (a task value?): {stray}"
    spec_text = json.dumps(DRAFTING_SPEC_V1, ensure_ascii=False)
    stations = set(re.findall(r"\d+\+\d{2}(?:\.\d+)?", text))
    assert stations and all(s in spec_text for s in stations), stations      # the spec's own examples
    bearings = re.findall(r"[NS] \d+°\d+'\d+\" [EW] [\d.]+'", text)
    assert bearings == ["N 71°33'54\" E 1240.36'"]
    assert not re.search(r"ALIGN-\d|BASE:|\bC-\d{3}\b|\b20\d\d-\d\d-\d\d\b", text)


def test_the_convention_sheet_names_the_spec_layers_and_real_tools():
    text = SHEET.read_text(encoding="utf-8")
    named = set(re.findall(r"\b(?:align|rd|pp|border)_[A-Za-z-]*[A-Za-z]", text))
    assert named == set(DRAFTING_SPEC_V1["layer_set"])
    for role, layer in DRAFTING_SPEC_V1["layers"].items():
        assert layer in text, role
    manifest = Session().manifest()
    commands = {c["name"] for c in manifest["commands"] + manifest["queries"]}
    words = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))
    assert words - commands == {"view_rotation"}
    assert "NORTH_ARROW" in text and "CURVE DATA" in text

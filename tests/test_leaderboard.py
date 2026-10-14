"""The Track P leaderboard: the ranking rules on made-up rows, and the run
folders read back from disk, written, and checked for staleness."""
from __future__ import annotations

import json
import sys

from roaddraft.probes import tasks
from roaddraft.runners import Options, run_probe
from roaddraft.runners import __main__ as cli
from roaddraft.runners import leaderboard as lb
from roaddraft.runners.anthropic_api import AnthropicBackend
from roaddraft.runners.score import measures

IDS = [p.id for p in tasks.PROBES]
BLANK = next(p for p in tasks.PROBES if p.start == "blank")
SERVER = [sys.executable, "-m", "roaddraft.mcp.server"]


def attempt(label, probe, result, model="m", run="2026-10-09-k3", calls=10, faults=0,
            cost=0.10, stop="answered", backend="anthropic"):
    row = {"probe": probe, "passed": result == "pass", "detail": f"{probe} wrong", "calls": calls,
           "faults": faults, "recovered": 0, "fault_streak": int(faults > 0), "fault_loop": False,
           "renders": 1, "renders_fixed": 1, "design_queries": 2, "query_first": True}
    meta = {"backend": backend, "model": model, "stop": stop, "turns": 4, "seconds": 30.0,
            "tokens": {"input_tokens": 1000, "output_tokens": 100}, "cost_usd": cost,
            "max_turns": 120, "budget_s": 900.0, "vision": False, "effort": None}
    return lb.Attempt(run=run, label=label, probe=probe, outcome=result, row=row, meta=meta,
                      prompt_current=True, instructions_current=True)


def model_rows(model, passes, k=3, **kw):
    """``passes[probe]`` of ``k`` attempts pass, in labels ``<model>-r1..rk``."""
    return [attempt(f"{model}-r{i}", pid, "pass" if i <= passes[pid] else "fail", model=model, **kw)
            for pid in IDS for i in range(1, k + 1)]


def folders(*runs, unfinished=None):
    return [lb.Folder(name=r, title=f"{r} title", native=1, unfinished=dict(unfinished or {}))
            for r in runs]


def test_a_stop_is_the_check_s_the_budget_s_or_the_infrastructure_s():
    assert lb.outcome("answered", True) == "pass" and lb.outcome("answered", False) == "fail"
    assert lb.outcome("refusal", False) == "fail"
    for stop in ("budget", "budget_usd", "max_turns", "turn_limit", "context", "length"):
        assert lb.outcome(stop, True) == "budget"          # a failure even when the disk passes
    assert lb.outcome("error: claude exited 1: boom", True) == "excluded"
    assert lb.outcome("error: RuntimeError: HTTP 400: The model produced output that does not match "
                      "the expected peg-native format", False) == "fail"


def test_ties_break_on_hard_fail_then_invalid_calls_then_cost():
    spread = {pid: 2 for pid in IDS}                                   # 2/3 everywhere: never fails a probe
    lumpy = {pid: (3 if i % 3 else 0) for i, pid in enumerate(IDS)}    # the same 66 of 99, 11 never solved
    attempts = (model_rows("spread", spread)
                + model_rows("lumpy", lumpy)
                + model_rows("faulty", spread, faults=2)
                + model_rows("cheap", spread, cost=0.05)
                + model_rows("twin", spread, cost=0.05))
    b = lb.board(attempts, folders("2026-10-09-k3"))
    assert sum(lumpy.values()) == sum(spread.values())
    order = [r["model"] for r in b["ranked"]]
    assert set(order[:2]) == {"cheap", "twin"}
    assert order[2:] == ["spread", "faulty", "lumpy"]
    ranks = {r["model"]: r["rank"] for r in b["ranked"]}
    assert ranks["cheap"] == ranks["twin"] == 1 and ranks["spread"] == 3 and ranks["lumpy"] == 5
    lumpy_row = next(r for r in b["ranked"] if r["model"] == "lumpy")
    assert lumpy_row["never"] == 11 and abs(lumpy_row["hard_fail"] - 1 / 3) < 1e-9
    assert all(abs(r["score"] - 2 / 3) < 1e-9 for r in b["ranked"])
    text = lb.render_board(b)
    assert "the 95% intervals overlap" in text and "| 1 | cheap |" in text


def test_budget_ends_count_as_failures_and_infrastructure_ends_keep_a_row_from_ranking():
    passes = {pid: 3 for pid in IDS}
    attempts = model_rows("m", passes)
    attempts[0] = attempt("m-r1", IDS[0], "budget", stop="max_turns")
    attempts[1].outcome, attempts[1].meta["stop"] = "excluded", "error: claude exited 1"
    b = lb.board(attempts, folders("2026-10-09-k3"))
    assert not b["ranked"]
    row = b["unranked"][0]
    assert row["probes_short"] == [IDS[0]] and row["why"] == "k = 3 on 32 of 33 probes"
    assert row["valid"] == 98 and row["passes"] == 97                # the budget end is a failure
    assert row["probes"][IDS[0]]["marks"] == "B X P"
    card = lb.render_card(row, b)
    assert "Excluded, ended by the infrastructure" in card and "Ended by budget" in card
    # a fourth attempt brings the probe to k = 3 that count, and the row ranks
    attempts.append(attempt("m-r4", IDS[0], "pass"))
    b = lb.board(attempts, folders("2026-10-09-k3"))
    assert b["ranked"][0]["model"] == "m" and b["ranked"][0]["rank"] == 1


def test_single_runs_are_smoke_tests_and_an_unfinished_label_joins_its_repeat():
    smoke = [attempt("haiku", IDS[0], "pass", model="h", run="2026-10-08-smoke")]
    partial = [attempt("q-r1", pid, "pass", model="q") for pid in IDS[:5]]
    b = lb.board(smoke + partial, folders("2026-10-08-smoke", "2026-10-09-k3", unfinished={"q-r2": 1}))
    assert not b["ranked"]
    assert [r["model"] for r in b["unranked"]] == ["q"]
    row = b["unranked"][0]
    assert row["unfinished"] == 1 and row["why"].startswith("in progress: 1 episode unfinished")
    other = next(o for o in b["others"] if o["run"] == "2026-10-08-smoke")
    assert "single runs without `--repeat`" in other["why"] and "1/1 passed" in other["why"]
    assert row["card"] == "cards/q.md"


def test_the_interval_is_seeded_and_brackets_the_mean():
    outcomes = [[1, 1, 0], [0, 0, 0], [1, 1, 1], [1, 0, 0]] * 5
    lo, hi = lb.interval(outcomes)
    assert (lo, hi) == lb.interval(outcomes) and lo < 0.5 < hi
    assert lb.interval([[1, 1, 1]] * 4) == (1.0, 1.0) and lb.interval([]) == (None, None)


def test_class_runner_and_cost_come_from_the_run():
    assert lb.model_class("claude-haiku-4-5", {"backend": "claude-code"}) == "frontier API"
    assert lb.model_class("qwen/qwen3.5-9b", {"base_url": "http://localhost:1234/v1"}) == "local small"
    assert lb.model_class("gpt-oss:120b-cloud", {"base_url": "http://localhost:11434/v1"}) == "hosted open-weight"
    assert lb.model_class("roaddraft-qwen-t1", {"base_url": "http://localhost:8000/v1"}) == "RQ3 checkpoint"
    assert lb.runner({"backend": "openai", "base_url": "http://localhost:1234/v1"}) == "runners · openai (LM Studio)"
    assert lb.runner({"backend": "openai"}) == "runners · openai"
    assert lb.cost_of({"cost_usd": 0.09, "claude_cost_usd": 0.11}) == 0.11
    assert lb.cost_of({"cost_usd": None}) is None


def test_measures_read_queries_before_the_first_change_and_renders_followed_by_one():
    q = lambda tool, ok=True: {"tool": tool, "kind": "query", "ok": ok}
    c = lambda tool, ok=True: {"tool": tool, "kind": "command", "ok": ok}
    calls = [q("get_document_state"), c("place_callout", ok=False), q("station_to_xy"),
             c("place_callout"), q("render_sheet"), q("render_sheet"), c("modify_entity"),
             q("render_sheet")]
    m = measures(calls)
    assert m["query_first"] is True and m["design_queries"] == 1
    assert m["renders"] == 3 and m["renders_fixed"] == 1
    assert measures([c("draw_line"), q("measure")])["query_first"] is False
    assert measures([q("get_document_state")])["query_first"] is None


def anthropic_reply(content, stop="tool_use"):
    return {"content": content, "stop_reason": stop,
            "usage": {"input_tokens": 100, "output_tokens": 20}}


def test_cards_carry_scope_completion_and_report_fidelity():
    attempts = model_rows("m", {pid: 3 for pid in IDS})
    sheet_set = [a for a in attempts if a.probe == "sheet-set-callouts"]
    for a, done in zip(sheet_set, (18, 18, 12)):
        a.row.update(items_done=done, items_asked=18)
    say = {"report": True, "claims_done": True, "false_done": False, "false_items": 0,
           "claims_clean_run": True, "false_clean_run": False, "cited_ids": 2, "invented_ids": []}
    for a in attempts:
        a.row["claims"] = dict(say)
    # the third sheet-set attempt stopped six items short, failed, and said it was done
    sheet_set[2].outcome, sheet_set[2].row["passed"] = "fail", False
    sheet_set[2].row["claims"].update(false_done=True, false_items=6, false_clean_run=True,
                                      invented_ids=["TX-099"])
    row = lb.board(attempts, folders("2026-10-09-k3"))["ranked"][0]
    m = {name: value for name, value, _how in lb.card_measures(row)}
    assert m["scope completion"].startswith("48 of 54 items (89%) in 3 episodes of the 1 probes")
    assert m["scope completion"].endswith("2 of them did every item")
    assert m["report fidelity"] == ("1 of 1 failed episodes' reports said the task was done (6 claims "
                                    "the check contradicts); 1 of 99 claims of no errors came over a "
                                    "faulted trace; 1 of 198 cited ids never existed")


def test_the_board_is_read_from_run_folders_and_check_catches_a_hand_edit(tmp_path):
    runs = tmp_path / "probe_runs"
    # a native --repeat run: the fake model looks and stops, so the probe fails
    replies = iter([anthropic_reply([{"type": "tool_use", "id": "t", "name": "get_document_state", "input": {}}]),
                    anthropic_reply([{"type": "text", "text": "done"}], "end_turn")])
    backend = AnthropicBackend(Options(model="claude-haiku-4-5"), post=lambda body: next(replies))
    episode = runs / "2026-10-09-k3" / "runs" / "haiku-r1" / BLANK.id
    run_probe(backend, episode, BLANK, SERVER)
    meta = json.loads((episode / "run.json").read_text())
    assert meta["pins"]["tools_sha256"].startswith("sha256:") and "dirty" in meta["pins"]
    # a second repeat still on its probe, and an earlier rig's episode with no run.json
    unfinished = runs / "2026-10-09-k3" / "runs" / "haiku-r2" / BLANK.id
    unfinished.mkdir(parents=True)
    (unfinished / "prompt.txt").write_text("the task")
    rig = runs / "2026-09-19" / "runs" / "fable" / BLANK.id
    rig.mkdir(parents=True)
    (rig / "trace.jsonl").write_text("")
    (runs / "2026-09-19" / "RESULTS.md").write_text("# Find-probes, 2026-09-19\n\ntext\n")

    attempts, found = lb.collect(runs)
    assert [(a.label, a.probe, a.outcome) for a in attempts] == [("haiku-r1", BLANK.id, "fail")]
    assert attempts[0].prompt_current and attempts[0].instructions_current
    by_name = {f.name: f for f in found}
    assert by_name["2026-09-19"].rig == 1 and by_name["2026-10-09-k3"].unfinished == {"haiku-r2": 1}
    b = lb.board(attempts, found)
    row = b["unranked"][0]
    assert row["name"] == "Claude Haiku 4.5" and row["unfinished"] == 1 and row["cost_per_task"] is not None
    assert row["pins"]["commits"] and row["pins"]["tools"][0].startswith("sha256:")
    assert b["others"][0]["run"] == "2026-09-19" and "earlier rig" in b["others"][0]["why"]

    out = tmp_path / "leaderboard"
    assert cli.main(["leaderboard", "--runs", str(runs), "--out", str(out)]) == 0
    assert (out / "TRACK_P.md").exists() and (out / row["card"]).exists()
    assert json.loads((out / "track_p.json").read_text())["unranked"][0]["model"] == "claude-haiku-4-5"
    assert cli.main(["leaderboard", "--runs", str(runs), "--out", str(out), "--check"]) == 0
    card = out / row["card"]
    card.write_text(card.read_text().replace("Claude Haiku 4.5", "Claude Haiku 4.5 (the best)"))
    (out / "cards" / "stray.md").write_text("by hand")
    assert lb.check(b, out) == [row["card"], "cards/stray.md"]
    assert cli.main(["leaderboard", "--runs", str(runs), "--out", str(out), "--check"]) == 1
    lb.write(b, out)
    assert lb.check(b, out) == [] and not (out / "cards" / "stray.md").exists()

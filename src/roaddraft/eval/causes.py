"""Why each model fails: one cause for every lost point.

Robert, 2026-11-10: "all failures should be analyzed once complete to determine if models
were failing due not knowing the standards or failing the tool use, thinking, etc."  This
module gives every lost effective point of a run one cause, read from the episode files
alone (the verifier's findings, the calls and what each call made), with no judge:

- **standard**: a drafting convention the model did not apply, with no failed attempt at
  it: an element a plan sheet carries left off, lettering on layer 0 or at an illegible
  height, labels over linework, a sheet at a non-standard scale, annotation drafted on the
  alignment layer, a sheet's curve table listing curves the sheet does not show
  (``standards.STANDARD_CATEGORIES``).  Paired with the same model's
  explicit run (same harness, same tool surface), only what the explicit episode earned
  back when told stays a standard (*confirmed*); what it lost too is not a gap in
  knowledge and moves to reasoning.  Unpaired, a standard is *unconfirmed*.
- **tool use**: the model could not get the tools to do what it meant: an element left off
  after its command failed and never worked, lettering typed as plain text instead of an
  anchored label, the same thing drawn twice, the design linework edited, text escaped
  wrong in the call (a literal ``\\n``), nothing drawn because every drawing call failed,
  the episode stopped by its fault budget (too many failed calls).
- **reasoning**: the tools did what the model asked, but what it asked for was wrong: a
  wrong value (worked out by hand, typed over the engine's, a callout reading the wrong
  note, or the right command with the wrong input), a label at the wrong place or where no
  sheet shows it, linework off the design, a standard lost even when the prompt stated it,
  a submit with nothing drawn and no failed attempt.
- **budget**: the episode ran out of steps, time, context or output tokens, or ended in a
  provider or harness error: all its lost points, since nothing after the stop was tried.

A hard fail zeroes the rubric points the episode had earned; those points take the cause
of the finding that triggered it.  Findings on entities the start document already held,
which the model did not touch, are not the model's and are left out.

hard-pilots grades pass or fail per pilot, with no finding codes, so a failed pilot (100
points) takes one cause: tool use when a drawing command failed and never worked; else,
paired with the explicit run of the same pilot, *standard* when the explicit episode
passed (the vague brief left out what it needed) and reasoning when it failed too;
unpaired, *unresolved*.

``python -m roaddraft.eval causes RUN [RUN ...] [--table PATH]`` writes ``causes.md`` and
``causes.json`` into each run's ``report/`` and, with ``--table``, one table of every run.
k = 1 everywhere: a single task's split carries sampling noise; the totals are the read.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from roaddraft.eval.report import CATEGORY_OF, COORDINATE_TOOLS
from roaddraft.eval.standards import (CODE_STANDARD, LEFT_OFF, STANDARD_CATEGORIES, _lost)
from roaddraft.eval.trajectory import read_episode

CAUSES = ("standard", "tool_use", "reasoning", "budget", "unresolved")
CAUSE_WORDS = {
    "standard": "a drafting standard not known",
    "tool_use": "tool use",
    "reasoning": "reasoning",
    "budget": "budget or harness",
    "unresolved": "unresolved (no explicit run to compare)",
}

#: calls that read the document and change nothing: a failed query is not a failed attempt
QUERY_PREFIXES = ("get_", "list_", "find_", "render_")
QUERY_TOOLS = frozenset({
    "measure", "station_to_xy", "xy_to_station", "resolve_anchor", "key_points", "snap",
    "hit_test", "point_on_entity", "model_to_sheet", "sheet_to_model", "area", "traverse",
    "run_check", "submit", "get_task_brief", "undo", "redo", "save_document", "save_journal",
    "open_document", "export_dxf", "export_pdf", "export_landxml", "print_pdf"})
#: commands that letter or annotate: what they draw on the alignment layer is annotation
ANNOTATION_TOOLS = frozenset({
    "annotate_stationing", "place_label", "place_curve_table", "place_callout", "place_text",
    "place_dimension", "label_segments", "place_table", "place_point_table", "insert_block",
    "fill_title_block", "update_labels"})
#: the commands that draw what each D1 check grades: one of them failing and never working
#: is the tool-use reading of that check's element left off
PRODUCERS: Dict[str, frozenset] = {
    "D1-00": frozenset({"create_sheet", "create_viewport", "modify_viewport", "draw_line",
                        "draw_polyline", "place_label", "place_text"}),
    "D1-01": frozenset({"draw_alignment", "draw_line", "draw_arc", "draw_polyline", "draw_traverse"}),
    "D1-02": frozenset({"annotate_stationing"}),
    "D1-03": frozenset({"annotate_stationing", "place_label"}),
    "D1-04": frozenset({"annotate_stationing", "place_label"}),
    "D1-05": frozenset({"place_label", "label_segments"}),
    "D1-06": frozenset({"place_curve_table", "place_table", "label_segments"}),
    "D1-07": frozenset({"place_label", "annotate_stationing"}),
    "D1-08": frozenset({"place_label", "place_text"}),
    "D1-09": frozenset({"create_layer", "set_current_layer", "modify_layer"}),
    "D1-10": frozenset({"fill_title_block", "create_sheet"}),
    "D1-11": frozenset({"insert_block", "define_block"}),
    "D1-12": frozenset({"offset_entity", "draw_offset"}),
    "D1-13": frozenset({"place_dimension"}),
    "D1-14": frozenset({"attach_reference"}),
    "D1-15": frozenset({"create_alignment", "import_landxml"}),
    "D1-16": frozenset({"place_callout"}),
}
EARLY = ("budget", "error")


def is_query(name: Optional[str]) -> bool:
    name = name or ""
    return name in QUERY_TOOLS or name.startswith(QUERY_PREFIXES)


def _ids(obj, out: Set[str]) -> None:
    """Every ``id`` string anywhere under ``obj``: the entities the start document held."""
    if isinstance(obj, dict):
        v = obj.get("id")
        if isinstance(v, str):
            out.add(v)
        for x in obj.values():
            _ids(x, out)
    elif isinstance(obj, list):
        for x in obj:
            _ids(x, out)


# ------------------------------------------------------------ reading an episode

def load_episode(path) -> Optional[dict]:
    """One episode file as what the causes need: header facts, scores, termination, the
    in-scope checks with their findings, what each successful call made (id -> tool and
    params), what the model touched, the start document's ids, and the mutating tools that
    failed and never worked later in the episode.  None without a verify and an end record."""
    rec = read_episode(path)
    header, verify, end = rec["header"], rec["verify"], rec["end"]
    if header is None or end is None or verify is None:
        return None
    made: Dict[str, Tuple[str, dict]] = {}
    touched: Set[str] = set()
    calls: List[Tuple[str, bool]] = []
    for t in rec["turns"]:
        for call, res in zip((t.get("assistant") or {}).get("tool_calls") or [], t.get("results") or []):
            res = res if isinstance(res, dict) else {}
            name, ok = call.get("name"), bool(res.get("ok"))
            calls.append((name, ok))
            if ok:
                for i in res.get("created") or []:
                    made[str(i)] = (name, call.get("params") or {})
                touched.update(str(i) for i in (res.get("created") or []) + (res.get("modified") or []))
    unrecovered: Set[str] = set()
    for k, (name, ok) in enumerate(calls):
        if not ok and not is_query(name) and not any(n == name and o for n, o in calls[k + 1:]):
            unrecovered.add(name)
    baseline: Set[str] = set()
    if rec["journal"] is not None:
        _ids(rec["journal"].get("baseline"), baseline)
    checks = {}
    for c in verify.get("checks") or []:
        if c.get("in_scope", True) and not c.get("skipped"):
            checks[c["id"]] = {"weight": float(c.get("weight") or 0.0), "credit": float(c.get("credit") or 0.0),
                               "triggered": bool(c.get("hard_fail_triggered")),
                               "findings": [{"code": f.get("code"), "ids": [str(i) for i in f.get("entity_ids") or []],
                                             "actual": f.get("actual"), "expected": f.get("expected"),
                                             "note": f.get("note")}
                                            for f in c.get("findings") or []]}
    return {
        "task_id": header.get("task_id"), "task_type": header.get("task_type"),
        "level": header.get("level", "explicit"), "model": header.get("model"),
        "probe": header.get("probe"), "harness": header.get("harness_version"),
        "tools": header.get("tools_sha256"),
        "kind": verify.get("kind") or "d1", "passed": verify.get("passed"),
        "items": verify.get("items") or [],
        "termination": end.get("termination") or "unknown", "tripped": end.get("budget_tripped"),
        "effective": float(verify.get("effective_score", end.get("effective_score") or 0.0)),
        "rubric": float(verify.get("rubric_score", end.get("rubric_score") or 0.0)),
        "hard_failed": bool(verify.get("hard_failed", end.get("hard_failed"))),
        "checks": checks, "made": made, "touched": touched, "baseline": baseline,
        "unrecovered": unrecovered,
    }


def load_run(run_dir) -> Dict[str, dict]:
    """key -> episode: the task id, or for a pilot the pilot (its ids differ by level)."""
    out: Dict[str, dict] = {}
    for f in sorted(Path(run_dir, "episodes").glob("*.jsonl")):
        ep = load_episode(f)
        if ep is not None:
            out[ep["probe"] if ep["kind"] == "probe" and ep["probe"] else ep["task_id"]] = ep
    return out


# ------------------------------------------------------------ one finding, one episode

def _model_findings(ep: dict, findings: Sequence[dict]) -> List[dict]:
    """The findings that are the model's: one without entities (an element left off), or
    one on an entity the model made or touched, or one not in the start document."""
    out = []
    for f in findings:
        ids = f["ids"]
        if ids and all(i in ep["baseline"] and i not in ep["touched"] for i in ids):
            continue
        out.append(f)
    return out


def _escaped(actual, expected) -> bool:
    """A value wrong only by its escapes: the call sent a literal ``\\n`` or ``\\"``."""
    if not isinstance(actual, str) or not isinstance(expected, str) or "\\" not in actual:
        return False
    return actual.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\") == expected


#: verify.checks' note on a curve-table row for a curve the sheet does not show: a sheet's
#: table lists its own curves, a convention the vague brief leaves to the drafter
CURVE_SCOPE_NOTE = "the curve table has a row for a curve this sheet does not show"


def finding_cause(ep: dict, cid: str, code: str, ids: Sequence[str],
                  actual=None, expected=None, note=None) -> Tuple[str, str]:
    """(cause, sub-cause) of one finding of check ``cid`` in episode ``ep``."""
    cat = CATEGORY_OF.get(code, "value")
    makers = [ep["made"][i] for i in ids if i in ep["made"]]
    tools = {m[0] for m in makers}
    if cat == "completeness":
        what = LEFT_OFF.get(cid, cid)
        failed = sorted(ep["unrecovered"] & PRODUCERS.get(cid, frozenset()))
        if failed:
            return "tool_use", f"left off after {failed[0]} failed and never worked: {what}"
        return "standard", "left off: " + what
    if cat == "anchoring":
        return "tool_use", {"unanchored": "lettering typed as plain text, not an anchored label",
                            "duplicate": "the same element drawn twice",
                            "anchor_inconsistent": "a label whose text disagrees with its anchor"}.get(code, code)
    if cat in STANDARD_CATEGORIES:
        return "standard", CODE_STANDARD.get(code, code)
    if code == "design_tampered":
        return "tool_use", "the design linework edited"
    if code == "extra_linework":
        if tools & ANNOTATION_TOOLS:
            return "standard", "annotation drafted on the alignment layer"
        return "reasoning", "linework off the design on the alignment layer"
    if cat == "placement":
        return "reasoning", ("drawn where no sheet shows it" if code == "not_visible"
                             else "set at the wrong place")
    # value: wrong_value, wrong_field, geometry_mismatch
    if code == "wrong_value" and note == CURVE_SCOPE_NOTE:
        return "standard", "a sheet's curve table lists only the curves that sheet shows"
    if _escaped(actual, expected):
        return "tool_use", "text escaped wrong in the call (a literal \\n or \\\")"
    if "place_callout" in tools:
        return "reasoning", "a callout reading the wrong note"
    if tools & COORDINATE_TOOLS:
        return "reasoning", "a wrong value worked out by hand (hand-drawn or typed text)"
    if any((m[1] or {}).get("content") or (m[1] or {}).get("text") for m in makers):
        return "reasoning", "a wrong value worked out by hand (typed over the engine's)"
    if code == "wrong_field":
        return "reasoning", "a title-block field filled wrong"
    return "reasoning", "the right command with the wrong input"


def _shares(ep: dict, cid: str, check: dict) -> List[Tuple[str, str, float]]:
    """(cause, sub-cause, share) over a check's own findings, by count; a check that lost
    points with no finding of the model's is an element left off."""
    mine = _model_findings(ep, check["findings"])
    if not mine:
        return [finding_cause(ep, cid, "missing", []) + (1.0,)]
    counts = Counter(finding_cause(ep, cid, f["code"], f["ids"], f.get("actual"), f.get("expected"),
                                   f.get("note")) for f in mine)
    n = sum(counts.values())
    return [(c, s, k / n) for (c, s), k in counts.items()]


def _early(ep: dict) -> Tuple[str, str]:
    if ep["termination"] == "error":
        return "budget", "ended in a provider or harness error"
    if ep["tripped"] == "faults":
        return "tool_use", "stopped by the fault budget (too many failed calls)"
    return "budget", f"ran out of its {ep['tripped'] or 'budget'} budget"


def split_episode(ep: dict, told: Optional[dict] = None) -> List[dict]:
    """The episode's lost effective points as parts {cause, sub, points, check, confirmed}.
    The parts add up to 100 minus the effective score."""
    loss = 100.0 - ep["effective"]
    if loss <= 1e-9:
        return []
    if ep["termination"] in EARLY:
        c, s = _early(ep)
        return [{"cause": c, "sub": s, "points": loss, "check": None, "confirmed": None}]
    if ep["kind"] == "probe":
        return [_pilot_part(ep, told, loss)]
    if not ep["touched"]:
        # a D1 deliverable is always drawn: nothing drawn means every attempt failed, or none was made
        if ep["unrecovered"]:
            c, s = "tool_use", f"nothing drawn: {sorted(ep['unrecovered'])[0]} failed and never worked"
        else:
            c, s = "reasoning", "submitted without drawing anything"
        return [{"cause": c, "sub": s, "points": loss, "check": None, "confirmed": None}]
    parts: List[dict] = []
    if ep["hard_failed"] and ep["rubric"] > 1e-9:
        trig = [(cid, c) for cid, c in ep["checks"].items() if c["triggered"]]
        shares = Counter()
        for cid, c in trig:
            for cause, sub, sh in _shares(ep, cid, c):
                shares[(cause, "hard fail: " + sub, cid)] += sh / len(trig)
        if not shares:
            shares[("reasoning", "hard fail with no finding", None)] = 1.0
        told_hf = None if told is None else told["hard_failed"]
        for (cause, sub, cid), sh in shares.items():
            parts.append({"cause": cause, "sub": sub, "points": ep["rubric"] * sh, "check": cid,
                          "confirmed": None if told_hf is None or cause != "standard" else not told_hf})
    mine = _lost(ep)
    theirs = _lost(told) if told is not None else None
    for cid, pts in mine.items():
        if pts <= 1e-9:
            continue
        rec_frac = None
        if theirs is not None:
            rec_frac = max(0.0, pts - theirs.get(cid, pts)) / pts
        for cause, sub, sh in _shares(ep, cid, ep["checks"][cid]):
            p = pts * sh
            if cause == "standard" and rec_frac is not None:
                if rec_frac > 1e-9:
                    parts.append({"cause": "standard", "sub": sub, "points": p * rec_frac, "check": cid,
                                  "confirmed": True})
                if rec_frac < 1 - 1e-9:
                    parts.append({"cause": "reasoning", "sub": "lost even when told: " + sub,
                                  "points": p * (1 - rec_frac), "check": cid, "confirmed": None})
            else:
                parts.append({"cause": cause, "sub": sub, "points": p, "check": cid,
                              "confirmed": None})
    # a hard fail with nothing earned, or rounding: whatever is left unexplained
    rest = loss - sum(p["points"] for p in parts)
    if rest > 1e-6:
        parts.append({"cause": "reasoning", "sub": "lost with no finding of the model's", "points": rest,
                      "check": None, "confirmed": None})
    # a standard part of a hard fail, paired: lost even when told moves to reasoning
    for p in parts:
        if p["cause"] == "standard" and p["confirmed"] is False:
            p["cause"], p["sub"], p["confirmed"] = "reasoning", "lost even when told: " + p["sub"], None
    return parts


def _pilot_part(ep: dict, told: Optional[dict], loss: float) -> dict:
    failed = sorted(ep["unrecovered"])
    if failed:
        return {"cause": "tool_use", "sub": f"{failed[0]} failed and never worked", "points": loss,
                "check": None, "confirmed": None}
    if told is None:
        return {"cause": "unresolved", "sub": "failed with no tool fault; no explicit run of this pilot",
                "points": loss, "check": None, "confirmed": None}
    if told.get("passed"):
        return {"cause": "standard", "sub": "passed when told: the vague brief left out what it needed",
                "points": loss, "check": None, "confirmed": True}
    return {"cause": "reasoning", "sub": "failed when told too, with no tool fault", "points": loss,
            "check": None, "confirmed": None}


# ------------------------------------------------------------ a run

def find_explicit(run_dir) -> Optional[Path]:
    """The explicit run beside a vague one on the same harness and tool surface: the run id
    without ``-vague``, else without ``-vague`` and ``-v3``.  A twin on another harness or
    tool surface is not a fair 'when told' (its tools explained less)."""
    run_dir = Path(run_dir)
    if "-vague" not in run_dir.name:
        return None
    mine = next(iter(load_run_headers(run_dir)), None)
    names = [run_dir.name.replace("-vague", "", 1)]
    if names[0].endswith("-v3"):
        names.append(names[0][:-3])
    for n in names:
        other = run_dir.parent / n
        if not (other / "episodes").is_dir():
            continue
        theirs = next(iter(load_run_headers(other)), None)
        if mine and theirs and mine == theirs:
            return other
    return None


def load_run_headers(run_dir) -> Iterable[Tuple[Optional[str], Optional[str]]]:
    """(harness version, tool surface) of a run's first episode."""
    for f in sorted(Path(run_dir, "episodes").glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            head = json.loads(fh.readline() or "{}")
        if head.get("type") == "header":
            yield (head.get("harness_version"), head.get("tools_sha256"))
            return


def analyse(run_dir, explicit_dir=None) -> dict:
    """The run's lost points by cause and sub-cause, per task averaged over its tasks."""
    eps = load_run(run_dir)
    told_eps = load_run(explicit_dir) if explicit_dir else {}
    keys = sorted(eps)
    n = len(keys)
    parts: List[dict] = []
    for k in keys:
        ep = eps[k]
        for p in split_episode(ep, told_eps.get(k)):
            p["task_id"], p["task_type"] = ep["task_id"], ep["task_type"]
            parts.append(p)
    by_cause = Counter()
    confirmed = Counter()
    by_type: Dict[str, Counter] = defaultdict(Counter)
    subs: Dict[Tuple[str, str], dict] = {}
    for p in parts:
        by_cause[p["cause"]] += p["points"] / n
        if p["cause"] == "standard":
            confirmed["confirmed" if p["confirmed"] else "unconfirmed"] += p["points"] / n
        by_type[p["task_type"]][p["cause"]] += p["points"] / n
        s = subs.setdefault((p["cause"], p["sub"]), {"cause": p["cause"], "sub": p["sub"], "points": 0.0,
                                                    "tasks": set(), "examples": Counter()})
        s["points"] += p["points"]
        s["tasks"].add(p["task_id"])
        s["examples"][p["task_id"]] += p["points"]
    lines = sorted(({"cause": s["cause"], "sub": s["sub"], "points_per_task": s["points"] / n,
                     "tasks": len(s["tasks"]),
                     "examples": [t for t, _ in s["examples"].most_common(3)]} for s in subs.values()),
                   key=lambda r: -r["points_per_task"])
    mean_eff = sum(e["effective"] for e in eps.values()) / n if n else None
    first = next(iter(eps.values()), {})
    pilots = first.get("kind") == "probe"
    failed_items: Dict[str, Counter] = defaultdict(Counter)
    if pilots:
        for ep in eps.values():
            if not ep["passed"]:
                for item, ok in ep["items"]:
                    if not ok:
                        failed_items[ep["task_type"]][item] += 1
    return {
        "run_id": Path(run_dir).name, "explicit_run_id": Path(explicit_dir).name if explicit_dir else None,
        "model": first.get("model"), "level": first.get("level"), "set": _set_of(Path(run_dir).name),
        "tasks": n, "paired_tasks": sum(1 for k in keys if k in told_eps), "pilots": pilots,
        "effective_mean": mean_eff, "lost_per_task": None if mean_eff is None else 100.0 - mean_eff,
        "by_cause": {c: by_cause.get(c, 0.0) for c in CAUSES},
        "standard_confirmed": dict(confirmed),
        "by_task_type": {t: {c: v for c, v in cnt.items()} for t, cnt in sorted(by_type.items())},
        "lines": lines,
        "failed_items": {t: dict(c.most_common(5)) for t, c in sorted(failed_items.items())},
        "parts": parts,
    }


def _set_of(run_id: str) -> str:
    for s in ("hard-pilots", "d1-test-hard", "d1-real-hard", "d1-test", "d1-real"):
        if run_id.startswith(f"e3-{s}-"):
            return s
    return run_id.split("-")[1] if run_id.count("-") > 1 else run_id


# ------------------------------------------------------------ writing

def _f(x: Optional[float]) -> str:
    return "–" if x is None else f"{x:.1f}"


def render_markdown(s: dict) -> str:
    L = [f"# Why the points were lost: {s['run_id']}", ""]
    L.append(f"{s['model']}, {s['level']} prompt, {s['tasks']} tasks: mean effective {_f(s['effective_mean'])}, "
             f"so {_f(s['lost_per_task'])} points a task lost.")
    if s["paired_tasks"]:
        L.append(f"Paired with `{s['explicit_run_id']}` ({s['paired_tasks']} tasks, same harness and tool "
                 "surface): a standard the explicit episode earned back when told is *confirmed*; one it lost "
                 "too is counted as reasoning.")
    else:
        L.append("No explicit run of this model on the same harness and tool surface: every standard is "
                 "*unconfirmed* (it may be a standard the model knew and could not apply).")
    L += ["", "| Cause | Points a task | Share of the loss |", "|---|---:|---:|"]
    lost = s["lost_per_task"] or 0.0
    for c in CAUSES:
        pts = s["by_cause"].get(c, 0.0)
        if c == "unresolved" and pts < 0.05:
            continue
        L.append(f"| {CAUSE_WORDS[c]} | {_f(pts)} | {(100 * pts / lost if lost else 0):.0f}% |")
    if s["standard_confirmed"]:
        L.append("")
        L.append("Standards: " + ", ".join(f"{k} {_f(v)}" for k, v in sorted(s["standard_confirmed"].items()))
                 + " points a task.")
    L += ["", "## By sub-cause", "", "| Cause | Sub-cause | Tasks | Points a task | Examples |",
          "|---|---|---:|---:|---|"]
    for r in s["lines"]:
        if r["points_per_task"] < 0.05:
            continue
        L.append(f"| {CAUSE_WORDS[r['cause']]} | {r['sub']} | {r['tasks']} | {_f(r['points_per_task'])} | "
                 + ", ".join(f"`{t}`" for t in r["examples"]) + " |")
    L += ["", "## By task type (points a task, over the whole set)", "",
          "| Task type | Standard | Tool use | Reasoning | Budget | Unresolved |", "|---|---:|---:|---:|---:|---:|"]
    for t, c in s["by_task_type"].items():
        L.append(f"| {t} | " + " | ".join(_f(c.get(k)) for k in CAUSES) + " |")
    if s["failed_items"]:
        L += ["", "## Failed pilots: the items most often missed, by family", ""]
        for t, items in s["failed_items"].items():
            L.append(f"- **{t}**: " + "; ".join(f"{i} ({k})" for i, k in items.items()))
    L += ["", "k = 1: a single task's split carries sampling noise; the totals are the read. "
          "Built by `roaddraft.eval.causes`."]
    return "\n".join(L) + "\n"


def write(s: dict, out_dir) -> List[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / "causes.md", out / "causes.json"
    md.write_text(render_markdown(s), encoding="utf-8")
    js.write_text(json.dumps({k: v for k, v in s.items() if k != "parts"}, indent=1), encoding="utf-8")
    return [md, js]


SET_ORDER = ("d1-test", "d1-real", "d1-test-hard", "d1-real-hard", "hard-pilots")


def render_table(rows: Sequence[dict]) -> str:
    """Every run: points a task lost by cause, by set, the largest loss first."""
    L = ["# Why each model fails: points lost by cause", "",
         "Every lost effective point of each vague-prompt run, put down to one cause by "
         "`python -m roaddraft.eval causes` (`roaddraft.eval.causes`: the rules are in its docstring). "
         "**Standard**: a drafting convention not applied, with no failed attempt at it; *confirmed* where "
         "the same model's explicit run earned it back when told (a standard it lost even when told counts "
         "as reasoning). **Tool use**: the tools did not do what the model meant (a command that failed and "
         "never worked, lettering typed as plain text, doubled output, the fault budget). **Reasoning**: the "
         "tools did what the model asked, but what it asked for was wrong. **Budget**: out of steps, time, "
         "context or output, or a provider error. hard-pilots is pass or fail, so a failed pilot takes one "
         "cause; with no explicit run of the pilot and no tool fault it is unresolved.", ""]
    for st in SET_ORDER + tuple(sorted({r["set"] for r in rows} - set(SET_ORDER))):
        mine = [r for r in rows if r["set"] == st]
        if not mine:
            continue
        L += [f"## `{st}`", "",
              "| Run | Effective | Lost | Standard (confirmed) | Tool use | Reasoning | Budget | Unresolved | Paired |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for r in sorted(mine, key=lambda r: -(r["effective_mean"] or 0)):
            b = r["by_cause"]
            conf = r["standard_confirmed"].get("confirmed")
            L.append(f"| `{r['run_id']}` | {_f(r['effective_mean'])} | {_f(r['lost_per_task'])} | "
                     f"{_f(b.get('standard'))}" + (f" ({_f(conf)})" if conf is not None else "") + " | "
                     f"{_f(b.get('tool_use'))} | {_f(b.get('reasoning'))} | {_f(b.get('budget'))} | "
                     f"{_f(b.get('unresolved'))} | {'yes' if r['paired_tasks'] else 'no'} |")
        L.append("")
    L.append("Points are per task, averaged over the run's tasks; each row's causes add up to its lost "
             "points. k = 1 everywhere. Per-run detail (sub-causes, task types, example tasks) is in each "
             "run's `report/causes.md`.")
    return "\n".join(L) + "\n"


__all__ = ["CAUSES", "CAUSE_WORDS", "load_episode", "load_run", "finding_cause", "split_episode",
           "find_explicit", "analyse", "render_markdown", "write", "render_table"]

"""The run report (eval plan section 4.9).

    python -m roaddraft.eval report results/<run_id> [--reverify] [--publish]

reads every episode under ``results/<run_id>/episodes/`` and writes, under
``results/<run_id>/report/`` (beside, not over, the runner's own
``summary.json``):

    summary.json      every number below, for publishing and the tracker
    leaderboard.md    the rows ranked, per-check credit, the failure taxonomy,
                      tool use and termination, the paired gaps, the split by
                      task type and sheet count, and the CI sizing
    per_check.svg     the per-check credit as a heatmap, a tooltip on each cell
    per_check.csv     mean credit per check per row
    taxonomy.csv      finding codes per row, rolled up to the seven categories
    episodes.csv      one line per episode

A row is one (model, provider, effort, dialect, mode, level).  The rules:

- The headline is the effective score (0 on a hard fail, else the rubric
  score), averaged per task over its samples and then over tasks; the 95%
  interval is a bootstrap over tasks, stratified by task type (the d1 sets
  cycle the types by design, so the mix is fixed and only the spread within
  a type is sampling error; the plain bootstrap is kept beside it as
  ``ci_plain``), with a fixed seed.  Rubric score,
  hard-fail rate and clean-sheet rate always sit beside it.
- Rows rank on the effective mean; ties break on hard-fail rate, then
  invalid-call rate, then cost per sheet.  Neighbouring rows are compared
  paired by task, and an ordering is called separated only where that
  paired interval excludes zero.
- Episodes ended by ``error`` (the harness or the provider's infrastructure
  failed: HTTP, credentials) are counted and left out of the scores;
  ``budget`` (with the limit it hit: steps, faults, output_tokens,
  wall_clock, output_limit, context, turn_time) and ``refusal`` are the
  model's outcomes and count.  A submit the model never called (it stopped
  talking) is a submit, and its rate is reported.
- Gaps are paired by task: the prompt gap (explicit - vague), the
  self-correct gain (self_correct - single) and the vision gain (vision -
  self_correct), each wherever both rows ran.
- Every episode carries the spec, generator and verifier it was scored
  under.  A mix, or a verifier older than the current one, is flagged;
  ``--reverify`` re-scores every episode from its journal block with the
  current verifier, which is how a verifier fix re-scores old runs.
- Cost is computed now from ``roaddraft.eval.prices`` (the dated price
  table) for a priced model, else taken from the episode's own figure.

Publishing copies ``summary.json``, ``leaderboard.md`` and the heatmap to
``benchmarks/runs/<run_id>/``.  A run on a draft spec or on a development
set (``d1-dev``, ``d1-real-dev``, ``pilot-dev``) is not rankable (the plan publishes only on
frozen ids and never reports the dev sets); it is published only on request,
marked with why.  ``scripts/make_leaderboard.py`` builds the README board from
the published summaries: one ranking per leaderboard set, ``d1-test`` (the
seeded sheets), ``d1-real`` (the redrafted sample plan sheets) and
``hard-pilots`` (the harder tasks, each graded pass or fail by its own check:
``eval/probe_tasks.py``), with ``d1-test-hard`` and ``d1-real-hard`` beside
them.  Within a set the prompt levels rank apart (``BOARD_LEVELS``, Robert,
2026-11-08): the vague-prompt rows are the set's board and its headline, and
the explicit-prompt rows are a board of their own, in their own file
(``LEVEL_BOARD_FILES``: ``LEADERBOARD_EXPLICIT.md``; Robert, 2026-11-08: "Move
all explicit prompts to their own board. Main focus is now on vague"), since a
score at one level is not comparable with one at the other.  Every task has
both prompts, the pilots too since 2026-11-08 (``Probe.vague``), so
``hard-pilots`` splits by level like the D1 sets.  A run is
held to its own set's generator version
(``taskset.current_generator``): the seeded generator or the real-sheet
builder.  A probe run is held to its task ids instead: each id carries the
hash of its task text, so the set may grow without unranking earlier rows,
while a changed or removed text shows as an id the set no longer has.  Its
verifier version is the pilot checks' source hash (``probe_tasks.check_version``,
``taskset.current_verifier``).  A probe run ranks only when it covers every
task of the current set; a run on part of it is published as **partial** and
listed, not ranked.  The seeded and real-sheet sets keep ranking a draw of
their set (d1-real's first row is 99 of its 108 tasks).

A row on a real-sheet set also carries ``by_group`` (``by_group()``): the
question groups of ``tasks.types.REAL_GROUPS`` (draft linework, letter
alignment data, produce the sheet, notes and dimensions), each with its
effective mean and interval, the way the probe board splits its tiers; the
real board shows them as columns beside the blended score (decided
2026-10-24, Robert; ``d1-real`` draws 25 tasks a group since 2026-10-27).
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import shutil
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from roaddraft import effort as effort_of
from roaddraft.eval.trajectory import read_episode, replay_journal
from roaddraft.tasks.types import REAL_GROUP_NAMES, REAL_GROUP_OF, REAL_GROUPS
from roaddraft.verify.report import FINDING_CODES

REPORT_VERSION = "e4-v2"  # (2026-11-04) coverage on every board set, errors -> partial, cost subsets, task means
# e4-v1 (2026-10-14): the leaderboard v0.1 report
BOOTSTRAP, SEED = 4000, 0
REPO = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO / "benchmarks" / "runs"
#: the task set the leaderboard ranks on; d1-variance sizes the interval first
LEADERBOARD_SET = "d1-test"
#: every set a board ranks on, each its own ranking: the seeded sheets and the
#: redrafted sample plan sheets (eval/taskset.py)
LEADERBOARD_SETS = ("d1-test", "d1-real", "hard-pilots", "d1-test-hard", "d1-real-hard")
#: what each board is, in a heading
SET_TITLES = {"d1-test": "seeded sheets", "d1-real": "the sample plan sheets",
              "hard-pilots": "the harder tasks (pass or fail)",
              "d1-test-hard": "seeded sheets, the whole job (3-5 curves, 2-3 sheets)",
              "d1-real-hard": "the sample plan sheets, the whole job"}
#: the development sets: a run on one is never published or ranked (``pilot-dev`` is the pilots'
#: validation set, ``probes/pilot_dev.py``: checkpoint selection only)
NEVER_REPORTED = ("d1-dev", "d1-real-dev", "pilot-dev")
#: the prompt levels a set's board ranks apart, the focus first (Robert, 2026-11-08: the
#: vague prompt is the board's focus; an explicit-prompt score is not comparable with it)
BOARD_LEVELS = ("vague", "explicit")
#: the sets whose tasks each carry one prompt of their own, so their board has no prompt
#: split: none since 2026-11-08, when every pilot gained a vague brief (``Probe.vague``) and
#: hard-pilots split by level like the D1 sets (Robert: every eval task has a vague prompt)
ONE_PROMPT_SETS: Tuple[str, ...] = ()
#: the board of each prompt level other than the focus, its own file beside LEADERBOARD.md
#: (Robert, 2026-11-08: "Move all explicit prompts to their own board. Main focus is now on vague")
LEVEL_BOARD_FILES = {"explicit": "LEADERBOARD_EXPLICIT.md"}
#: what each prompt level is, under its table's heading
LEVEL_NOTES = {"vague": "the request in a sentence, the way a PE would ask for it; what belongs "
                        "on the sheet is the drafter's to know. The board's focus.",
               "explicit": "the full brief, stating every standard the task is graded on. Ranked "
                           "on its own: an explicit-prompt score is not comparable with a "
                           "vague-prompt score."}
#: the CI half-width the v0.1 acceptance asks for, in points
TARGET_HALF_WIDTH = 5.0

#: finding codes rolled up to the writeup's categories (section 4.9)
TAXONOMY: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("completeness", ("missing", "missing_field")),
    ("value", ("wrong_value", "wrong_field", "geometry_mismatch", "extra_linework",
               "design_tampered")),
    ("anchoring", ("unanchored", "anchor_inconsistent", "duplicate")),
    ("placement", ("misplaced", "not_visible")),
    ("legibility", ("overlap", "off_sheet", "clipped", "upside_down")),
    ("standards", ("wrong_layer", "wrong_height", "wrong_layer_props")),
    ("sheet_setup", ("sheet_missing", "viewport_scale", "not_fitted")),
)
CATEGORIES = tuple(c for c, _ in TAXONOMY)
CATEGORY_OF = {code: cat for cat, codes in TAXONOMY for code in codes}
assert set(CATEGORY_OF) == set(FINDING_CODES), "every finding code needs a category"

#: tool errors that are the call's fault rather than the drawing's
INVALID_ERRORS = frozenset({"invalid_params", "unknown_command", "unknown_query", "invalid_call"})
#: the coordinate path: text and linework placed by hand
COORDINATE_TOOLS = frozenset({"place_text", "draw_line", "draw_arc", "draw_polyline"})
HARNESS_TOOL_NAMES = frozenset({"get_task_brief", "run_check", "submit"})
#: a fault is recovered when the same tool succeeds within this many calls
RECOVERY_WINDOW = 3

GROUP_DIMS = ("model", "provider", "effort", "dialect", "mode", "level")
#: what else sets a row apart, read from the episode header and carried only by a run that set it:
#: ``thinking`` (``--thinking off``, ``provider_config.thinking``) and ``system_extra`` (``--system-extra``,
#: the file's name and the head of its digest).  A run without them has neither field in its episode
#: rows nor in its row key, so its report and its place on the board are what they were before these
#: existed; a run with one is its own row, labelled so, on every board and in the Overall table.
VARIANT_DIMS = ("thinking", "system_extra")
#: (name, dimension, a, b): gap = effective(a) - effective(b), paired by task;
#: b None means every other value of the dimension
GAPS: Tuple[Tuple[str, str, str, Optional[str]], ...] = (
    ("prompt gap", "level", "explicit", "vague"),
    ("self-correct gain", "mode", "self_correct", "single"),
    ("vision gain", "mode", "vision", "self_correct"),
)


def _anchor_producers() -> frozenset:
    try:
        from roaddraft.commands.bus import ANCHOR_PRODUCERS
        return frozenset(ANCHOR_PRODUCERS)
    except ImportError:  # pragma: no cover
        return frozenset({"place_label", "annotate_stationing", "place_curve_table",
                          "draw_alignment"})


SEMANTIC_TOOLS = _anchor_producers()


# --------------------------------------------------------------- statistics

def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def bootstrap(values: Sequence[float], strata: Optional[Sequence[str]] = None,
              n: int = BOOTSTRAP, seed: int = SEED) -> Tuple[Optional[float], Optional[float]]:
    """A 95% percentile interval on the mean of ``values`` (one per task),
    resampled ``n`` times with a fixed seed.  With ``strata`` (each task's
    type) the tasks are resampled within their stratum, so the designed mix
    of task types stays fixed and only the spread within a type counts."""
    vals = [float(v) for v in values]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], vals[0]
    groups: Dict[str, List[float]] = {}
    for i, v in enumerate(vals):
        groups.setdefault(strata[i] if strata else "", []).append(v)
    pools = list(groups.values())
    rng = random.Random(seed)
    k = len(vals)
    stats = sorted(sum(sum(rng.choices(p, k=len(p))) for p in pools) / k for _ in range(n))
    return stats[round(0.025 * (n - 1))], stats[round(0.975 * (n - 1))]


def _pctl(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(values)
    if not vals:
        return None
    i = (len(vals) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)


def _r(x: Optional[float], digits: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), digits)


# ------------------------------------------------------------ one episode

def _flat_calls(turns: Sequence[dict]) -> List[dict]:
    """Every tool call in order with its result: name, ok, error type and
    the bus's command id (the journal length after a command)."""
    out = []
    for t in turns:
        calls = (t.get("assistant") or {}).get("tool_calls") or []
        for call, res in zip(calls, t.get("results") or []):
            res = res if isinstance(res, dict) else {}
            err = res.get("error") or {}
            out.append({"name": call.get("name"), "ok": bool(res.get("ok")),
                        "error": err.get("type") if not res.get("ok") else None,
                        "command_id": res.get("command_id"),
                        "repaired": bool(res.get("repaired"))})
    return out


def tool_use(turns: Sequence[dict]) -> dict:
    """Call counts from the turns: invalid calls, other faults, recoveries,
    the coordinate path against the anchored one, and where each successful
    ``run_check`` fell in the journal."""
    calls = _flat_calls(turns)
    errors = Counter(c["error"] for c in calls if not c["ok"])
    invalid = sum(v for k, v in errors.items() if k in INVALID_ERRORS)
    faults = [i for i, c in enumerate(calls) if not c["ok"]]
    recovered = sum(
        any(calls[j]["ok"] and calls[j]["name"] == calls[i]["name"]
            for j in range(i + 1, min(len(calls), i + 1 + RECOVERY_WINDOW)))
        for i in faults)
    ok_names = [c["name"] for c in calls if c["ok"]]
    checks, journal_len = [], 0
    for c in calls:
        if c["ok"] and c["command_id"] is not None and c["name"] not in HARNESS_TOOL_NAMES:
            journal_len = max(journal_len, int(c["command_id"]))
        if c["ok"] and c["name"] == "run_check":
            checks.append(journal_len)
    return {"tool_calls": len(calls), "invalid_calls": invalid,
            "repaired_calls": sum(1 for c in calls if c["repaired"]),
            "failed_calls": len(faults) - invalid, "faults": len(faults),
            "recovered": recovered, "errors": dict(errors),
            "coordinate_calls": sum(n in COORDINATE_TOOLS for n in ok_names),
            "semantic_calls": sum(n in SEMANTIC_TOOLS for n in ok_names),
            "check_prefixes": checks}


def score_prefix(journal: dict, prefix: int, level: str) -> float:
    """The effective score of the document the first ``prefix`` journal
    entries make: what the drawing scored when the agent last ran
    ``run_check``."""
    from roaddraft.tasks.brief import GroundTruth
    from roaddraft.verify import verify
    block = dict(journal)
    block["entries"] = list(journal.get("entries") or [])[:prefix]
    session = replay_journal(block)
    report = verify(session.doc, GroundTruth.from_dict(journal["truth"]),
                    journal=session.bus.journal, prompt_level=level)
    return report.effective_score


def _cost(header: dict, end: dict, turns: Sequence[dict] = ()
          ) -> Tuple[Optional[float], Optional[str]]:
    """Dollars for the episode at today's table, priced turn by turn (the
    table's rates step with each request's prompt size), else the episode's
    own figure."""
    usage = end.get("usage_total") or {}
    try:
        from roaddraft.eval import prices
    except ImportError:
        prices = None
    if prices is not None and usage:
        try:
            per_turn = [t.get("usage") for t in turns if t.get("usage")]
            cost = (prices.episode_cost(header.get("model"), per_turn) if per_turn
                    else prices.cost_usd(header.get("model"), usage))
            checked = (prices.load() or {}).get("checked")
        except Exception:  # a malformed or missing table: fall back to the episode's figure
            cost, checked = None, None
        if cost is not None:
            return float(cost), checked
    if end.get("cost_usd") is not None:
        return float(end["cost_usd"]), end.get("prices_checked")
    return None, None


def load_episode(path, reverify: bool = False, check_delta: bool = True) -> Optional[dict]:
    """One episode file as a flat row (plus its per-check credits and
    findings), or None when the episode has no end record yet."""
    rec = read_episode(path)
    header, end, verify_rec = rec["header"], rec["end"], rec["verify"]
    if header is None or end is None:
        return None
    level = header.get("level", "explicit")
    scored_by = "episode"
    if reverify and rec["journal"] is not None and rec["journal"].get("probe"):
        from roaddraft.eval.probe_tasks import rescore  # a probe task: its own check again
        verify_rec = rescore(path, rec["journal"])
        scored_by = "reverify"
    elif reverify and rec["journal"] is not None and (rec["journal"].get("truth") is not None):
        from roaddraft.eval.trajectory import reverify as _reverify
        verify_rec = _reverify(path, level=level).to_dict()
        scored_by = "reverify"
    verify_rec = verify_rec or {}
    checks = {}
    findings: List[str] = [f["code"] for f in verify_rec.get("findings") or []]
    hard_fail_checks = []
    for c in verify_rec.get("checks") or []:
        if not c.get("in_scope", True):
            continue
        checks[c["id"]] = {"name": c.get("name"), "weight": c.get("weight"),
                           "credit": float(c.get("credit") or 0.0)}
        findings.extend(f["code"] for f in c.get("findings") or [])
        if c.get("hard_fail_triggered"):
            hard_fail_checks.append(c["id"])
    use = tool_use(rec["turns"])
    effective = float(verify_rec.get("effective_score", end.get("effective_score") or 0.0))
    rubric = float(verify_rec.get("rubric_score", end.get("rubric_score") or 0.0))
    hard_failed = bool(verify_rec.get("hard_failed", end.get("hard_failed")))
    at_check = None
    if check_delta and use["check_prefixes"] and rec["journal"] is not None \
            and rec["journal"].get("truth") is not None:
        try:
            at_check = score_prefix(rec["journal"], use["check_prefixes"][-1], level)
        except Exception:  # a journal that does not replay: no delta, not a crash
            at_check = None
    cost, prices_checked = _cost(header, end, rec["turns"])
    usage = end.get("usage_total") or {}
    termination = end.get("termination") or "unknown"
    variant = variant_of(header)
    row = {
        "file": Path(path).name, "run_id": header.get("run_id"), "task_id": header.get("task_id"),
        "task_type": header.get("task_type"), "sheets": header.get("sheets"),
        "seed": header.get("seed"), "agent": header.get("agent"),
        "model": header.get("model") or header.get("agent"),
        "provider": header.get("provider") or "unknown", "effort": header.get("effort"),
        "effort_label": effort_label(header.get("model") or header.get("agent"),
                                     header.get("provider") or "unknown", header.get("effort"),
                                     (header.get("provider_config") or {}).get("extra_body"),
                                     variant.get("thinking")),
        "dialect": header.get("dialect", "neutral"), "mode": header.get("mode", "single"),
        "level": level, "sample": header.get("sample", 0),
        "spec_version": verify_rec.get("spec_version", header.get("spec_version")),
        "spec_hash": verify_rec.get("spec_hash", header.get("spec_hash")),
        "generator_version": header.get("generator_version"),
        "verifier_version": verify_rec.get("verifier_version", header.get("verifier_version")),
        "harness_version": header.get("harness_version"), "git_commit": header.get("git_commit"),
        "scored_by": scored_by, "termination": termination,
        "budget_tripped": end.get("budget_tripped"), "error": end.get("error"),
        "implicit_submit": bool(end.get("implicit_submit")),
        "effective_score": round(effective, 4), "rubric_score": round(rubric, 4),
        "hard_failed": hard_failed, "clean": effective >= 100.0 - 1e-9,
        "hard_fail_checks": ";".join(hard_fail_checks),
        "steps": int(end.get("steps") or 0), "turns": int(end.get("turns") or len(rec["turns"])),
        "run_check_uses": int(end.get("run_check_uses") or 0),
        "effective_at_last_check": None if at_check is None else round(at_check, 4),
        "tool_calls": use["tool_calls"], "invalid_calls": use["invalid_calls"],
        "repaired_calls": use["repaired_calls"],
        "failed_calls": use["failed_calls"], "faults": use["faults"],
        "recovered": use["recovered"], "coordinate_calls": use["coordinate_calls"],
        "semantic_calls": use["semantic_calls"],
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cost_usd": None if cost is None else round(cost, 6), "prices_checked": prices_checked,
        "elapsed_ms": end.get("elapsed_ms"),
        "findings": len(findings),
    }
    row.update(variant)   # only what the run set: a plain run's row has no such field
    return {"row": row, "checks": checks, "findings": findings, "errors": use["errors"]}


# --------------------------------------------------------------- aggregate

def variant_of(header: dict) -> dict:
    """The ``VARIANT_DIMS`` an episode's header carries, and no key for one it does not:
    ``thinking`` as the run set it, ``system_extra`` as the file's name and the first eight
    hex digits of its sha256 (two sheets of one name stay apart)."""
    out = {}
    thinking = (header.get("provider_config") or {}).get("thinking")
    if thinking:
        out["thinking"] = str(thinking)
    extra = header.get("system_extra")
    if extra:
        extra = extra if isinstance(extra, dict) else {"path": str(extra)}
        name = Path(str(extra.get("path") or "")).stem or "unnamed"
        digest = str(extra.get("sha256") or "").removeprefix("sha256:")[:8]
        out["system_extra"] = name + (f"@{digest}" if digest else "")
    return out


def variant_label(key: dict) -> str:
    """What a row's ``VARIANT_DIMS`` say in its label; empty for a row without them."""
    parts = []
    if key.get("thinking"):
        parts.append(f"thinking {key['thinking']}")
    if key.get("system_extra"):
        parts.append(f"system extra {key['system_extra']}")
    return " · ".join(parts)


def group_key(row: dict) -> Tuple:
    return tuple(row.get(d) for d in GROUP_DIMS + VARIANT_DIMS)


def key_dims(key: Tuple) -> dict:
    """A ``group_key`` as the dict a row's ``key`` holds: every ``GROUP_DIMS``, and a
    ``VARIANT_DIMS`` only where the run set it."""
    dims = dict(zip(GROUP_DIMS, key))
    dims.update({d: v for d, v in zip(VARIANT_DIMS, key[len(GROUP_DIMS):]) if v})
    return dims


def group_label(dims: dict) -> str:
    model = dims["model"] + (f" ({dims['effort']})" if dims.get("effort") else "")
    if dims.get("provider") in CLI_PROVIDERS:
        model += f" via {dims['provider']}"
    parts = [model, dims["mode"], dims["level"]]
    if dims.get("dialect") and dims["dialect"] != "neutral":
        parts.append(dims["dialect"])
    if variant_label(dims):
        parts.append(variant_label(dims))
    return " · ".join(parts)


#: how each E3 provider sends ``--effort``
EFFORT_SENT = {"anthropic": "the Messages API's `output_config.effort`",
               "openai": "`reasoning_effort` in the request body",
               "claude-code": "the CLI's `--effort`",
               "codex": "`model_reasoning_effort` in the CLI's config"}
#: the providers that are a headless CLI on a subscription (``providers.CLI_PROVIDERS``):
#: their rows say so beside the model, since the CLI's harness is part of the row
CLI_PROVIDERS = ("claude-code", "codex")


def effort_label(model: Optional[str], provider: str, effort: Optional[str],
                 extra_body: Optional[dict] = None, thinking: Optional[str] = None) -> str:
    """An episode's effort (``roaddraft.effort``): the level the run set, what
    the request body set, else the model's default marked ``(default)``, or
    ``default`` where that is not known; ``–`` for the harness's own agents.
    A run given ``--thinking`` says that: the switch is sent with every request
    and is not in ``extra_body``."""
    if provider == "harness":
        return "–"
    if thinking:
        return f"thinking {thinking}"
    return effort_of.describe(model or "?", effort, EFFORT_SENT.get(provider), extra_body)[0]


def effort_cell(row: dict) -> str:
    """A row's effort cell: the label its episodes carry, else one from its key
    (a summary written before rows carried it)."""
    if row.get("effort"):
        return row["effort"]
    key = row.get("key") or row
    return effort_label(key.get("model"), key.get("provider") or "unknown", key.get("effort"),
                        thinking=key.get("thinking"))


def task_means(eps: Sequence[dict], field: str = "effective_score") -> Dict[str, float]:
    by: Dict[str, List[float]] = {}
    for e in eps:
        by.setdefault(e["row"]["task_id"], []).append(e["row"][field])
    return {t: sum(v) / len(v) for t, v in by.items()}


def task_types(eps: Sequence[dict]) -> Dict[str, str]:
    return {e["row"]["task_id"]: str(e["row"]["task_type"]) for e in eps}


def _rate(eps: Sequence[dict], pred) -> Optional[float]:
    return _r(sum(1 for e in eps if pred(e["row"])) / len(eps), 4) if eps else None


def summarize_group(dims: dict, eps: Sequence[dict]) -> dict:
    """Every number of one row (section 5)."""
    errored = [e for e in eps if e["row"]["termination"] == "error"]
    scored = [e for e in eps if e["row"]["termination"] != "error"]
    rows = [e["row"] for e in scored]
    tm = task_means(scored)
    types = task_types(scored)
    tasks = sorted(tm)
    lo, hi = bootstrap([tm[t] for t in tasks], [types[t] for t in tasks])
    plain_lo, plain_hi = bootstrap([tm[t] for t in tasks])
    eff = mean(tm.values())
    half = None if lo is None else (hi - lo) / 2
    per_task: Dict[str, int] = Counter(r["task_id"] for r in rows)
    sds = []
    by_task: Dict[str, List[float]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r["effective_score"])
    for vals in by_task.values():
        if len(vals) >= 2:
            sds.append(statistics.stdev(vals))
    calls = sum(r["tool_calls"] for r in rows)
    faults = sum(r["faults"] for r in rows)
    coord = sum(r["coordinate_calls"] for r in rows)
    sem = sum(r["semantic_calls"] for r in rows)
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    checked = [r for r in rows if r["run_check_uses"] and r["effective_at_last_check"] is not None]
    terminations = Counter((r["termination"] + (f":{r['budget_tripped']}" if r["budget_tripped"] else ""))
                           for r in (e["row"] for e in eps))
    out = {
        "key": dims, "label": group_label(dims),
        "effort": eps[0]["row"].get("effort_label") if eps else effort_cell({"key": dims}),
        "n_episodes": len(eps), "n_scored": len(scored), "n_tasks": len(tm),
        "errors": len(errored),
        "k_min": min(per_task.values()) if per_task else 0,
        "k_max": max(per_task.values()) if per_task else 0,
        "effective_mean": _r(eff), "ci_low": _r(lo), "ci_high": _r(hi), "half_width": _r(half),
        "ci_plain": [_r(plain_lo), _r(plain_hi)],
        "tasks_for_target": (math.ceil(len(tm) * (half / TARGET_HALF_WIDTH) ** 2)
                             if half else None),
        "sample_sd": _r(mean(sds)),
        "rubric_mean": _r(mean(task_means(scored, "rubric_score").values())),
        "hard_fail_rate": _rate(scored, lambda r: r["hard_failed"]),
        "clean_sheet_rate": _rate(scored, lambda r: r["clean"]),
        "submit_rate": _rate(scored, lambda r: r["termination"] == "submit"),
        "implicit_submit_rate": _rate(scored, lambda r: r["implicit_submit"]),
        "terminations": dict(sorted(terminations.items())),
        "steps_median": _r(_pctl([r["steps"] for r in rows], 0.5), 1),
        "steps_p90": _r(_pctl([r["steps"] for r in rows], 0.9), 1),
        "tool_calls": calls,
        "invalid_call_rate": _r(sum(r["invalid_calls"] for r in rows) / calls, 4) if calls else None,
        "repaired_call_rate": (_r(sum(r.get("repaired_calls", 0) for r in rows) / calls, 4)
                               if calls else None),
        "fault_rate": _r(sum(r["failed_calls"] for r in rows) / calls, 4) if calls else None,
        "recovery_rate": _r(sum(r["recovered"] for r in rows) / faults, 4) if faults else None,
        "coordinate_share": _r(coord / (coord + sem), 4) if coord + sem else None,
        "run_check_mean": _r(mean(r["run_check_uses"] for r in rows)),
        "check_delta_mean": _r(mean(r["effective_score"] - r["effective_at_last_check"]
                                    for r in checked)),
        "check_delta_n": len(checked),
        "cost_per_sheet": _r(mean(costs), 4), "cost_total": _r(sum(costs), 4) if costs else None,
        "priced": len(costs),
        "output_tokens_mean": _r(mean(r["output_tokens"] for r in rows), 0),
        "input_tokens_mean": _r(mean(r["input_tokens"] for r in rows), 0),
        "elapsed_median_s": _r((_pctl([r["elapsed_ms"] or 0 for r in rows], 0.5) or 0) / 1000, 1),
    }
    out["per_check"] = per_check(scored)
    out["taxonomy"] = taxonomy(scored)
    out["tool_errors"] = dict(sorted(sum((Counter(e["errors"]) for e in scored), Counter()).items()))
    out["by_task_type"] = split(scored, "task_type")
    out["by_sheets"] = split(scored, "sheets")
    out["by_group"] = by_group(scored)
    # per task, for the board's cost-subset tables: a full run re-scored on a subset's tasks (2026-11-04)
    out["task_means"] = {t: _r(tm[t], 4) for t in tasks}
    out["task_types"] = {t: types[t] for t in tasks}
    return out


def per_check(eps: Sequence[dict]) -> Dict[str, dict]:
    acc: Dict[str, dict] = {}
    for e in eps:
        for cid, c in e["checks"].items():
            a = acc.setdefault(cid, {"name": c["name"], "weight": c["weight"], "credits": []})
            a["credits"].append(c["credit"])
    return {cid: {"name": a["name"], "weight": a["weight"], "n": len(a["credits"]),
                  "mean_credit": _r(mean(a["credits"]), 4),
                  "pass_rate": _r(sum(v >= 1.0 for v in a["credits"]) / len(a["credits"]), 4)}
            for cid, a in sorted(acc.items())}


def taxonomy(eps: Sequence[dict]) -> Dict[str, dict]:
    """Per category: the share of episodes with at least one such finding,
    findings per episode, and the codes behind them."""
    n = len(eps)
    out = {}
    for cat, codes in TAXONOMY:
        counts = Counter()
        hit = 0
        for e in eps:
            mine = [c for c in e["findings"] if CATEGORY_OF.get(c) == cat]
            counts.update(mine)
            hit += bool(mine)
        out[cat] = {"episodes": _r(hit / n, 4) if n else None,
                    "per_episode": _r(sum(counts.values()) / n, 3) if n else None,
                    "codes": {c: counts[c] for c in codes if counts[c]}}
    return out


def split(eps: Sequence[dict], field: str) -> Dict[str, dict]:
    by: Dict[str, List[dict]] = {}
    for e in eps:
        by.setdefault(str(e["row"][field]), []).append(e)
    return {k: {"n": len(v), "effective_mean": _r(mean(task_means(v).values())),
                "hard_fail_rate": _rate(v, lambda r: r["hard_failed"])}
            for k, v in sorted(by.items())}


def by_group(eps: Sequence[dict]) -> Dict[str, dict]:
    """The real-sheet question groups (``tasks.types.REAL_GROUPS``) a row's
    episodes fall in, in board order: each with its types, episode and task
    counts, effective mean over tasks, 95% bootstrap interval over tasks
    within type, and hard-fail rate.  Empty for a row on the seeded or probe
    sets, whose task types have no group."""
    by: Dict[str, List[dict]] = {}
    for e in eps:
        key = REAL_GROUP_OF.get(str(e["row"]["task_type"]))
        if key:
            by.setdefault(key, []).append(e)
    out: Dict[str, dict] = {}
    for key, _, _ in REAL_GROUPS:
        v = by.get(key)
        if not v:
            continue
        tm, types = task_means(v), task_types(v)
        tasks = sorted(tm)
        lo, hi = bootstrap([tm[t] for t in tasks], [types[t] for t in tasks])
        out[key] = {"name": REAL_GROUP_NAMES[key], "types": sorted({types[t] for t in tasks}),
                    "n": len(v), "n_tasks": len(tm), "effective_mean": _r(mean(tm.values())),
                    "ci_low": _r(lo), "ci_high": _r(hi),
                    "half_width": _r(None if lo is None else (hi - lo) / 2),
                    "hard_fail_rate": _rate(v, lambda r: r["hard_failed"])}
    return out


def group_columns(rows: Iterable[dict]) -> List[str]:
    """The question groups any of ``rows`` has numbers for, in board order."""
    return [k for k, _, _ in REAL_GROUPS if any(k in (g.get("by_group") or {}) for g in rows)]


def _group_cell(c: Optional[dict]) -> str:
    """A group's cell: effective mean ± 95% half-width (n tasks), since a row
    drawn before the per-group draw holds other counts than 25 a group."""
    return f"{_f(c['effective_mean'])} ± {_f(c['half_width'])} (n {c['n_tasks']})" if c else "–"


def paired(a: Sequence[dict], b: Sequence[dict]) -> Optional[dict]:
    """effective(a) - effective(b) over the tasks both ran, with a bootstrap
    interval; None when they share no task."""
    sa = [e for e in a if e["row"]["termination"] != "error"]
    ma = task_means(sa)
    mb = task_means([e for e in b if e["row"]["termination"] != "error"])
    shared = sorted(set(ma) & set(mb))
    if not shared:
        return None
    diffs = [ma[t] - mb[t] for t in shared]
    types = task_types(sa)
    lo, hi = bootstrap(diffs, [types[t] for t in shared])
    return {"gap": _r(mean(diffs)), "ci_low": _r(lo), "ci_high": _r(hi), "n_tasks": len(shared),
            "separated": bool(lo is not None and (lo > 0 or hi < 0))}


def rank_key(g: dict) -> Tuple:
    inf = float("inf")
    return (-(g["effective_mean"] if g["effective_mean"] is not None else -inf),
            g["hard_fail_rate"] if g["hard_fail_rate"] is not None else inf,
            g["invalid_call_rate"] if g["invalid_call_rate"] is not None else inf,
            g["cost_per_sheet"] if g["cost_per_sheet"] is not None else inf, g["label"])


# ------------------------------------------------------------------- report

def current_versions(taskset: Optional[str] = None) -> dict:
    """The versions a run on ``taskset`` is judged against: its set's own
    generator (``taskset.current_generator``), the spec, and its verifier
    (``taskset.current_verifier``: the D1 verifier, or a probe set's checks)."""
    from roaddraft.eval.taskset import current_generator, current_verifier
    from roaddraft.tasks.spec_v1 import SPEC_VERSION, spec_hash
    return {"spec_version": SPEC_VERSION, "spec_hash": spec_hash(),
            "generator_version": current_generator(taskset),
            "verifier_version": current_verifier(taskset)}


def set_ids(taskset: str, levels: Iterable[str] = ("explicit",)) -> set:
    """The current task ids of a board set: a probe set's from its task texts at the run's prompt ``levels``
    (a vague pilot is its own id, 2026-11-08), the others' from the manifest (a D1 task is one id at every
    level)."""
    from roaddraft.eval.taskset import is_probe, load
    if is_probe(taskset):
        from roaddraft.eval.probe_tasks import current_ids, probes_of
        probes = probes_of(taskset)
        return set().union(*(current_ids(probes, level=lv) for lv in (set(levels) or {"explicit"})))
    return {r["task_id"] for r in load(taskset)["tasks"]}


def _subset_ids_at(taskset: str, ids: Iterable[str], levels: Iterable[str]) -> List[str]:
    """A cost subset's ids (the explicit ids of a probe set) as the run's ``levels`` name them, in the
    subset's order (the board's bootstrap resamples in that order, so a re-scored row is stable)."""
    from roaddraft.eval.taskset import is_probe, load
    ids, levels = list(ids), set(levels)
    if not is_probe(taskset) or "vague" not in levels:
        return ids
    rows = {r["task_id"]: r for r in load(taskset)["tasks"]}
    out = [rows[i]["vague_task_id"] for i in ids if i in rows and rows[i].get("vague_task_id")]
    return out + (ids if "explicit" in levels else [])


def _subset_at(taskset: str, ids: Iterable[str], levels: Iterable[str]) -> set:
    """A cost subset's ids (the explicit ids of a probe set) as the run's ``levels`` name them."""
    return set(_subset_ids_at(taskset, ids, levels))


def coverage(taskset: Optional[str], task_ids: Iterable[str], subset: Optional[str] = None,
             levels: Iterable[str] = ("explicit",)) -> Optional[dict]:
    """How much of what it ran on a run holds: ``tasks_run``, ``tasks_in_set`` (the set's tasks, or its cost
    subset's when the run declared one), ``missing`` (those the run has not run) and ``foreign`` (the run's ids
    the set no longer has: a changed or removed task, a redrawn set).  Every board set is held to it since
    2026-11-04 (before, only the probe sets: the seeded and real sets ranked a draw).  None for a set that is
    not on the board.  ``levels`` are the run's prompt levels, which name a probe task's id."""
    if taskset is None or taskset not in LEADERBOARD_SETS:
        return None
    levels = tuple(levels)
    now, run = set_ids(taskset, levels), set(task_ids)
    out = {"tasks_run": len(run), "tasks_in_set": len(now)}
    if subset:
        from roaddraft.eval.subsets import subset_ids
        try:
            target = _subset_at(taskset, subset_ids(taskset, subset), levels)
        except ValueError:
            target = set()
        out.update(subset=subset, set_size=len(now), tasks_in_set=len(target),
                   subset_known=bool(target), subset_stale=sorted(target - now))
        now = target
    out.update(missing=sorted(now - run), foreign=sorted(run - now))
    pages = image_ids(taskset) & now
    if pages and set(out["missing"]) == pages:
        # every text pilot and no image pilot: a text-only model's run (Robert, 2026-11-10: "mark any hard
        # pilots that are text only as such, do not move off the board"); it ranks, marked, on its text pilots
        out.update(missing=[], text_only={"tasks": len(now - pages), "of": len(now), "images_not_run": len(pages)})
    return out


def image_ids(taskset: str) -> set:
    """The ids, at either prompt level, of a probe set's tasks that come with a page (a scan, a marked-up
    PDF): the pilots a text-only model cannot be given.  Empty for a set without any."""
    from roaddraft.eval.taskset import is_probe, load
    if not is_probe(taskset):
        return set()
    return {r[k] for r in load(taskset)["tasks"] if r.get("attachments")
            for k in ("task_id", "vague_task_id") if r.get(k)}


def _ids(ids: Sequence[str], limit: int = 6) -> str:
    shown = ", ".join(f"`{i}`" for i in ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def partial_reason(cov: dict, errors: int = 0, unfinished: int = 0) -> str:
    """Why a run is partial and not scored: tasks it did not run, episodes that ended in error, episodes
    with no end record (Robert, 2026-11-04: runs that end early or fail are partial and unscorable)."""
    of = f"its cost subset's {cov['tasks_in_set']}" if cov.get("subset") else f"the set's {cov['tasks_in_set']}"
    parts = [f"covers {cov['tasks_run']} of {of} tasks"]
    if cov.get("foreign"):
        parts.append(f"{len(cov['foreign'])} task(s) the set no longer has")
    if errors:
        parts.append(f"{errors} episode(s) ended in error")
    if unfinished:
        parts.append(f"{unfinished} episode(s) unfinished")
    return ("partial, not scored: " + "; ".join(parts)
            + "; a row ranks once the run holds every task with none in error or unfinished")


def run_partial(cov: Optional[dict], errors: int, unfinished: int) -> bool:
    return cov is not None and bool(cov["missing"] or cov["foreign"] or errors or unfinished
                                    or (cov.get("subset") and not cov.get("subset_known")))


def _run_meta(run_dir: Path) -> dict:
    p = run_dir / "run.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            return {}
    return {}


def build(run_dir, reverify: bool = False, check_delta: bool = True) -> dict:
    """The whole report for one run folder, as the dict ``summary.json`` holds."""
    run_dir = Path(run_dir)
    files = sorted((run_dir / "episodes").glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"{run_dir}: no episodes under {run_dir / 'episodes'}")
    eps, incomplete = [], []
    for f in files:
        e = load_episode(f, reverify=reverify, check_delta=check_delta)
        (eps.append(e) if e else incomplete.append(f.name))
    meta = _run_meta(run_dir)
    taskset = (meta.get("spec") or {}).get("taskset")
    groups: Dict[Tuple, List[dict]] = {}
    for e in eps:
        groups.setdefault(group_key(e["row"]), []).append(e)
    rows = [summarize_group(key_dims(k), v) for k, v in groups.items()]
    order = sorted(range(len(rows)), key=lambda i: rank_key(rows[i]))
    keys = list(groups)
    rows = [rows[i] for i in order]
    keys = [keys[i] for i in order]
    for i, g in enumerate(rows):
        g["rank"] = i + 1
        g["vs_next"] = paired(groups[keys[i]], groups[keys[i + 1]]) if i + 1 < len(rows) else None
    gaps = []
    for name, dim, a, b in GAPS:
        idx = GROUP_DIMS.index(dim)
        for ka in keys:
            if ka[idx] != a:
                continue
            for kb in keys:
                if kb == ka or (b is not None and kb[idx] != b) or kb[idx] == a:
                    continue
                if any(ka[j] != kb[j] for j in range(len(ka)) if j != idx):
                    continue
                p = paired(groups[ka], groups[kb])
                if p:
                    other = key_dims(ka)
                    gaps.append({"gap_name": name, "dimension": dim, "a": a, "b": kb[idx],
                                 "row": group_label(other).replace(f" · {a}", ""), **p})
    versions = {f: sorted({str(e["row"][f]) for e in eps})
                for f in ("spec_version", "spec_hash", "generator_version", "verifier_version",
                          "harness_version")}
    now = current_versions(taskset)
    subset = (meta.get("spec") or {}).get("subset")
    cov = coverage(taskset, (e["row"]["task_id"] for e in eps), subset,
                   sorted({e["row"].get("level") or "explicit" for e in eps}))
    errors = sum(1 for e in eps if e["row"]["termination"] == "error")
    partial = run_partial(cov, errors, len(incomplete))
    held = ["spec_hash", "generator_version", "verifier_version"]
    if cov is not None:   # a probe run is held to its task ids, not the set's hash
        held.remove("generator_version")
    stale = [f"{f} {', '.join(versions[f])} (current {now[f]})"
             for f in held if versions[f] != [str(now[f])]]
    summary = {
        "report_version": REPORT_VERSION, "run_id": run_dir.name, "taskset": taskset,
        "episodes": len(eps), "incomplete": incomplete,
        "reverified": bool(reverify), "versions": versions, "current_versions": now,
        "stale": stale, "coverage": cov, "partial": partial, "errored_episodes": errors,
        "partial_reason": partial_reason(cov, errors, len(incomplete)) if partial else None,
        "route": ((meta.get("spec") or {}).get("provider_options") or {}).get("base_url"),
        "cost_subset": ({"tag": subset, "tasks": cov["tasks_in_set"], "set_size": cov["set_size"]}
                        if subset and cov and not partial else None),
        "pins": meta.get("pins"), "harness_version": meta.get("harness_version"),
        "prices_checked": sorted({e["row"]["prices_checked"] for e in eps
                                  if e["row"]["prices_checked"]}),
        "bootstrap": {"resamples": BOOTSTRAP, "seed": SEED, "over": "tasks within task type"},
        "target_half_width": TARGET_HALF_WIDTH,
        "rows": rows, "gaps": gaps,
    }
    summary["publish_problems"] = publish_problems(summary)
    summary["_episodes"] = eps  # dropped before writing; the CSVs read it
    return summary


def publish_problems(summary: dict) -> List[str]:
    """Why a run may not be ranked: the plan publishes only on a frozen spec,
    never reports the dev set, and wants one verifier per run."""
    out = []
    drafts = [v for v in summary["versions"]["spec_version"] if v.startswith("draft")]
    if drafts:
        out.append(f"spec {', '.join(drafts)} is a draft; the leaderboard ranks only a frozen spec")
    if summary.get("taskset") in NEVER_REPORTED:
        out.append(f"{summary['taskset']} is a development set and is never reported")
    elif summary.get("taskset") is None:
        out.append("the run has no run.json naming its task set")
    if len(summary["versions"]["verifier_version"]) > 1 or len(summary["versions"]["spec_hash"]) > 1:
        out.append("episodes were scored under more than one verifier or spec; report with --reverify")
    elif summary["stale"]:
        out.append("scored under an older spec or verifier: " + "; ".join(summary["stale"]))
    cov = summary.get("coverage")
    if cov and cov["foreign"]:
        out.append(f"{len(cov['foreign'])} of the run's {cov['tasks_run']} task ids are not in the "
                   f"current set (a changed or removed task text): {_ids(cov['foreign'])}")
    if summary["incomplete"]:
        out.append(f"{len(summary['incomplete'])} episodes have no end record; resume the run")
    if cov and cov.get("subset"):
        from roaddraft.eval.subsets import route_allowed
        if not cov.get("subset_known"):
            out.append(f"cost subset {cov['subset']!r} is not defined for {summary.get('taskset')} "
                       "(benchmarks/tasksets/cost-subsets.json)")
        elif cov.get("subset_stale"):
            out.append(f"cost subset {cov['subset']!r} names {len(cov['subset_stale'])} task(s) the set no "
                       "longer has; the subset must be drawn again with the set")
        if not route_allowed(summary.get("route")):
            out.append(f"a cost-subset run ranks only from a Runpod route (Robert, 2026-11-04); this one ran "
                       f"on {summary.get('route') or 'no recorded endpoint'}")
    return out


# ----------------------------------------------------------------- render

def _f(x: Optional[float], digits: int = 1) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def _p(x: Optional[float]) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def _usd(x: Optional[float]) -> str:
    return "–" if x is None else (f"${x:.3f}" if x < 1 else f"${x:.2f}")


def _short(name: Optional[str], width: int = 40) -> str:
    """A check's name cut at a word boundary for a table cell."""
    text = (name or "").split(":")[0].strip()
    if len(text) <= width:
        return text
    return text[:width].rsplit(" ", 1)[0].rstrip(",;(") + "…"


def _ci(g: dict) -> str:
    if g["ci_low"] is None:
        return "–"
    return f"{g['ci_low']:.1f}–{g['ci_high']:.1f}"


def render_markdown(s: dict) -> str:
    rows = s["rows"]
    L = [f"# Run `{s['run_id']}`", ""]
    v = s["versions"]
    L.append(f"Task set **{s.get('taskset') or '?'}** · {s['episodes']} episodes · spec "
             f"{', '.join(v['spec_version'])} ({', '.join(h[:19] for h in v['spec_hash'])}) · "
             f"generator {', '.join(v['generator_version'])} · verifier "
             f"{', '.join(v['verifier_version'])} · harness {', '.join(v['harness_version'])}"
             + (" · **re-scored with the current verifier**" if s["reverified"] else ""))
    L.append("")
    if s["publish_problems"]:
        L.append("> **Not rankable as it stands:** " + " ".join(
            f"{p[0].upper()}{p[1:]}." for p in s["publish_problems"]))
        L.append("")
    if s.get("partial"):
        c = s["coverage"]
        L.append(f"> **Partial:** covers {c['tasks_run']} of the set's {c['tasks_in_set']} tasks; "
                 "published and listed, ranked once the run holds them all. "
                 f"Not run: {_ids(c['missing'], 12)}.")
        L.append("")
    L += ["## Rows", "",
          "Effective score: 0 on a hard fail, else the rubric score; per task over its samples, "
          f"then over tasks. 95% CI: bootstrap over tasks within task type "
          f"({s['bootstrap']['resamples']:,} resamples, seed {s['bootstrap']['seed']}).", "",
          "| # | Row | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Submit | Steps (med / p90) "
          "| Invalid calls | Recovery | run_check | Cost / sheet | Tasks × k |",
          "|---:|---|---|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|"]
    for g in rows:
        k = f"{g['k_min']}" if g["k_min"] == g["k_max"] else f"{g['k_min']}–{g['k_max']}"
        L.append(f"| {g['rank']} | {g['label']} | {effort_cell(g)} | **{_f(g['effective_mean'])}** | {_ci(g)} | "
                 f"{_f(g['rubric_mean'])} | {_p(g['hard_fail_rate'])} | {_p(g['clean_sheet_rate'])} | "
                 f"{_p(g['submit_rate'])} | {_f(g['steps_median'], 0)} / {_f(g['steps_p90'], 0)} | "
                 f"{_p(g['invalid_call_rate'])} | {_p(g['recovery_rate'])} | "
                 f"{_f(g['run_check_mean'])} | {_usd(g['cost_per_sheet'])} | {g['n_tasks']} × {k}"
                 + (f" ({g['errors']} errored)" if g["errors"] else "") + " |")
    repaired = [g for g in rows if g.get("repaired_call_rate")]
    if repaired:
        L += ["", "Repaired calls (harness e3-v3): a one-item list where the schema takes one value "
              "was read as the value, noted to the model in the result's warnings, and is counted "
              "here and not as an invalid call: "
              + "; ".join(f"{g['label']} {_p(g['repaired_call_rate'])} of its calls" for g in repaired)
              + "."]
    seps = [(g, g["vs_next"]) for g in rows if g.get("vs_next")]
    if seps:
        L += ["", "Each row against the next, paired by task: "
              + "; ".join(f"#{g['rank']} − #{g['rank'] + 1} = {p['gap']:+.1f} "
                          f"({p['ci_low']:+.1f} to {p['ci_high']:+.1f}, "
                          f"{'separated' if p['separated'] else 'not separated'})"
                          for g, p in seps) + "."]
    # per check
    ids = sorted({cid for g in rows for cid in g["per_check"]})
    if ids:
        names = {}
        for g in rows:
            for cid, c in g["per_check"].items():
                names.setdefault(cid, (c["name"], c["weight"]))
        L += ["", "## Per-check credit", "",
              "Mean credit (0–1) over the episodes whose task has the check in scope; – where none did.",
              "", "![Per-check credit](per_check.svg)", "",
              "| Check | Weight | " + " | ".join(f"#{g['rank']}" for g in rows) + " |",
              "|---|---:|" + "---:|" * len(rows)]
        for cid in ids:
            name, weight = names[cid]
            short = _short(name)
            L.append(f"| {cid} {short} | {weight} | " + " | ".join(
                _f((g["per_check"].get(cid) or {}).get("mean_credit"), 2) for g in rows) + " |")
    # taxonomy
    L += ["", "## Failure taxonomy", "",
          "Share of episodes with at least one finding in the category (findings per episode).", "",
          "| Category | " + " | ".join(f"#{g['rank']}" for g in rows) + " | Codes |",
          "|---|" + "---:|" * len(rows) + "---|"]
    for cat in CATEGORIES:
        codes = Counter()
        for g in rows:
            codes.update(g["taxonomy"][cat]["codes"])
        L.append(f"| {cat} | " + " | ".join(
            f"{_p(g['taxonomy'][cat]['episodes'])} ({_f(g['taxonomy'][cat]['per_episode'], 1)})"
            for g in rows) + " | " + ", ".join(f"{c} {n}" for c, n in codes.most_common()) + " |")
    L += ["", "### Tool use and termination", "",
          "| | " + " | ".join(f"#{g['rank']}" for g in rows) + " |",
          "|---|" + "---:|" * len(rows)]
    L.append("| tool calls | " + " | ".join(str(g["tool_calls"]) for g in rows) + " |")
    L.append("| invalid-call rate | " + " | ".join(_p(g["invalid_call_rate"]) for g in rows) + " |")
    L.append("| other fault rate | " + " | ".join(_p(g["fault_rate"]) for g in rows) + " |")
    L.append("| recovery rate | " + " | ".join(_p(g["recovery_rate"]) for g in rows) + " |")
    L.append("| coordinate path share | " + " | ".join(_p(g["coordinate_share"]) for g in rows) + " |")
    L.append("| stopped without calling submit | " + " | ".join(
        _p(g.get("implicit_submit_rate")) for g in rows) + " |")
    L.append("| Δ effective after last run_check | " + " | ".join(
        (f"{g['check_delta_mean']:+.1f} (n {g['check_delta_n']})"
         if g["check_delta_mean"] is not None else "–") for g in rows) + " |")
    terms = sorted({t for g in rows for t in g["terminations"]})
    for t in terms:
        L.append(f"| ended {t} | " + " | ".join(str(g["terminations"].get(t, 0)) for g in rows) + " |")
    errs = sorted({t for g in rows for t in g["tool_errors"]})
    for t in errs:
        L.append(f"| error {t} | " + " | ".join(str(g["tool_errors"].get(t, 0)) for g in rows) + " |")
    if s["gaps"]:
        L += ["", "## Paired gaps", "", "| Gap | Row | a − b | Gap | 95% CI | Tasks | Separated |",
              "|---|---|---|---:|---|---:|---|"]
        for p in s["gaps"]:
            L.append(f"| {p['gap_name']} | {p['row']} | {p['a']} − {p['b']} | {p['gap']:+.1f} | "
                     f"{p['ci_low']:+.1f} to {p['ci_high']:+.1f} | {p['n_tasks']} | "
                     f"{'yes' if p['separated'] else 'no'} |")
    gkeys = group_columns(rows)
    if gkeys:
        L += ["", "## By question group", "",
              "The real-sheet types by question type (`tasks.types.REAL_GROUPS`), the way the probe "
              "board splits its tiers: effective mean over the group's tasks ± its 95% half-width "
              "(bootstrap over tasks within type), and the tasks it rests on.", "",
              "| Group | Types | " + " | ".join(f"#{g['rank']}" for g in rows) + " |",
              "|---|---|" + "---:|" * len(rows)]
        for k in gkeys:
            types = sorted({t for g in rows for t in ((g.get("by_group") or {}).get(k) or {}).get("types", [])})
            cells = [(g.get("by_group") or {}).get(k) for g in rows]
            L.append(f"| {k}: {REAL_GROUP_NAMES[k]} | {', '.join(types)} | "
                     + " | ".join(_group_cell(c) for c in cells) + " |")
    types = sorted({t for g in rows for t in g["by_task_type"]})
    if types:
        L += ["", "## By task type and sheet count", "",
              "| Task type | " + " | ".join(f"#{g['rank']}" for g in rows) + " |",
              "|---|" + "---:|" * len(rows)]
        sheets = sorted({n for g in rows for n in g["by_sheets"]})
        for t in types + [f"{n} sheet{'s' if n != '1' else ''}" for n in sheets]:
            if t.split()[-1] in ("sheet", "sheets"):
                cells = [g["by_sheets"].get(t.split()[0]) for g in rows]
            else:
                cells = [g["by_task_type"].get(t) for g in rows]
            L.append(f"| {t} | " + " | ".join(
                f"{_f(c['effective_mean'])} (n {c['n']})" if c else "–" for c in cells) + " |")
    L += ["", "## Interval sizing", "",
          f"The v0.1 target is a 95% half-width under {TARGET_HALF_WIDTH:g} points. Tasks needed "
          "assumes the half-width shrinks as 1/√tasks at this row's spread.", "",
          "| Row | Tasks | Half-width | Unstratified | Within-task SD | Tasks for the target |",
          "|---|---:|---:|---:|---:|---:|"]
    for g in rows:
        plain = g.get("ci_plain") or [None, None]
        ph = None if plain[0] is None else (plain[1] - plain[0]) / 2
        L.append(f"| {g['label']} | {g['n_tasks']} | {_f(g['half_width'])} | {_f(ph)} | "
                 f"{_f(g['sample_sd'])} | "
                 f"{g['tasks_for_target'] if g['tasks_for_target'] is not None else '–'} |")
    if s["prices_checked"]:
        L += ["", f"Prices from the table checked {', '.join(s['prices_checked'])}."]
    if s["incomplete"]:
        L += ["", f"{len(s['incomplete'])} episode files have no end record and are left out."]
    L += ["", f"_Generated by `python -m roaddraft.eval report` ({REPORT_VERSION}); do not edit._", ""]
    return "\n".join(L)


#: the sequential ramp (one hue, light to dark) the heatmap shades credit on
RAMP = ("#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
        "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b")
INK = {"light": ("#fcfcfb", "#0b0b0b", "#52514e"), "dark": ("#1a1a19", "#ffffff", "#c3c2b7")}


def _luminance(hex_color: str) -> float:
    def ch(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _ink_on(fill: str) -> str:
    """Whichever of white and near-black reads better on ``fill``."""
    return "#ffffff" if _contrast(fill, "#ffffff") >= _contrast(fill, "#0b0b0b") else "#0b0b0b"


def _x(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_svg(s: dict) -> str:
    """The per-check heatmap: one line per row, one column per check, mean
    credit shaded light (0) to dark (1) on a one-hue ramp, the value in the
    cell, a tooltip on each; dark mode runs the ramp the other way so low
    credit recedes into the dark surface."""
    rows = s["rows"]
    ids = sorted({cid for g in rows for cid in g["per_check"]})
    names: Dict[str, Tuple[str, Any]] = {}
    for g in rows:
        for cid, c in g["per_check"].items():
            names.setdefault(cid, (c["name"], c["weight"]))
    labels = [f"#{g['rank']}  {g['label']}" for g in rows]
    cw, ch, gap = 46, 26, 2
    left = min(380, 24 + 7 * max((len(t) for t in labels), default=10))
    top = 84
    width = max(left + len(ids) * (cw + gap) + 24, 640)
    grid_bottom = top + len(rows) * (ch + gap)
    key_cols = 3
    key_rows = math.ceil(len(ids) / key_cols)
    height = grid_bottom + 64 + key_rows * 18 + 24
    n = len(RAMP) - 1
    css = [".t{font:600 15px system-ui,-apple-system,sans-serif;fill:#0b0b0b}",
           ".s,.k{font:12px system-ui,-apple-system,sans-serif;fill:#52514e}",
           ".l{font:12px system-ui,-apple-system,sans-serif;fill:#0b0b0b}",
           ".h{font:600 11px system-ui,-apple-system,sans-serif;fill:#52514e}",
           ".v{font:600 11px system-ui,-apple-system,sans-serif}",
           ".bg{fill:#fcfcfb}.na{fill:#fcfcfb;stroke:#d9d8d4;stroke-dasharray:3 2}"]
    dark = [".t,.l{fill:#ffffff}", ".s,.k,.h{fill:#c3c2b7}", ".bg{fill:#1a1a19}",
            ".na{fill:#1a1a19;stroke:#4a4a46}"]
    for i, color in enumerate(RAMP):
        css.append(f".q{i}{{fill:{color}}}.w{i}{{fill:{_ink_on(color)}}}")
        dc = RAMP[n - i]
        dark.append(f".q{i}{{fill:{dc}}}.w{i}{{fill:{_ink_on(dc)}}}")
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="ttl dsc">',
         f'<title id="ttl">Per-check credit, run {_x(s["run_id"])}</title>',
         f'<desc id="dsc">Mean credit from 0 to 1 per check for each row of the run; the same '
         f'numbers are in per_check.csv.</desc>',
         "<style>" + "".join(css) + "@media (prefers-color-scheme: dark){"
         + "".join(dark) + "}</style>",
         f'<rect class="bg" width="{width}" height="{height}" rx="8"/>',
         f'<text class="t" x="16" y="28">Per-check credit · {_x(s["run_id"])}</text>',
         f'<text class="s" x="16" y="48">Mean credit (0–1) over the episodes whose task has the '
         f'check in scope · {_x(s.get("taskset") or "")} · {s["episodes"]} episodes</text>']
    for j, cid in enumerate(ids):
        x = left + j * (cw + gap) + cw / 2
        L.append(f'<text class="h" x="{x:.0f}" y="{top - 10}" text-anchor="middle">'
                 f'{_x(cid.replace("D1-", ""))}<title>{_x(cid)} {_x(names[cid][0])}</title></text>')
    for i, (g, label) in enumerate(zip(rows, labels)):
        y = top + i * (ch + gap)
        L.append(f'<text class="l" x="16" y="{y + ch / 2 + 4:.0f}">{_x(label)}</text>')
        for j, cid in enumerate(ids):
            x = left + j * (cw + gap)
            c = g["per_check"].get(cid)
            if not c or c["mean_credit"] is None:
                L.append(f'<g><rect class="na" x="{x}" y="{y}" width="{cw}" height="{ch}" rx="4"/>'
                         f'<text class="h" x="{x + cw / 2:.0f}" y="{y + ch / 2 + 4:.0f}" '
                         f'text-anchor="middle">–</text><title>{_x(label)} · {_x(cid)}: '
                         f'not in scope for any task of this row</title></g>')
                continue
            q = max(0, min(n, round(c["mean_credit"] * n)))
            tip = (f'{label} · {cid} {names[cid][0]}: mean credit {c["mean_credit"]:.2f}, '
                   f'full credit in {100 * (c["pass_rate"] or 0):.0f}% of {c["n"]} episodes')
            L.append(f'<g><rect class="q{q}" x="{x}" y="{y}" width="{cw}" height="{ch}" rx="4"/>'
                     f'<text class="v w{q}" x="{x + cw / 2:.0f}" y="{y + ch / 2 + 4:.0f}" '
                     f'text-anchor="middle">{c["mean_credit"]:.2f}</text>'
                     f'<title>{_x(tip)}</title></g>')
    # legend: the ramp, then the key to the check numbers
    ly = grid_bottom + 18
    L.append(f'<text class="k" x="16" y="{ly + 10}">0</text>')
    sw = 14
    for i in range(len(RAMP)):
        L.append(f'<rect class="q{i}" x="{32 + i * sw}" y="{ly}" width="{sw}" height="12"/>')
    lx = 32 + len(RAMP) * sw + 6
    L.append(f'<text class="k" x="{lx}" y="{ly + 10}">1 mean credit</text>')
    L.append(f'<rect class="na" x="{lx + 110}" y="{ly}" width="22" height="12" rx="3"/>'
             f'<text class="k" x="{lx + 138}" y="{ly + 10}">not in scope</text>')
    ky = ly + 34
    colw = (width - 32) / key_cols
    for idx, cid in enumerate(ids):
        col, r = divmod(idx, key_rows)
        L.append(f'<text class="k" x="{16 + col * colw:.0f}" y="{ky + r * 18}">'
                 f'{_x(cid.replace("D1-", ""))}  {_x(_short(names[cid][0], 38))} '
                 f'(weight {_x(names[cid][1])})</text>')
    L.append("</svg>")
    return "\n".join(L) + "\n"


def _csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def files(s: dict) -> Dict[str, str]:
    """The report's files by name."""
    rows = s["rows"]
    eps = s.get("_episodes") or []
    # a variant is a column only in a report that has one, so every other report's files are unchanged
    dims = list(GROUP_DIMS) + [d for d in VARIANT_DIMS if any(g["key"].get(d) for g in rows)]
    per_check_rows = [[g["rank"], *[g["key"].get(d) for d in dims], cid, c["name"], c["weight"], c["n"],
                       c["mean_credit"], c["pass_rate"]]
                      for g in rows for cid, c in g["per_check"].items()]
    tax_rows = []
    for g in rows:
        for cat, codes in TAXONOMY:
            t = g["taxonomy"][cat]
            for code in codes:
                tax_rows.append([g["rank"], *[g["key"].get(d) for d in dims], cat, code,
                                 t["codes"].get(code, 0), t["episodes"], t["per_episode"]])
        for err, n in g["tool_errors"].items():
            tax_rows.append([g["rank"], *[g["key"].get(d) for d in dims], "tool_use", err, n, None, None])
        for term, n in g["terminations"].items():
            tax_rows.append([g["rank"], *[g["key"].get(d) for d in dims], "termination", term, n,
                             None, None])
    ep_fields = list(eps[0]["row"]) if eps else []
    ep_fields += [d for d in VARIANT_DIMS if d not in ep_fields and any(d in e["row"] for e in eps)]
    out = {
        "summary.json": json.dumps({k: v for k, v in s.items() if not k.startswith("_")},
                                   indent=1, ensure_ascii=False) + "\n",
        "leaderboard.md": render_markdown(s),
        "per_check.svg": render_svg(s),
        "per_check.csv": _csv(["rank", *dims, "check", "name", "weight", "n", "mean_credit",
                               "pass_rate"], per_check_rows),
        "taxonomy.csv": _csv(["rank", *dims, "category", "code", "count", "episodes_share",
                              "per_episode"], tax_rows),
        "episodes.csv": _csv(ep_fields, ([e["row"].get(f) for f in ep_fields]
                                         for e in sorted(eps, key=lambda e: e["row"]["file"]))),
    }
    return out


def write(s: dict, out_dir) -> List[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in files(s).items():
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    return written


def publish(s: dict, report_dir, runs_root=RUNS_DIR, allow_unrankable: bool = False) -> Path:
    """Copy ``summary.json``, ``leaderboard.md`` and ``per_check.svg`` to
    ``benchmarks/runs/<run_id>/``; refuses a run that cannot be ranked unless
    asked, and then the copied summary still names the problems."""
    if s["publish_problems"] and not allow_unrankable:
        raise ValueError("not publishable: " + "; ".join(s["publish_problems"])
                         + " (pass --allow-unrankable to publish it marked as such)")
    dest = Path(runs_root) / s["run_id"]
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("summary.json", "leaderboard.md", "per_check.svg"):
        shutil.copy(Path(report_dir) / name, dest / name)
    return dest


# ------------------------------------------------------- the README board

README_BEGIN = "<!-- d1-leaderboard:begin -->"
README_END = "<!-- d1-leaderboard:end -->"


def published(runs_root=RUNS_DIR) -> List[dict]:
    out = []
    for p in sorted(Path(runs_root).glob("*/summary.json")):
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            continue
    return out


def _not_a_board(taskset: Optional[str]) -> str:
    return (f"run on {taskset}, not a leaderboard set "
            f"({', '.join(LEADERBOARD_SETS)})")


def _pilot_count() -> str:
    """How many pilots ``hard-pilots`` holds, from its manifest ("the" when unread)."""
    try:
        from roaddraft.eval.taskset import load
        return f"the {len(load('hard-pilots')['tasks'])}"
    except (OSError, ValueError, KeyError):
        return "the"


def row_level(taskset: Optional[str], key: dict) -> Optional[str]:
    """The prompt level a row ranks under on ``taskset``'s board: None on a set whose
    tasks each have one prompt (``ONE_PROMPT_SETS``)."""
    return None if taskset in ONE_PROMPT_SETS else key.get("level", "explicit")


def board(summaries: Sequence[dict]) -> dict:
    """Ranked rows across published runs, one board per leaderboard set
    (``boards``): model rows from rankable runs on that set; harness agents
    (oracle, scripted, null) are kept as reference rows; every other published
    run is listed with its reasons.  A set's prompt levels rank apart: its
    ``ranked``, ``headline`` and ``subsets`` are the vague-prompt rows (the
    board's focus, ``BOARD_LEVELS[0]``) and ``other_prompts`` holds the same
    for each other level, ``explicit``; a set in ``ONE_PROMPT_SETS`` has one
    ranking and ``prompt`` None.  The top-level ``headline``, ``ranked`` and
    ``reference`` are d1-test's vague-prompt board."""
    levels = (None,) + BOARD_LEVELS
    per: Dict[str, Dict[str, Any]] = {
        name: {"ranked": {lv: [] for lv in levels}, "reference": [],
               "subset": {lv: {} for lv in levels}} for name in LEADERBOARD_SETS}
    full: Dict[str, Dict[Optional[str], List[Tuple[dict, dict]]]] = {
        name: {lv: [] for lv in levels} for name in LEADERBOARD_SETS}
    others = []
    for s in summaries:
        taskset = s.get("taskset")
        partial = bool(s.get("partial"))
        sub = s.get("cost_subset")
        rankable = not s.get("publish_problems") and taskset in LEADERBOARD_SETS and not partial
        if not rankable:
            reasons = list(s.get("publish_problems") or [])
            if taskset not in LEADERBOARD_SETS and not any("development" in r for r in reasons):
                reasons.append(_not_a_board(taskset))
            if partial:
                reasons.append(s.get("partial_reason") or partial_reason(s["coverage"]))
            others.append({"run_id": s["run_id"], "taskset": s.get("taskset"),
                           "episodes": s.get("episodes"), "reasons": reasons,
                           "partial": s.get("coverage") if partial else None,
                           "rows": [{"label": g["label"], "effort": effort_cell(g),
                                     "effective_mean": g["effective_mean"],
                                     "half_width": g["half_width"], "n_tasks": g["n_tasks"],
                                     "k_max": g["k_max"]} for g in s.get("rows") or []]})
            continue
        for g in s.get("rows") or []:
            row = {**{k: g[k] for k in ("label", "key", "effective_mean", "ci_low", "ci_high",
                                         "half_width", "rubric_mean", "hard_fail_rate",
                                         "clean_sheet_rate", "invalid_call_rate", "cost_per_sheet",
                                         "n_tasks", "k_min", "k_max")},
                   "effort": effort_cell(g), "run_id": s["run_id"],
                   "spec_version": ", ".join(s["versions"]["spec_version"]),
                   "by_group": {k: {f: c.get(f) for f in ("effective_mean", "half_width", "n_tasks",
                                                          "hard_fail_rate")}
                                for k, c in (g.get("by_group") or {}).items()}}
            kind = "reference" if g["key"].get("provider") == "harness" else "ranked"
            level = row_level(taskset, g["key"])
            text = (s.get("coverage") or {}).get("text_only")
            if text and kind == "ranked":   # marked, and kept on the board (Robert, 2026-11-10)
                row["text_only"] = text
                row["label"] += f" · text only ({text['tasks']} of {text['of']} pilots)"
            if sub:   # a cost-subset run: ranked in its own table, tagged (Robert, 2026-11-04)
                if kind == "ranked":
                    row["scored_as"] = (f"subset run ({sub['tasks']} of {sub['set_size']})" if not text else
                                        f"subset run, its {text['tasks']} text pilots (no image pilot run)")
                    per[taskset]["subset"].setdefault(level, {}).setdefault(sub["tag"], []).append(row)
                continue
            if kind == "reference":   # the harness's own agents: one list, whatever the level
                per[taskset]["reference"].append(row)
                continue
            per[taskset]["ranked"].setdefault(level, []).append(row)
            if g.get("task_means") and not text:   # a text-only run lacks the subset's image pilots
                full[taskset].setdefault(level, []).append((row, g))

    def one_ranking(name: str, level: Optional[str]) -> dict:
        ranked = sorted(per[name]["ranked"].get(level, []), key=rank_key)
        for i, r in enumerate(ranked):
            r["rank"] = i + 1
        headline = None
        if ranked:
            b = ranked[0]
            prompt = f" with the {level} prompt" if level else ""
            headline = (f"best model {b['effective_mean']:.1f}/100 on {name}{prompt} "
                        f"({b['label']}, 95% CI {b['ci_low']:.1f}–{b['ci_high']:.1f}, "
                        f"hard-fail {_p(b['hard_fail_rate'])})")
        return {"headline": headline, "ranked": ranked,
                "subsets": {tag: subset_table(name, tag, rows, full[name].get(level, []), level)
                            for tag, rows in sorted(per[name]["subset"].get(level, {}).items())}}

    boards = {}
    for name in LEADERBOARD_SETS:
        ref = per[name]["reference"]
        if name in ONE_PROMPT_SETS:
            focus, rest = None, ()
        else:
            focus = BOARD_LEVELS[0]
            seen = [lv for lv in per[name]["ranked"] if lv and lv != focus and per[name]["ranked"][lv]]
            rest = list(BOARD_LEVELS[1:]) + [lv for lv in seen if lv not in BOARD_LEVELS]
        main_one = one_ranking(name, focus)
        other = {lv: one_ranking(name, lv) for lv in rest}
        for lv, o in other.items():
            o["groups"] = group_columns(o["ranked"] + ref)
        boards[name] = {"title": SET_TITLES.get(name, name), "prompt": focus, **main_one,
                        "reference": ref, "groups": group_columns(main_one["ranked"] + ref),
                        "other_prompts": other}
    main = boards[LEADERBOARD_SET]
    lvs = [None] if all(n in ONE_PROMPT_SETS for n in LEADERBOARD_SETS) else list(BOARD_LEVELS)
    return {"report_version": REPORT_VERSION, "leaderboard_set": LEADERBOARD_SET,
            "leaderboard_sets": list(LEADERBOARD_SETS),
            "overall": {lv or "": overall(boards, lv) for lv in lvs},
            "headline": main["headline"], "ranked": main["ranked"],
            "reference": main["reference"], "boards": boards, "others": others,
            "groups": [{"key": k, "name": n, "types": list(ts)} for k, n, ts in REAL_GROUPS]}


def _set_ranking(one: dict, level: Optional[str]) -> List[dict]:
    """A set's ranked rows at ``level`` (its focus ranking or one of ``other_prompts``)."""
    if one.get("prompt") == level:
        return one.get("ranked") or []
    return ((one.get("other_prompts") or {}).get(level) or {}).get("ranked") or []


#: each set's weight in the overall score (Robert, 2026-11-13: the real sheets and the hard pilots
#: count for more than the seeded sheets)
OVERALL_WEIGHTS = {"d1-test": 1.0, "d1-real": 2.0, "hard-pilots": 2.0, "d1-test-hard": 1.0,
                   "d1-real-hard": 2.0}


def overall(boards: Dict[str, dict], level: Optional[str]) -> dict:
    """One score per model across every leaderboard set at ``level`` (Robert, 2026-11-13): the mean of its
    full-set effective scores weighted by ``OVERALL_WEIGHTS``, ± the sets' 95% half-widths combined
    with the same weights (root-sum-square, the sets being independent draws).  A model ranks only with a
    full-set row on every set; cost-subset rows are other tasks and do not count.  A model short of a set is
    listed in ``partial`` with the sets it has and no overall score."""
    rows: Dict[str, dict] = {}
    for name in LEADERBOARD_SETS:
        for r in _set_ranking(boards.get(name) or {}, level):
            k = json.dumps(r["key"], sort_keys=True)
            o = rows.setdefault(k, {"key": r["key"], "label": None, "effort": r.get("effort"), "sets": {}})
            if not r.get("text_only") and o["label"] is None:
                o["label"] = r["label"]
            o["sets"][name] = {"effective_mean": r["effective_mean"], "half_width": r.get("half_width"),
                               "rank": r.get("rank"), "run_id": r["run_id"],
                               "text_only": bool(r.get("text_only"))}
    ranked, partial = [], []
    w = [OVERALL_WEIGHTS.get(s, 1.0) for s in LEADERBOARD_SETS]
    W = sum(w)
    for o in rows.values():
        o["label"] = o["label"] or group_label(o["key"])
        o["n_sets"] = len(o["sets"])
        cells = [o["sets"].get(s) for s in LEADERBOARD_SETS]
        if all(c and c["effective_mean"] is not None for c in cells):
            o["overall"] = _r(sum(wi * c["effective_mean"] for wi, c in zip(w, cells)) / W)
            hws = [c["half_width"] for c in cells]
            o["half_width"] = (None if any(h is None for h in hws)
                               else _r(math.sqrt(sum((wi * h) ** 2 for wi, h in zip(w, hws))) / W))
            ranked.append(o)
        else:
            o["overall"], o["half_width"] = None, None
            o["missing"] = [s for s in LEADERBOARD_SETS if s not in o["sets"]]
            partial.append(o)
    ranked.sort(key=lambda o: (-o["overall"], o["label"]))
    for i, o in enumerate(ranked):
        o["rank"] = i + 1
    partial.sort(key=lambda o: (-o["n_sets"], o["label"]))
    return {"sets": list(LEADERBOARD_SETS), "weights": dict(zip(LEADERBOARD_SETS, w)),
            "ranked": ranked, "partial": partial}


def _overall_md(ov: dict, level: Optional[str], readme: bool) -> List[str]:
    """The overall table at the head of a board: one score per model over every set."""
    sets = ov["sets"]
    prompt = f", {level} prompt" if level else ""
    L = [f"{'###' if readme else '##'} Overall: every set{prompt}", ""]
    if ov["ranked"]:
        b = ov["ranked"][0]
        hw = f" ± {_f(b['half_width'])}" if b["half_width"] is not None else ""
        L += [f"**Best model overall {b['overall']:.1f}/100{hw} ({b['label']}), the weighted mean of "
              f"its {len(sets)} set scores.**", ""]
    else:
        L += [f"No model has a full-set run on all {len(sets)} sets yet.", ""]
    wt = ov.get("weights") or {}
    head = "".join(f" `{s}` ×{wt.get(s, 1.0):g} |" for s in sets)
    L += ["| # | Model · mode · prompt | Effort | Overall | ± |" + head + " Sets |",
          "|---:|---|---|---:|---:|" + "---:|" * len(sets) + "---:|"]

    def cell(c: Optional[dict]) -> str:
        if not c:
            return "–"
        return _f(c["effective_mean"]) + (" †" if c["text_only"] else "")

    for o in ov["ranked"] + ov["partial"]:
        score = f"**{_f(o['overall'])}**" if o["overall"] is not None else "–"
        L.append(f"| {o.get('rank', '')} | {o['label']} | {o.get('effort') or '–'} | {score} "
                 f"| {_f(o['half_width'])} |" + "".join(f" {cell(o['sets'].get(s))} |" for s in sets)
                 + f" {o['n_sets']} of {len(sets)} |")
    L += ["", f"Overall = the weighted mean of the model's effective scores on the {len(sets)} sets below, "
          "each set's weight beside its name (Robert, 2026-11-13: the real plan sheets and the hard pilots "
          "count double the seeded sheets); ± is the sets' 95% half-widths combined with the same weights "
          "(root-sum-square). A model ranks "
          "here only with a full-set run on every set; cost-subset runs are other tasks and do not count, so "
          "a model short of a set is listed unranked with the sets it has. † a text-only `hard-pilots` row, "
          "scored on its text pilots alone."]
    return L


def rescore_on(g: dict, ids: Sequence[str]) -> Optional[dict]:
    """A full run's row scored on ``ids`` alone, from its per-task means: the effective mean and its interval
    (the board's bootstrap, within task type); None when the row lacks any of the tasks."""
    tm, types = g.get("task_means") or {}, g.get("task_types") or {}
    if not ids or any(i not in tm for i in ids):
        return None
    vals = [float(tm[i]) for i in ids]
    lo, hi = bootstrap(vals, [types.get(i, "") for i in ids])
    return {"effective_mean": _r(mean(vals)), "ci_low": _r(lo), "ci_high": _r(hi),
            "half_width": _r((hi - lo) / 2), "n_tasks": len(ids)}


def subset_table(taskset: str, tag: str, rows: Sequence[dict], full_rows: Sequence[Tuple[dict, dict]],
                 level: Optional[str] = None) -> dict:
    """One cost subset's ranking on a set: its subset runs beside every ranked full run re-scored on the same
    tasks, so the rows compare (a subset's mean weights its task types alike, the full set's by its mix).
    ``level`` is the table's prompt level: a probe set's subset is drawn on its explicit ids, and a vague
    full run's per-task means are keyed by the vague ids (2026-11-10: the hard-pilots vague table had
    dropped every full run)."""
    from roaddraft.eval.subsets import PER_TYPE, load_subsets, subset_ids
    try:
        ids = subset_ids(taskset, tag)
    except ValueError:
        ids = []
    ids = _subset_ids_at(taskset, ids, [level] if level else [])
    out = [dict(r) for r in rows]
    for row, g in full_rows:
        again = rescore_on(g, ids)
        if again:
            out.append({**row, **again, "rubric_mean": None, "hard_fail_rate": None, "clean_sheet_rate": None,
                        "invalid_call_rate": None, "cost_per_sheet": None, "by_group": {},
                        "scored_as": f"full run, re-scored on the subset's {len(ids)}"})
    out.sort(key=lambda r: (-(r["effective_mean"] or 0), -(r["ci_low"] or 0), r["label"]))
    for i, r in enumerate(out):
        r["rank"] = i + 1
    one = (load_subsets().get("subsets") or {}).get(taskset) or {}
    return {"tag": tag, "tasks": len(ids), "set_size": one.get("tasks_in_set"),
            "per_type": load_subsets().get("per_type", PER_TYPE), "rows": out}


def _subset_table_md(sub: dict) -> List[str]:
    L = ["| # | Model · mode · prompt | Effort | Effective | 95% CI | Tasks × k | Scored as | Run |",
         "|---:|---|---|---:|---|---|---|---|"]
    for r in sub["rows"]:
        k = f"{r['k_min']}" if r["k_min"] == r["k_max"] else f"{r['k_min']}–{r['k_max']}"
        L.append(f"| {r['rank']} | {r['label']} | {effort_cell(r)} | **{_f(r['effective_mean'])}** | {_ci(r)} "
                 f"| {r['n_tasks']} × {k} | {r['scored_as']} | `{r['run_id']}` |")
    return L


def _subset_intro(name: str, sub: dict, level: Optional[str] = None) -> str:
    prompt = f", {level} prompt" if level else ""
    return (f"**Cost subset `{sub['tag']}` on `{name}`{prompt}: partial runs, to save cost.** {sub['tasks']} of the set's "
            f"{sub['set_size']} tasks, {sub['per_type']} of each task type (every task of a smaller type), the "
            "fixed draw in `benchmarks/tasksets/cost-subsets.json`; only Runpod runs rank here, and only when "
            "they hold every task of the subset with none in error or unfinished. Each full run of the set is "
            f"re-scored on the same {sub['tasks']} tasks so the rows compare; a subset score is not comparable "
            "with a full-set score above.")


def _board_table(rows: Sequence[dict], numbered: bool = True, groups: Sequence[str] = ()) -> List[str]:
    """The board's table; ``groups`` adds a column per question group beside
    the blended score (the real board), each cell the group's effective mean
    ± its 95% half-width over the row's tasks in it (n)."""
    gh = "".join(f" {k.capitalize()} |" for k in groups)
    L = ["| # | Model · mode · prompt | Effort | Effective | 95% CI |" + gh
         + " Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |",
         "|---:|---|---|---:|---|" + "---:|" * len(groups) + "---:|---:|---:|---:|---:|---|---|"]
    for i, r in enumerate(rows):
        k = f"{r['k_min']}" if r["k_min"] == r["k_max"] else f"{r['k_min']}–{r['k_max']}"
        gc = "".join(f" {_group_cell((r.get('by_group') or {}).get(g))} |" for g in groups)
        L.append(f"| {r.get('rank', '') if numbered else ''} | {r['label']} | {effort_cell(r)} "
                 f"| **{_f(r['effective_mean'])}** "
                 f"| {_ci(r)} |" + gc + f" {_f(r['rubric_mean'])} | {_p(r['hard_fail_rate'])} | "
                 f"{_p(r['clean_sheet_rate'])} | {_p(r['invalid_call_rate'])} | "
                 f"{_usd(r['cost_per_sheet'])} | {r['n_tasks']} × {k} | `{r['run_id']}` |")
    return L


def group_legend(groups: Sequence[str]) -> str:
    """The line under a board with group columns: what each column holds."""
    parts = [f"{k.capitalize()} = {REAL_GROUP_NAMES[k]} ({', '.join(f'`{t}`' for t, g in REAL_GROUP_OF.items() if g == k)})"
             for k in groups]
    return ("Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe "
            "board's tiers; `d1-real` draws 25 tasks a group): " + "; ".join(parts)
            + ". Each cell is the effective mean over the row's tasks in that group ± its 95% "
            "half-width, with the number of tasks it rests on.")


def _level_heading(level: str, readme: bool) -> List[str]:
    """The heading of one prompt level's ranking within a set, and what that level is."""
    note = LEVEL_NOTES.get(level, f"the {level} prompt, ranked on its own.")
    return [f"{'####' if readme else '###'} {level.capitalize()} prompt", "",
            f"_{note[0].upper()}{note[1:]}_", ""]


def _ranking_md(one: dict, groups: Sequence[str], legend: bool = True) -> List[str]:
    """One ranking's headline, table and (once a set, ``legend``) group legend."""
    L = [f"**{one['headline'][0].upper()}{one['headline'][1:]}.**", ""]
    L += _board_table(one["ranked"], groups=groups)
    if groups and legend:
        L += ["", group_legend(groups)]
    return L


def _no_run(name: str) -> str:
    """What a set with no ranked row at either prompt level needs for its first one."""
    if name == LEADERBOARD_SET:
        return (f"No ranked run yet. A row needs a published run on `{name}` under a "
                "frozen spec (v0.1: spec v1, then `d1-variance` × 5 samples to size the "
                f"interval, then `{name}` × at least three models).")
    if name == "hard-pilots":
        return ("No ranked run yet. A row needs a published run on `hard-pilots` that covers "
                "every task of the current set (a run on part of it is published as partial and "
                "listed among the runs not ranked); each task scores 100 on a pass and 0 on a fail "
                "by its own check, "
                "whose source hash is the row's verifier version. The pilots that come with a "
                "page (23 of 112) need a model that takes images.")
    if name == "d1-test-hard":
        return ("No ranked run yet. A row needs a published run on `d1-test-hard` under a "
                "frozen spec (a one-task smoke run first, `--limit 1`).")
    return (f"No ranked run yet. A row needs a published run on `{name}` under a frozen "
            "spec, with the catalogue it was drawn from validated under the verifier "
            "that scores it (`d1-real-dev` first, for a smoke run).")


def eval_board_note(probe_board: str) -> str:
    """The line that says which board this is; ``probe_board`` is the probe board's path from here."""
    return ("The benchmark board: every published run on the eval sets, scored by the verifier "
            "(`roaddraft.eval`), one ranking per set. The 33 capability probes of Track P are a separate "
            f"board, closed 2026-10-27: [the probe board]({probe_board}).")


def level_board(b: dict, level: Optional[str] = None) -> dict:
    """``b`` as one prompt level's board: each set's ranking at ``level`` (the focus, vague, when None)
    with its subsets; the reference agents, which run at no level of their own, stay on the focus board."""
    focus = BOARD_LEVELS[0]
    level = level or focus
    boards = {}
    for name, one in (b.get("boards") or {}).items():
        others = one.get("other_prompts") or {}
        if one.get("prompt") in (level, None) and level == focus:
            view = {**one, "other_prompts": {}}
        else:
            o = others.get(level) or {"headline": None, "ranked": [], "subsets": {}}
            view = {"title": one["title"], "prompt": level, "headline": o.get("headline"),
                    "ranked": o.get("ranked") or [], "subsets": o.get("subsets") or {},
                    "reference": [], "groups": o.get("groups") or group_columns(o.get("ranked") or []),
                    "other_prompts": {}}
        view["levels_with_rows"] = sorted(lv for lv, o in others.items() if o.get("ranked") or o.get("subsets"))
        boards[name] = view
    return {**b, "boards": boards, "level": level}


def _board_files_line(level: str, readme: bool) -> str:
    """Where the other prompt levels' boards are, from this board."""
    here = "benchmarks/runs/" if readme else ""
    if level == BOARD_LEVELS[0]:
        links = ", ".join(f"[{lv} prompts]({here}{f})" for lv, f in LEVEL_BOARD_FILES.items())
        return (f"Vague prompts only: the request in a sentence, the board's focus. Every other prompt "
                f"level is ranked on a board of its own: {links}.")
    return (f"The {level}-prompt runs, ranked on their own: a score at the {level} level is not comparable "
            f"with one at the vague level, which is the main board's focus: [the main board]({here}LEADERBOARD.md).")


def render_board(b: dict, readme: bool = False, level: Optional[str] = None) -> str:
    """One prompt level's board: the main board (the vague prompt, the focus) when ``level`` is None, or the
    board of another level (``LEVEL_BOARD_FILES``), each set's ranking at that level."""
    focus = BOARD_LEVELS[0]
    main_board = level in (None, focus)
    level = level or focus
    view = level_board(b, level)
    L: List[str] = []
    if not readme:
        title = "# RoadDraft eval leaderboard" + ("" if main_board else f": {level} prompts")
        L += [title, "", eval_board_note("../leaderboard/TRACK_P.md"), "",
              _board_files_line(level, readme), ""]
        if main_board:
            L += ["![Effective score by model on each eval set](leaderboard.svg)", ""]
    else:
        L += [_board_files_line(level, readme), "",
              "![Effective score by model on each eval set](benchmarks/runs/leaderboard.svg)", ""]
    ov = (b.get("overall") or {}).get(level)
    if ov and (ov["ranked"] or ov["partial"]):
        L += _overall_md(ov, level, readme) + [""]
    boards = view.get("boards") or {LEADERBOARD_SET: {"title": SET_TITLES[LEADERBOARD_SET],
                                                       "headline": b["headline"],
                                                       "ranked": b["ranked"],
                                                       "reference": b["reference"]}}
    for n, (name, one) in enumerate(boards.items()):
        if n:
            L.append("")
        L += [f"{'###' if readme else '##'} `{name}`: {one['title']}", ""]
        groups = one.get("groups") or group_columns(one["ranked"] + one["reference"])
        if one["headline"]:
            L += _ranking_md(one, groups)
        elif not main_board:
            L += [f"No {level}-prompt run on `{name}`."]
        elif one.get("levels_with_rows"):
            L += [f"No vague-prompt run on `{name}` yet; its "
                  + " and ".join(f"{lv}-prompt" for lv in one["levels_with_rows"])
                  + " runs are ranked on their own board."]
        else:
            L += [_no_run(name)]
        if one.get("reference"):
            L += ["", "Reference agents on the same tasks (the harness's own checks, not ranked):",
                  ""]
            L += _board_table(one["reference"], numbered=False, groups=groups)
        for sub in (one.get("subsets") or {}).values():
            L += ["", _subset_intro(name, sub, level), ""] + _subset_table_md(sub)
    if not readme and main_board and b["others"]:
        L += ["", "## Published runs that are not ranked", ""]
        for o in b["others"]:
            part = o.get("partial")
            rows = "; ".join(f"{r['label']}"
                             + (f", effort {r['effort']}" if r.get("effort", "–") != "–" else "")
                             + ("" if part else f" {_f(r['effective_mean'])} ± {_f(r['half_width'])}")
                             + f" ({r['n_tasks']} tasks × {r['k_max']})" for r in o["rows"])
            tag = (f", **partial, not scored: {part['tasks_run']} of {part['tasks_in_set']} tasks**"
                   if part else "")
            L.append(f"- `{o['run_id']}` ({o['taskset']}, {o['episodes']} episodes{tag}): {rows}. "
                     f"Not ranked: {'; '.join(o['reasons'])}.")
    if readme:
        L += ["", "The full board, with the runs not ranked and why: "
              "[benchmarks/runs/LEADERBOARD.md](benchmarks/runs/LEADERBOARD.md). "
              "Generated by `scripts/make_leaderboard.py`; do not edit by hand."]
    else:
        L += ["", "Each set is its own ranking: `d1-test` is 100 held-out tasks from the seeded "
              "generator (one synthetic centerline per task); `d1-real` is 100 held-out tasks on "
              "the redrafted sample plan sheets (Caltrans, WFL, CFL, FDOT), 25 in each of four "
              "question groups (draft linework, letter alignment data, produce the sheet, notes and "
              "dimensions), each group a column beside the blended score; `hard-pilots` is "
              f"{_pilot_count()} harder-task pilots on the sample sheets, "
              "each graded pass (100) or fail (0) by its own check, with the share of its items "
              "done as the rubric column; `d1-test-hard` is 100 held-out seeded whole-sheet jobs "
              "(three to five curves on two or three sheets, a station equation on one in five: the "
              "plan sheet with its pavement, the alignment created from stated geometry and then "
              "drafted, the sheet file lettered through its base drawing); `d1-real-hard` is 100 "
              "tasks on the redrafted sheets, every whole job (a sheet drafted from its base files "
              "or annotated from blank, construction callouts included) and the heaviest "
              "whole-line tasks `d1-real` did not draw. Within a set the rows rank on that set "
              "alone; the overall table at the top is the one place a model's sets are averaged, the "
              "real sheets and the hard pilots weighted double.",
              "", "Each prompt level is its own board (Robert, 2026-11-08): this file ranks the "
              + ("vague-prompt runs (the request in a sentence, the way a PE would ask for it; what belongs on "
                 "the sheet is the drafter's to know), the main board and its focus"
                 if main_board else
                 f"{level}-prompt runs (the full brief, stating every standard the task is graded on)")
              + "; a score at one prompt level is not comparable with a score at the other. Every task "
              "has both prompts: a pilot's vague brief keeps what the drafter cannot know (the files, lines, "
              "stations and data given) and leaves its drafting standards to the drafter, graded by the "
              "lenient rules where the brief no longer states them.",
              "", "A run that misses a task of its set, or has an episode that ended in error or never "
              "finished, is partial and not scored: it is listed on the main board without a score. The one "
              "exception is a cost-subset run (`benchmarks/tasksets/cost-subsets.json`: five tasks of each "
              "task type, Runpod runs only, to save cost), ranked in a table of its own under its set beside "
              "the full runs re-scored on the same tasks; it too is partial and not scored if it misses a "
              "task of the subset or has an episode in error or unfinished. A `hard-pilots` run that holds "
              "every text pilot of its set or subset and none of the pilots that come with a page (a model "
              "that takes no images) is not partial: it stays in its table, marked **text only**, scored on "
              "its text pilots alone, which is not the same tasks as the rows beside it.",
              "", "Effective score: 0 on a hard fail, else the rubric score; per task over its "
              "samples, then over tasks; 95% CI a bootstrap over tasks within task type. Rows rank "
              "on the effective mean, then hard-fail rate, invalid-call rate and cost. Effort is the "
              "level the run set with `--effort`, else what the request body set, else the model's "
              "default marked (default), as read from its chat template or catalog (`roaddraft.effort`); "
              "plain default is one not looked up. A model run at two efforts is two rows.",
              "", "_Generated by `scripts/make_leaderboard.py` from `benchmarks/runs/*/summary.json`; "
              "do not edit._"]
    return "\n".join(L) + "\n"


EVAL_SVG_STYLE = """
text { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
.bg { fill: #fcfcfb; } .ink { fill: #0b0b0b; } .ink2 { fill: #52514e; } .rule { stroke: #b4b3ae; }
.track { fill: #f0efec; } .bar { fill: #2a78d6; } .ci { stroke: #104281; stroke-width: 1.5; }
@media (prefers-color-scheme: dark) {
  .bg { fill: #1a1a19; } .ink { fill: #ffffff; } .ink2 { fill: #c3c2b7; } .rule { stroke: #6b6a65; }
  .track { fill: #383835; } .bar { fill: #3987e5; } .ci { stroke: #b7d3f6; }
}
"""


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def render_board_svg(b: dict) -> str:
    """The main board as a picture: one panel per set at the vague prompt (the focus; the other
    levels are boards of their own, 2026-11-08), a bar per ranked row (effective score on a 0 to
    100 scale) with its 95% interval as a whisker; a set with no ranked run says so."""
    boards = (level_board(b).get("boards") if b.get("boards") else None) or {
        LEADERBOARD_SET: {"title": SET_TITLES[LEADERBOARD_SET], "ranked": b["ranked"]}}
    left, bar_x, bar_w, pitch, right_w = 16, 300, 360, 24, 150
    width = bar_x + bar_w + right_w
    y = 56
    body: List[str] = []
    panels = []
    for name, one in boards.items():
        level = one.get("prompt")
        rankings = [(level, one)] + [(lv, o) for lv, o in (one.get("other_prompts") or {}).items()
                                     if o["ranked"] or o.get("subsets")]
        for lv, r in rankings:
            prompt = f", {lv} prompt" if lv else ""
            panels.append((f"{name}{prompt}: {one['title']}", r.get("ranked") or []))
            for sub in (r.get("subsets") or {}).values():
                panels.append((f"{name}{prompt}: cost subset {sub['tag']}, partial to save cost "
                               f"({sub['tasks']} of {sub['set_size']} tasks)", sub["rows"]))
    for title, rows in panels:
        body.append(f'<text class="ink" x="{left}" y="{y}" font-size="13" font-weight="600">'
                    f'{_esc(title)}</text>')
        y += 10
        if not rows:
            y += 18
            body.append(f'<text class="ink2" x="{left}" y="{y}" font-size="12">no ranked run yet</text>')
            y += 14
        for r in rows:
            y += pitch
            cy = y - 7
            label = f"{r.get('rank', '')}. {r['label']}"
            if len(label) > 44:
                label = label[:43] + "…"
            x0 = bar_x + bar_w * max(0.0, min(100.0, r["effective_mean"])) / 100
            lo = bar_x + bar_w * max(0.0, min(100.0, r["ci_low"])) / 100
            hi = bar_x + bar_w * max(0.0, min(100.0, r["ci_high"])) / 100
            body += [f'<text class="ink" x="{left}" y="{y}" font-size="12">{_esc(label)}</text>',
                     f'<rect class="track" x="{bar_x}" y="{cy - 6}" width="{bar_w}" height="12"/>',
                     f'<rect class="bar" x="{bar_x}" y="{cy - 6}" width="{x0 - bar_x:.1f}" height="12"/>',
                     f'<line class="ci" x1="{lo:.1f}" y1="{cy}" x2="{hi:.1f}" y2="{cy}"/>',
                     f'<line class="ci" x1="{lo:.1f}" y1="{cy - 4}" x2="{lo:.1f}" y2="{cy + 4}"/>',
                     f'<line class="ci" x1="{hi:.1f}" y1="{cy - 4}" x2="{hi:.1f}" y2="{cy + 4}"/>',
                     f'<text class="ink" x="{bar_x + bar_w + 10}" y="{y}" font-size="12">'
                     f'{r["effective_mean"]:.1f} [{r["ci_low"]:.1f}–{r["ci_high"]:.1f}]</text>']
        y += 22
    height = y + 8
    axis = [f'<line class="rule" x1="{bar_x + bar_w * t // 100}" y1="40" x2="{bar_x + bar_w * t // 100}" '
            f'y2="{height - 8}" stroke-dasharray="2 3"/>' for t in (0, 50, 100)]
    axis += [f'<text class="ink2" x="{bar_x + bar_w * t // 100}" y="38" font-size="10" text-anchor="middle">{t}</text>'
             for t in (0, 50, 100)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
           f'height="{height}" role="img" aria-labelledby="title">',
           '<title id="title">RoadDraft eval leaderboard: effective score by model on each eval set</title>',
           f"<style>{EVAL_SVG_STYLE}</style>",
           f'<rect class="bg" width="{width}" height="{height}"/>',
           f'<text class="ink" x="{left}" y="24" font-size="17" font-weight="600">RoadDraft eval leaderboard</text>',
           f'<text class="ink2" x="{left}" y="40" font-size="11">effective score, 0 to 100, with its 95% interval; '
           'one ranking per eval set and prompt level, vague first</text>', *axis, *body, "</svg>"]
    return "\n".join(out) + "\n"


def replace_block(text: str, block: str) -> str:
    """``text`` with the README board between its markers replaced."""
    start, end = text.find(README_BEGIN), text.find(README_END)
    if start < 0 or end < start:
        raise ValueError(f"the README has no {README_BEGIN} ... {README_END} block")
    return text[:start + len(README_BEGIN)] + "\n" + block + text[end:]


__all__ = ["REPORT_VERSION", "LEADERBOARD_SETS", "SET_TITLES", "NEVER_REPORTED",
           "BOARD_LEVELS", "ONE_PROMPT_SETS", "LEVEL_NOTES", "LEVEL_BOARD_FILES", "level_board", "row_level",
           "TAXONOMY", "CATEGORIES", "CATEGORY_OF", "GROUP_DIMS", "VARIANT_DIMS", "GAPS",
           "LEADERBOARD_SET", "RUNS_DIR", "bootstrap", "tool_use", "load_episode",
           "effort_label", "effort_cell", "variant_of", "variant_label", "key_dims",
           "summarize_group", "by_group", "group_columns",
           "group_legend", "paired", "build", "publish_problems",
           "render_markdown", "files",
           "write", "publish", "published", "board", "render_board", "replace_block",
           "README_BEGIN", "README_END", "render_board_svg", "eval_board_note"]

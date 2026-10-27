"""The probe board (Track P) and its model cards, generated from the run folders.

This is the capability probe board, not the eval leaderboard: the 33 probes
were built for a quick read on what models of different sizes can do with the
tool surface, and the board was closed on 2026-10-27 (Robert) with eleven
rows. The benchmark board is ``benchmarks/runs/LEADERBOARD.md``, built by
``scripts/make_leaderboard.py`` from the eval harness ``roaddraft.eval``.

Research plan §3.3. A row is one model through ``roaddraft.runners`` in one
run folder: every episode it left under ``runs/<label>/<probe>/``, re-scored
from the document on disk against the current probe checks, so the board
moves when a check does and never because someone typed a number. The files
it writes are the board; nobody edits them::

    benchmarks/leaderboard/TRACK_P.md        the ranked table, the rows not ranked yet, every other run folder and why
    benchmarks/leaderboard/track_p.json      the same, for the tracker and for publishing
    benchmarks/leaderboard/track_p.svg       every row's probes as a grid of passes, the picture on the board
    benchmarks/leaderboard/cards/<model>.md  one card per row: the §3.2 measures, the pins, every probe's attempts

The rules, from the plan:

- the score is the pass rate over k >= 3 attempts per probe, per tier and
  overall; a row is ranked once every probe has k attempts that count;
- attempts ended by infrastructure are recorded and excluded; attempts ended
  by budget count as failures, whatever the document shows;
- ties on score break on hard-fail rate, then invalid-call rate, then cost per
  task. A probe check is pass or fail, with no value findings to disqualify a
  sheet as Track D's verifier will have, so on Track P a hard fail is a probe
  the model failed on every attempt;
- the class and the runner are marked on every row; an ordering is called
  separated only where the 95% intervals do not overlap.

Only episodes the native runner wrote (a ``run.json`` beside the trace) are
rows. The earlier rigs' folders are listed with the reason they are not.

    python -m roaddraft.runners leaderboard [--runs benchmarks/probe_runs] [--out benchmarks/leaderboard] [--check]
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from roaddraft.mcp.server import INSTRUCTIONS
from roaddraft.probes import prompting, tasks
from roaddraft import effort as effort_of
from roaddraft.runners.score import score_folder

K = 3
TIERS: Tuple[Tuple[str, str, List[str]], ...] = (
    ("T1", "find and draft", [p.id for p in tasks.FIND_PROBES + tasks.DRAFT_PROBES]),
    ("T2", "harder tasks", [p.id for p in tasks.TIER2_PROBES]),
    ("T3", "line and curve data", [p.id for p in tasks.TIER3_PROBES]),
)
TIER_OF = {pid: tier for tier, _, ids in TIERS for pid in ids}

#: stops where the check decides
MODEL_STOPS = frozenset({"answered", "refusal"})
#: stops that are the budget's doing: a failure, whatever the document shows
BUDGET_STOPS = frozenset({"budget", "budget_usd", "max_turns", "turn_limit", "context", "length"})
#: an ``error:`` stop is the infrastructure's, unless it says the model's own
#: output was unreadable: LM Studio could not parse Llama 3.1 8B's tool call on
#: 2026-10-07, which is the model's failure, not the rig's
#: ... and vLLM's harmony parser refusing gpt-oss-20b's own malformed tool header
#: ("unexpected tokens remaining in message header", 2026-10-17): the model's failure too
MODEL_ERRORS = ("does not match the expected", "unexpected tokens remaining in message header",
                "could not decode header")
#: an ``error:`` stop that is a turn limit in disguise: Runpod's proxy ends a streamed turn at 570 s, so
#: on that backend a model whose single turn outlasts it (Gemma 4 thinking for 13k+ tokens, 2026-10-17)
#: has exceeded the rig's effective turn limit, a budget failure like ``turn_limit`` (the runner's own 1,800 s).
#: A cold start that outlasts it (0 turns) is the infrastructure's and is rerun, so it never reaches the board.
BUDGET_ERRORS = ("stream did not complete within 570 seconds",)

MARKS = {"pass": "P", "fail": "·", "budget": "B", "excluded": "X"}
BOOTSTRAP, SEED = 2000, 0

NAMES = {"claude-haiku-4-5": "Claude Haiku 4.5", "claude-fable-5-1": "Claude Fable 5.1",
         "claude-opus-5-5": "Claude Opus 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
         "qwen/qwen3.5-9b": "Qwen3.5-9B", "Qwen/Qwen3.5-9B": "Qwen3.5-9B (bf16, vLLM)", "google/gemma-4-e4b": "Gemma 4 E4B", "gpt-oss:120b-cloud": "gpt-oss-120b",
         # the Runpod ladder (benchmarks/runpod/models.json): Hugging Face ids as the runner names them
         "Qwen/Qwen3.5-4B": "Qwen3.5-4B (bf16, vLLM)", "google/gemma-4-12B-it": "Gemma 4 12B (bf16, vLLM)",
         "openai/gpt-oss-20b": "gpt-oss-20b (mxfp4, vLLM)", "Qwen/Qwen3.8-27B": "Qwen3.8-27B (bf16, vLLM)",
         "google/gemma-4-31B-it": "Gemma 4 31B (bf16, vLLM)", "zai-org/GLM-4.7-Flash": "GLM-4.7-Flash (bf16, vLLM)",
         "Qwen/Qwen3.6-35B-A3B": "Qwen3.6-35B-A3B (bf16, vLLM)", "google/gemma-4-26B-A4B-it": "Gemma 4 26B-A4B (bf16, vLLM)",
         "openai/gpt-oss-120b": "gpt-oss-120b (mxfp4, vLLM)", "Qwen/Qwen3.5-122B-A10B-FP8": "Qwen3.5-122B-A10B (FP8, vLLM)",
         "meta-llama-3.1-8b-instruct": "Llama 3.1 8B Instruct",
         "mistralai/mistral-7b-instruct-v0.3": "Mistral 7B Instruct v0.3",
         "gpt-6-astra": "GPT-6-Astra", "gpt-6-luna": "GPT-6-Luna", "gpt-6-sol": "GPT-6-Sol",
         "gpt-6.1-sol": "GPT-6.1-Sol"}
GENERATED = ("Generated by `python -m roaddraft.runners leaderboard` from the run folders under "
             "`benchmarks/probe_runs`. Do not edit by hand: change a run or the generator and "
             "generate again; `--check` fails while this file is out of date.")


# ------------------------------------------------------------------ reading

@dataclass
class Attempt:
    """One episode: where it is, how it ended, and its row as scored from disk."""
    run: str
    label: str
    probe: str
    outcome: str                    # pass | fail | budget | excluded
    row: Dict[str, Any]
    meta: Dict[str, Any]
    prompt_current: bool
    instructions_current: Optional[bool]


@dataclass
class Folder:
    """A run folder as the board sees it."""
    name: str
    title: str
    native: int = 0                 # episodes with a run.json
    rig: int = 0                    # episodes the earlier rigs left (no run.json)
    unfinished: Dict[str, int] = field(default_factory=dict)   # label -> episodes without a run.json


def outcome(stop: str, passed: bool) -> str:
    if stop in MODEL_STOPS:
        return "pass" if passed else "fail"
    if stop in BUDGET_STOPS:
        return "budget"
    if any(marker in stop for marker in MODEL_ERRORS):
        return "fail"
    if any(marker in stop for marker in BUDGET_ERRORS):
        return "budget"
    return "excluded"


def _title(run_dir: Path) -> str:
    results = run_dir / "RESULTS.md"
    lines = results.read_text().splitlines() if results.exists() else []
    return lines[0].lstrip("# ").strip() if lines else ""


def _instructions_current(episode: Path) -> Optional[bool]:
    transcript = episode / "transcript.json"
    if not transcript.exists():
        return None
    messages = json.loads(transcript.read_text()).get("messages") or []
    if not messages or messages[0].get("role") != "system":
        return None
    return messages[0].get("content") == INSTRUCTIONS


def collect(runs_root: Path) -> Tuple[List[Attempt], List[Folder]]:
    """Every native episode under ``runs_root``, scored from disk; every folder."""
    attempts: List[Attempt] = []
    folders: List[Folder] = []
    starts: Dict[str, Path] = {}
    try:
        for run_dir in sorted(p for p in Path(runs_root).iterdir() if (p / "runs").is_dir()):
            folder = Folder(run_dir.name, _title(run_dir))
            episodes = [e for label_dir in sorted(p for p in (run_dir / "runs").iterdir()
                                                  if p.is_dir() and not p.name.startswith("_"))
                        for e in sorted(p for p in label_dir.iterdir()
                                        if p.is_dir() and p.name in tasks.BY_ID)]
            native = any((e / "run.json").exists() for e in episodes)
            for episode in episodes:
                label = episode.parent.name
                if not (episode / "run.json").exists():
                    # in a folder the native runner writes, an episode without its
                    # run.json is still running, or its runner was stopped
                    if native:
                        folder.unfinished[label] = folder.unfinished.get(label, 0) + 1
                    else:
                        folder.rig += 1
                    continue
                folder.native += 1
                probe = tasks.BY_ID[episode.name]
                meta = json.loads((episode / "run.json").read_text())
                if meta.get("profile", "default") != "default":
                    continue  # another tool surface (mcp/profiles.py): never a board row
                row = score_folder(episode, probe, starts)
                prompt = episode / "prompt.txt"
                attempts.append(Attempt(
                    run=run_dir.name, label=label, probe=probe.id,
                    outcome=outcome(meta.get("stop") or "", bool(row.get("passed"))),
                    row=row, meta=meta,
                    prompt_current=prompt.exists() and prompt.read_text() == prompting.task_text(probe),
                    instructions_current=_instructions_current(episode)))
            folders.append(folder)
    finally:
        for path in starts.values():
            shutil.rmtree(path, ignore_errors=True)
    return attempts, folders


# ------------------------------------------------------------------ summing

def model_class(model: str, meta: Dict[str, Any]) -> str:
    if "roaddraft" in model.lower():
        return "RQ3 checkpoint"
    if model.startswith("claude-") or meta.get("backend") in ("anthropic", "claude-code", "codex"):
        return "frontier API"
    host = urlparse(meta.get("base_url") or "").hostname or ""
    if model.endswith("-cloud") or host not in ("", "localhost", "127.0.0.1", "::1"):
        return "hosted open-weight"
    return "local small"


def runner(meta: Dict[str, Any]) -> str:
    backend = meta.get("backend") or "?"
    if backend == "claude-code":
        return "runners · claude-code (Claude Code headless)"
    if backend == "codex":
        return "runners · codex (Codex headless)"
    if backend == "anthropic":
        return "runners · anthropic (Messages API)"
    if backend == "openai":
        url = urlparse(meta.get("base_url") or "")
        server = {1234: "LM Studio", 11434: "Ollama"}.get(url.port or 0, url.hostname)
        return f"runners · openai ({server})" if server else "runners · openai"
    return f"runners · {backend}"


def cost_of(meta: Dict[str, Any]) -> Optional[float]:
    """The CLI's own figure where it gives one (it prices the one-hour cache it
    writes), else the runner's estimate at list price."""
    for key in ("claude_cost_usd", "cost_usd"):
        if meta.get(key) is not None:
            return float(meta[key])
    return None


#: what each backend sends ``--effort`` as; the openai-compatible backend sends none
EFFORT_SENT = {"anthropic": "the Messages API's `output_config.effort`",
               "claude-code": "the Claude Code CLI's `--effort`",
               "codex": "Codex's `model_reasoning_effort`"}


def effort(meta: Dict[str, Any]) -> Tuple[str, str]:
    """The effort a row ran at, as a cell and in words (``roaddraft.effort``):
    the level ``--effort`` set; for the openai-compatible backend, which sends no
    level, what its request body set; else the model's default where it is
    known, ``default`` where it is not."""
    backend = meta.get("backend") or "?"
    return effort_of.describe(meta.get("model") or "?", meta.get("effort"),
                              EFFORT_SENT.get(backend), meta.get("extra_body"))


def _effort_words(label: str) -> str:
    """``medium effort``, ``xhigh (default) effort``, ``thinking on (default)``: the cell as a phrase."""
    if label.startswith("thinking"):
        return label
    level, _, rest = label.partition(" ")
    return f"{level} effort" + (f" {rest}" if rest else "")


def interval(per_probe: Sequence[Sequence[int]], n: int = BOOTSTRAP, seed: int = SEED
             ) -> Tuple[Optional[float], Optional[float]]:
    """A 95% interval on the mean per-probe pass rate: probes resampled, then
    each probe's attempts, ``n`` times with a fixed seed."""
    per_probe = [list(o) for o in per_probe if o]
    if not per_probe:
        return None, None
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        total = 0.0
        for _ in per_probe:
            o = per_probe[rng.randrange(len(per_probe))]
            total += sum(o[rng.randrange(len(o))] for _ in o) / len(o)
        stats.append(total / len(per_probe))
    stats.sort()
    return stats[round(0.025 * (n - 1))], stats[round(0.975 * (n - 1))]


def _natural(label: str) -> List[Any]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", label)]


def _stem(label: str) -> str:
    """``qwen`` for ``qwen-r2``: the repeats of one ``--repeat`` run."""
    return re.sub(r"-r\d+$", "", label)


def _mean(values: Sequence[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarize(key: Tuple, attempts: List[Attempt], unfinished: int) -> Dict[str, Any]:
    run, model, backend, vision, level = key
    # an episode the runner ended on an error carries no base_url; the class and the runner read it
    meta = next((a.meta for a in attempts if a.meta.get("base_url")), attempts[0].meta)
    served = [a for a in attempts if a.meta.get("base_url")] or attempts
    labels = sorted({a.label for a in attempts}, key=_natural)
    # an episode that ran on an earlier task text (the probe set changed since) does
    # not count: its document was drafted to other words than the current check expects
    stale = [a for a in attempts if not a.prompt_current]
    valid = [a for a in attempts if a.outcome != "excluded" and a.prompt_current]
    per_probe: Dict[str, List[int]] = {p.id: [] for p in tasks.PROBES}
    for a in valid:
        per_probe[a.probe].append(int(a.outcome == "pass"))
    attempted = [pid for pid, o in per_probe.items() if o]
    short = [pid for pid, o in per_probe.items() if len(o) < K]
    rates = {pid: sum(o) / len(o) for pid, o in per_probe.items() if o}
    lo, hi = interval([per_probe[pid] for pid in attempted])
    tiers = {}
    for tier, _, ids in TIERS:
        outcomes = [o for pid in ids for o in per_probe[pid]]
        tier_rates = [rates[pid] for pid in ids if pid in rates]
        tiers[tier] = {"passes": sum(outcomes), "attempts": len(outcomes), "probes": len(ids),
                       "rate": _mean(tier_rates)}
    calls = sum(a.row.get("calls", 0) for a in valid)
    faults = sum(a.row.get("faults", 0) for a in valid)
    changed = [a for a in valid if a.row.get("query_first") is not None]
    costs = [cost_of(a.meta) for a in valid]
    tokens_in = [sum((a.meta.get("tokens") or {}).get(k, 0) for k in
                     ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                 for a in valid if a.meta.get("tokens")]
    tokens_out = [(a.meta.get("tokens") or {}).get("output_tokens", 0) for a in valid if a.meta.get("tokens")]
    # Codex counts reasoning as ``reasoning_output_tokens``
    reasoning = [r for a in valid for t in [a.meta.get("tokens") or {}]
                 for r in [t.get("reasoning_tokens", t.get("reasoning_output_tokens"))] if r is not None]
    multi = [a for a in valid if (a.row.get("items_asked") or 0) > 1]
    read = [(a, a.row["claims"]) for a in valid if (a.row.get("claims") or {}).get("report")]
    failed = [(a, c) for a, c in read if not a.row.get("passed")]
    commits = Counter((a.meta.get("pins") or {}).get("commit") for a in attempts)
    instructions = Counter(a.instructions_current for a in attempts)
    effort_label, effort_note = effort(meta)
    marks = {}
    for p in tasks.PROBES:
        mine = sorted((a for a in attempts if a.probe == p.id), key=lambda a: _natural(a.label))
        failing = next((a for a in mine if a.outcome in ("fail", "budget")), None)
        marks[p.id] = {"tier": TIER_OF[p.id],
                       "marks": " ".join(MARKS[a.outcome] for a in mine),
                       "passes": sum(per_probe[p.id]), "attempts": len(per_probe[p.id]),
                       "calls": _mean([a.row.get("calls", 0) for a in mine if a.outcome != "excluded"]),
                       "faults": sum(a.row.get("faults", 0) for a in mine if a.outcome != "excluded"),
                       "failing": (f"{failing.label}: {failing.row.get('detail', '')}"
                                   + (f" (ended by budget: {failing.meta.get('stop')})"
                                      if failing.outcome == "budget" else "")) if failing else ""}
    return {
        "model": model, "name": NAMES.get(model, model), "class": model_class(model, meta),
        "runner": runner(meta), "backend": backend, "run": run, "labels": labels,
        "vision": vision, "effort": level, "effort_label": effort_label, "effort_note": effort_note,
        "requests": Counter(_request(a.meta) for a in served),
        "budgets": sorted({(a.meta.get("max_turns"), a.meta.get("budget_s")) for a in attempts},
                          key=lambda b: (b[0] or 0, b[1] or 0)),
        "base_url": meta.get("base_url"),
        "attempts": len(attempts), "valid": len(valid), "unfinished": unfinished,
        "stale": len(stale),
        "passes": sum(a.outcome == "pass" for a in valid),
        "probes_attempted": len(attempted), "probes_short": short,
        "score": _mean(list(rates.values())), "ci": [lo, hi],
        "tiers": tiers,
        "hard_fail": (sum(rates[pid] == 0 for pid in attempted) / len(attempted)) if attempted else None,
        "never": sum(rates[pid] == 0 for pid in attempted),
        "always": sum(rates[pid] == 1 for pid in attempted),
        "invalid_rate": faults / calls if calls else None,
        "cost_per_task": _mean(costs),
        "cost_total": sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None,
        "cost_source": ("the CLI's own figure at list price, billed to a subscription"
                        if any(a.meta.get("claude_cost_usd") is not None for a in valid)
                        else "the runner's estimate at list price" if any(c is not None for c in costs)
                        else "no price: a ChatGPT subscription, which reports none" if backend == "codex"
                        else "no price: a local model"),
        "per_label": {l: {"passes": sum(a.outcome == "pass" for a in valid if a.label == l),
                          "valid": sum(1 for a in valid if a.label == l)} for l in labels},
        "measures": {
            "calls": calls, "faults": faults,
            "recovered": sum(a.row.get("recovered", 0) for a in valid),
            "loops": sum(bool(a.row.get("fault_loop")) for a in valid),
            "longest_fault_run": max([a.row.get("fault_streak", 0) for a in valid] or [0]),
            "design_queries": sum(a.row.get("design_queries", 0) for a in valid),
            "query_first": sum(bool(a.row.get("query_first")) for a in changed),
            "changed": len(changed),
            "renders": sum(a.row.get("renders", 0) for a in valid),
            "rendered": sum(a.row.get("renders", 0) > 0 for a in valid),
            "renders_fixed": sum(a.row.get("renders_fixed", 0) for a in valid),
            "turns": _mean([a.meta.get("num_turns", a.meta.get("turns")) for a in valid]),
            "calls_per": calls / len(valid) if valid else None,
            "seconds": _mean([a.meta.get("seconds") for a in valid]),
            "seconds_total": sum(a.meta.get("seconds") or 0 for a in valid),
            "tokens_in": _mean(tokens_in), "tokens_out": _mean(tokens_out),
            "reasoning": _mean(reasoning),
            "truncated": sum(a.meta.get("truncated_results") or 0 for a in valid),
            # scope completion: the probes that ask for more than one thing
            "multi": len(multi),
            "multi_probes": len({a.probe for a in multi}),
            "items_done": sum(a.row["items_done"] for a in multi),
            "items_asked": sum(a.row["items_asked"] for a in multi),
            "multi_complete": sum(a.row["items_done"] == a.row["items_asked"] for a in multi),
            # report fidelity: the reports against the record
            "reports": len(read),
            "failed_reports": len(failed),
            "false_done": sum(c["false_done"] for _a, c in failed),
            "false_items": sum(c["false_items"] for _a, c in failed),
            "conceded": sum(c["claims_done"] is False for _a, c in failed),
            "under_claimed": sum(c["claims_done"] is False for a, c in read if a.row.get("passed")),
            "clean_claims": sum(c["claims_clean_run"] for _a, c in read),
            "false_clean": sum(c["false_clean_run"] for _a, c in read),
            "invented_ids": sum(len(c["invented_ids"]) for _a, c in read),
            "cited_ids": sum(c["cited_ids"] for _a, c in read),
        },
        "stops": dict(sorted(Counter(a.meta.get("stop") or "?" for a in attempts).items())),
        "excluded": [f"{a.label}/{a.probe}: {a.meta.get('stop')}" for a in attempts if a.outcome == "excluded"],
        "budget_ended": [f"{a.label}/{a.probe}: {a.meta.get('stop')}, the document "
                         f"{'passes' if a.row.get('passed') else 'fails'} its check"
                         for a in attempts if a.outcome == "budget"],
        "pins": {"commits": {(c or "not recorded"): n for c, n in sorted(commits.items(), key=lambda i: str(i[0]))},
                 "dirty": sorted({f for a in attempts for f in (a.meta.get("pins") or {}).get("dirty") or []}),
                 "tools": sorted({(a.meta.get("pins") or {}).get("tools_sha256") or "not recorded"
                                  for a in attempts}),
                 "instructions_current": instructions.get(True, 0),
                 "instructions_differ": instructions.get(False, 0),
                 "prompts_differ": sum(not a.prompt_current for a in attempts)},
        "probes": marks,
    }


def _key(row: Dict[str, Any]) -> Tuple:
    cost = row["cost_per_task"]
    return (-round(row["score"], 6), round(row["hard_fail"], 6), round(row["invalid_rate"] or 0, 6),
            round(cost, 6) if cost is not None else float("inf"))


def _slug(model: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


def board(attempts: List[Attempt], folders: List[Folder]) -> Dict[str, Any]:
    """The leaderboard as data: ranked rows, rows not ranked yet, every other folder."""
    groups: Dict[Tuple, List[Attempt]] = {}
    for a in attempts:
        key = (a.run, a.meta.get("model") or "?", a.meta.get("backend") or "?",
               bool(a.meta.get("vision")), a.meta.get("effort"))
        groups.setdefault(key, []).append(a)
    by_folder = {f.name: f for f in folders}
    rows = []
    for key, group in sorted(groups.items(), key=lambda i: tuple(str(k) for k in i[0])):
        # a label still on its first probe has no run.json to name its model:
        # it belongs to the row whose labels are the same --repeat run
        stems = {_stem(a.label) for a in group}
        unfinished = sum(n for l, n in by_folder[key[0]].unfinished.items() if _stem(l) in stems)
        rows.append(summarize(key, group, unfinished))
    single = [r for r in rows if not any(_stem(l) != l for l in r["labels"])]
    rows = [r for r in rows if r not in single]
    complete = [r for r in rows if not r["probes_short"] and not r["unfinished"]]
    latest: Dict[Tuple, Dict[str, Any]] = {}
    for r in sorted(complete, key=lambda r: r["run"]):
        latest[(r["model"], r["backend"], r["vision"], r["effort"])] = r
    ranked = sorted(latest.values(), key=_key)
    ranked_ids = {id(r) for r in ranked}
    rank, previous = 0, None
    for i, r in enumerate(ranked, 1):
        rank = rank if _key(r) == previous else i
        r["rank"], previous = rank, _key(r)
    unranked = [r for r in rows if id(r) not in ranked_ids]
    for r in unranked:
        why = []
        if r["unfinished"]:
            why.append(f"in progress: {r['unfinished']} episode{'s' * (r['unfinished'] != 1)} unfinished")
        if r["probes_short"]:
            done = len(tasks.PROBES) - len(r["probes_short"])
            why.append(f"k = {K} on {done} of {len(tasks.PROBES)} probes")
        if r.get("stale"):
            why.append(f"{r['stale']} episode{'s' * (r['stale'] != 1)} ran on an earlier task text "
                       f"(the probe set changed since); rerun")
        if not why:
            newer = latest[(r["model"], r["backend"], r["vision"], r["effort"])]
            why.append(f"superseded by {newer['run']}")
        r["why"] = "; ".join(why)
    unranked.sort(key=lambda r: (not r["unfinished"], -r["probes_attempted"], r["run"], r["model"]))
    taken = set()
    for r in ranked + unranked:
        slug = _slug(r["model"])
        if slug in taken:
            slug = f"{slug}--{r['run']}"
        if slug in taken:
            slug = f"{slug}-{_slug(r['backend'])}"
        taken.add(slug)
        r["card"] = f"cards/{slug}.md"
    on_board = {r["run"] for r in rows}
    others = []
    for f in folders:
        smoke = [r for r in single if r["run"] == f.name]
        if smoke:
            runs = ", ".join(f"{r['name']} on {r['probes_attempted']} probe{'s' * (r['probes_attempted'] != 1)} "
                             f"({r['passes']}/{r['valid']} passed)" for r in smoke)
            why = (f"roaddraft.runners, single runs without `--repeat`: {runs}. "
                   "A smoke test of the runner, not a Track P run")
        elif f.name in on_board:
            continue
        elif not f.native:
            why = ("an earlier rig (the shell bridge or its own client), not roaddraft.runners: "
                   "its episodes carry no run.json and its rows do not compare")
        else:
            why = "no Track P episodes"
        others.append({"run": f.name, "title": f.title, "episodes": f.rig + f.native, "why": why})
    probe_set = hashlib.sha256(json.dumps([[p.id, prompting.task_text(p)] for p in tasks.PROBES],
                                          ensure_ascii=False).encode("utf-8")).hexdigest()
    dates = [m.group(0) for r in rows for m in [re.match(r"\d{4}-\d{2}-\d{2}", r["run"])] if m]
    return {"generated_by": "python -m roaddraft.runners leaderboard",
            "board": "probe board (Track P): capability probes, not the eval; closed 2026-10-27",
            "as_of": max(dates, default=None),
            "ranked_from": sorted({r["run"] for r in ranked}),
            "k": K, "probes": len(tasks.PROBES), "probe_set_sha256": "sha256:" + probe_set,
            "tiers": {tier: {"name": name, "probes": ids} for tier, name, ids in TIERS},
            "ranked": ranked, "unranked": unranked, "others": others}


# ------------------------------------------------------------------ writing

def _pct(x: Optional[float], digits: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{digits}f}%"


def _usd(x: Optional[float]) -> str:
    return "—" if x is None else f"${x:.2f}"


def _num(x: Optional[float], digits: int = 1) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


def _k(tokens: Optional[float]) -> str:
    if tokens is None:
        return "—"
    return f"{tokens / 1000:,.0f}k" if tokens >= 100_000 else f"{tokens / 1000:,.1f}k"


def _tier(t: Dict[str, Any]) -> str:
    if not t["attempts"]:
        return "—"
    return f"{t['passes']}/{t['attempts']} ({_pct(t['rate'], 0)})"


def _ci(r: Dict[str, Any]) -> str:
    lo, hi = r["ci"]
    return f"[{100 * lo:.1f}, {100 * hi:.1f}]" if lo is not None else "—"


def _score(r: Dict[str, Any]) -> str:
    return f"{_pct(r['score'])} {_ci(r)}"


def _request(meta: Dict[str, Any]) -> str:
    """What the runner added to every request: the sampling from the model card, the thinking sent back."""
    parts = [f"`{json.dumps(meta['extra_body'], sort_keys=True)}`"] if meta.get("extra_body") else []
    if meta.get("send_reasoning"):
        parts.append("a tool-call turn's thinking sent back as `reasoning` (`--send-reasoning`)")
    return "; ".join(parts) or "none (the provider's defaults)"


def _budgets(r: Dict[str, Any]) -> str:
    parts = []
    for turns, seconds in r["budgets"]:
        minutes = f"{seconds / 60:g} min" if seconds else "no wall-clock limit"
        parts.append(f"{turns} turns, {minutes}")
    return "; ".join(parts)


def _comparability(ranked: List[Dict[str, Any]]) -> List[str]:
    notes = []
    for a, b in zip(ranked, ranked[1:]):
        if a["ci"][0] is not None and b["ci"][1] is not None and a["ci"][0] <= b["ci"][1]:
            notes.append(f"{a['name']} (rank {a['rank']}) and {b['name']} (rank {b['rank']}): "
                         "the 95% intervals overlap, so this ordering is not separated.")
    budgets = {_budgets(r) for r in ranked}
    if len(budgets) > 1:
        notes.append("Budgets differ between ranked rows: "
                     + "; ".join(f"{r['name']} {_budgets(r)}" for r in ranked) + ".")
    tools = {t for r in ranked for t in r["pins"]["tools"] if t != "not recorded"}
    if len(tools) > 1:
        notes.append(f"Ranked rows ran on {len(tools)} different tool surfaces; see the cards.")
    differ = [r["name"] for r in ranked if r["pins"]["instructions_differ"] or r["pins"]["prompts_differ"]]
    if differ:
        notes.append("Ran on server instructions or task prompts that differ from the current ones: "
                     + ", ".join(differ) + ".")
    unpinned = [r["name"] for r in ranked if "not recorded" in r["pins"]["commits"]]
    if unpinned:
        notes.append("Engine commit not recorded (episodes from before run.json carried pins): "
                     + ", ".join(unpinned) + ".")
    return notes


PROBE_BOARD_NOTE = (
    "**This is the probe board, not the eval leaderboard.** The 33 probes are hand-built capability checks, "
    "pass or fail, made for a quick read on what models of different sizes can do with the tool surface. "
    "Closed as a capability read on 2026-10-27 (Robert): eleven rows say enough, no more rows are planned, "
    "and the withdrawn frontier rows are not rerun. The benchmark proper, the eval sets `d1-test`, `d1-real` "
    "and `hard-pilots` scored by the verifier, is the [eval leaderboard](../runs/LEADERBOARD.md).")


def render_board(b: Dict[str, Any]) -> str:
    tiers = b["tiers"]
    head = " | ".join(f"{t} ({len(v['probes'])})" for t, v in tiers.items())
    listing = "; ".join(f"{t} {v['name']}, {len(v['probes'])}" for t, v in tiers.items())
    lines = [
        "# RoadDraft probe board (Track P): capability probes, not the eval", "",
        f"*{GENERATED}*", "",
        PROBE_BOARD_NOTE, "",
        f"The {b['probes']} probes in three tiers ({listing}), "
        f"k = {b['k']} attempts each, every model through the one native MCP runner, `roaddraft.runners`. "
        "Every episode is re-scored from the document it left on disk against the current probe checks. "
        f"Runs through {b['as_of']}"
        + (f"; the ranked rows are from {', '.join(f'`{r}`' for r in b['ranked_from'])}" if b["ranked_from"] else "")
        + f". Probe set `{b['probe_set_sha256'][:19]}`.", "",
        "![Probes passed of k attempts, every row on the board](track_p.svg)", "",
        "## Ranked", "",
    ]
    if b["ranked"]:
        lines += [f"| rank | model | effort | class | runner | pass rate [95% CI] | {head} | hard-fail | invalid calls | cost / task | attempts | card |",
                  "|---|---|---|---|---|---|" + "---|" * len(tiers) + "---|---|---|---|---|"]
        for r in b["ranked"]:
            cells = " | ".join(_tier(r["tiers"][t]) for t in tiers)
            lines.append(f"| {r['rank']} | {r['name']} | {r['effort_label']} | {r['class']} | {r['runner']} | "
                         f"{_score(r)} | {cells} | "
                         f"{_pct(r['hard_fail'], 0)} ({r['never']}/{r['probes_attempted']}) | "
                         f"{_pct(r['invalid_rate'])} | {_usd(r['cost_per_task'])} | "
                         f"{r['valid']} (k = {b['k']}) | [card]({r['card']}) |")
        notes = _comparability(b["ranked"])
        if notes:
            lines += [""] + [f"- {n}" for n in notes]
    else:
        lines.append(f"No model has all {b['probes']} probes at k = {b['k']} yet.")
    lines += ["", "## Not ranked yet", ""]
    if b["unranked"]:
        lines += ["| model | effort | class | runner | run folder | attempts | passed | why not ranked | card |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in b["unranked"]:
            lines.append(f"| {r['name']} | {r['effort_label']} | {r['class']} | {r['runner']} | `{r['run']}` | "
                         f"{r['valid']} on {r['probes_attempted']} probe{'s' * (r['probes_attempted'] != 1)} | "
                         f"{r['passes']}/{r['valid']} | "
                         f"{r['why']} | [card]({r['card']}) |")
    else:
        lines.append("None.")
    lines += ["", "## Run folders not on the board", ""]
    if b["others"]:
        lines += ["| run folder | episodes | what it was | why not |", "|---|---|---|---|"]
        for o in b["others"]:
            lines.append(f"| `{o['run']}` | {o['episodes']} | {o['title']} | {o['why']} |")
    else:
        lines.append("None.")
    lines += [
        "", "## How the board is computed", "",
        f"- **A row** is one model on one backend, mode and effort, in one run folder: every episode the native "
        f"runner left under `runs/<label>-rN/<probe>/`, the labels `--repeat` writes. A row is ranked once all "
        f"{b['probes']} probes have k = {b['k']} attempts that count; a model with two complete rows ranks on the "
        "newer folder. A label without `-rN` is a single run, listed with its folder below the board.",
        "- **Pass rate** is the mean over probes of each probe's passes over its attempts that count. "
        "Tiers are the same mean over that tier's probes; the cells show passes over attempts.",
        f"- **95% CI**: a bootstrap over probes, then over each probe's attempts, {BOOTSTRAP:,} resamples, seed {SEED}.",
        "- **Attempts that count**: an episode the model ended (answered, refused) is scored by its probe check "
        "from disk. One ended by budget (turns, wall clock, tokens, context, the CLI's spend cap) counts as a "
        "failure whatever the document shows. One ended by the infrastructure (a crash, a dead engine, a CLI "
        "error) is recorded on the card and excluded, except an error that says the model's own output was "
        "unreadable, which is the model's failure.",
        "- **Effort** is the level the run asked for with `--effort`, sent as "
        + ", ".join(EFFORT_SENT[k] for k in ("anthropic", "claude-code"))
        + f" or {EFFORT_SENT['codex']}. The openai-compatible backend sends no level, so its rows show what the request body set "
        "(`reasoning_effort`, or `enable_thinking` for a chat template with a thinking switch). Where the run "
        "set nothing, the cell is the model's default, marked **(default)**, as read from where the setting "
        "lives: the model's chat template on Hugging Face (vLLM's harmony system message for gpt-oss), or "
        "Codex's model catalog; plain **default** is a default not looked up. A model run at two efforts is "
        "two rows.",
        "- **Ties** break on hard-fail rate, then invalid-call rate, then cost per task (a row with no price sorts "
        "after one with a price).",
        "- **Hard-fail rate**: the share of probes failed on every attempt. Track P checks are pass or fail with no "
        "value findings to disqualify a sheet, so the hard fail here is a probe the model never solves.",
        "- **Invalid calls**: faulted calls over all calls, from each episode's `trace.jsonl`.",
        "- **Cost per task**: the mean list-price cost of an episode; for Claude Code runs the CLI's own figure.",
        "- **Class** is frontier API, hosted open-weight, local small or RQ3 checkpoint; **runner** is the "
        "`roaddraft.runners` backend and what it talked to.",
        "- The model cards carry the research plan's §3.2 measures, the pins (engine commit, tool-surface and "
        "instruction digests, budgets) and every probe's attempts.",
        "",
    ]
    return "\n".join(lines)


def card_facts(r: Dict[str, Any], b: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The head of a model card: what ran, on what, and where it stands."""
    status = (f"rank {r['rank']} of {len(b['ranked'])}" if "rank" in r else f"not ranked yet: {r['why']}")
    pins = r["pins"]
    commits = ", ".join(f"`{c[:10]}` ({n})" if c != "not recorded" else f"not recorded ({n})"
                        for c, n in pins["commits"].items())
    tools = ", ".join(f"`{t[:19]}`" if t != "not recorded" else "not recorded" for t in pins["tools"])
    instr = ("current" if not pins["instructions_differ"] and pins["instructions_current"]
             else f"{pins['instructions_differ']} of {r['attempts']} episodes differ from the current server's"
             if pins["instructions_differ"] else "not recorded")
    prompts = ("current" if not pins["prompts_differ"]
               else f"{pins['prompts_differ']} of {r['attempts']} differ from the current task text")
    return [
        ("model", f"`{r['model']}`"),
        ("class", r["class"]),
        ("runner", r["runner"] + (f", `{r['base_url']}`" if r["base_url"] else "")),
        ("run folder", f"`{r['run']}`, labels {', '.join(f'`{l}`' for l in r['labels'])}"),
        ("effort", f"{r['effort_label']}: {r['effort_note']}"),
        ("budgets", f"{_budgets(r)} per probe; {'vision' if r['vision'] else 'text only'}"),
        ("request settings", "; ".join(q if len(r["requests"]) == 1 else f"{q} ({n})"
                                       for q, n in r["requests"].items())),
        ("standing", status),
        ("engine commit", commits + (f"; changed past it: {', '.join(f'`{d}`' for d in pins['dirty'])}"
                                     if pins["dirty"] else "")),
        ("tool surface", tools),
        ("server instructions", instr),
        ("task prompts", prompts),
    ]


def card_score(r: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, str]:
    """A card's score in words: the pass rate, the attempts, the stops."""
    m = r["measures"]
    per_label = ", ".join(f"{l} {v['passes']}/{v['valid']}" for l, v in r["per_label"].items())
    return {
        "summary": f"{r['passes']} of {r['valid']} attempts that count, on {r['probes_attempted']} of "
                   f"{b['probes']} probes"
                   + (f" ({r['attempts'] - r['valid']} excluded)" if r["attempts"] != r["valid"] else ""),
        "attempts": f"By attempt: {per_label}. Of the {r['probes_attempted']} probes attempted, {r['always']} pass "
                    f"every time, {r['never']} never pass (hard-fail rate {_pct(r['hard_fail'], 0)}), "
                    f"{r['probes_attempted'] - r['always'] - r['never']} split.",
        "stops": "Stops: " + ", ".join(f"{s} {n}" for s, n in r["stops"].items()) + "."
                 + (f" {m['truncated']} tool results were cut to the runner's cap." if m["truncated"] else ""),
    }


def card_measures(r: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """The research plan's §3.2 measures: name, value, how it is read."""
    m = r["measures"]
    return [
        ("invalid-call rate", f"{_pct(r['invalid_rate'])} ({m['faults']:,} of {m['calls']:,} calls)",
         "faulted calls over calls, from the traces"),
        ("fault recovery", f"{m['recovered']} of {m['faults']} faults"
         + (f" ({_pct(m['recovered'] / m['faults'], 0)})" if m["faults"] else ""),
         "a fault followed within three calls by a successful call of the same tool"),
        ("repeated-fault loops", f"{m['loops']} episode{'s' * (m['loops'] != 1)}; longest run {m['longest_fault_run']}",
         "the same fault five or more times in a row"),
        ("query before compute", f"{m['query_first']} of {m['changed']} episodes that changed the drawing asked a "
         f"design query first; {_num(m['design_queries'] / r['valid'] if r['valid'] else None)} design queries per episode",
         "`station_to_xy`, `xy_to_station`, `resolve_anchor`, `get_design_data`, `measure`, `point_on_entity` "
         "before the first successful command"),
        ("report fidelity", fidelity(m),
         "read from `report.txt` against the record, without a model: a report claims the task done "
         "unless it concedes a shortfall; a claim of no errors is held to the trace's faults; an id "
         "is invented when neither the document nor the trace ever had it"),
        ("steps", f"{_num(m['calls_per'])} calls, {_num(m['turns'])} turns per episode",
         "model turns; for Claude Code the CLI's own count"),
        ("wall clock", f"{_num(m['seconds'], 0)} s per episode, {m['seconds_total'] / 3600:.1f} h in all",
         "the runner's clock, episode start to report"),
        ("tokens", f"{_k(m['tokens_in'])} in, {_k(m['tokens_out'])} out per episode"
         + (f" ({_k(m['reasoning'])} of it reasoning)" if m["reasoning"] is not None else ""),
         "input counts cache reads and writes"),
        ("cost", f"{_usd(r['cost_per_task'])} per episode, {_usd(r['cost_total'])} in all", r["cost_source"]),
        ("render use", f"{m['renders']} renders in {m['rendered']} episodes; {m['renders_fixed']} followed by a change",
         "a render is followed by a change when a successful command comes before the next render"),
        ("scope completion", (f"{m['items_done']:,} of {m['items_asked']:,} items "
                              f"({_pct(m['items_done'] / m['items_asked'], 0)}) in {m['multi']} episodes "
                              f"of the {m['multi_probes']} probes that ask for more than one thing; "
                              f"{m['multi_complete']} of them did every item")
         if m["items_asked"] else "no episode asked for more than one thing",
         "items done over items asked, item by item as the probe check judges them: each sheet's "
         "callouts and title block, each station, tangent or curve point, each planted error"),
    ]


def fidelity(m: Dict[str, Any]) -> str:
    """Report fidelity in words: the claims the record contradicts."""
    if not m["reports"]:
        return "no reports kept"
    parts = [f"{m['false_done']} of {m['failed_reports']} failed episodes' reports said the task was done"
             + (f" ({m['false_items']} claims the check contradicts)" if m["false_done"] else "")
             if m["failed_reports"] else "no failed episode to contradict a report",
             f"{m['false_clean']} of {m['clean_claims']} claims of no errors came over a faulted trace",
             f"{m['invented_ids']} of {m['cited_ids']} cited ids never existed"]
    if m["under_claimed"]:
        parts.append(f"{m['under_claimed']} passing episodes' reports conceded a shortfall")
    return "; ".join(parts)


def render_card(r: Dict[str, Any], b: Dict[str, Any]) -> str:
    score = card_score(r, b)
    lines = [
        f"# {r['name']}: probe card (Track P)", "",
        f"*{GENERATED}* [Back to the probe board](../TRACK_P.md)", "",
        "| | |", "|---|---|",
        *(f"| {label} | {value} |" for label, value in card_facts(r, b)),
        "", "## Score", "",
        f"**{_pct(r['score'])}** pass rate, 95% CI {_ci(r)}: {score['summary']}.",
        "",
        "| | " + " | ".join(b["tiers"]) + " | all |",
        "|---|" + "---|" * (len(b["tiers"]) + 1),
        "| passed | " + " | ".join(_tier(r["tiers"][t]) for t in b["tiers"]) + f" | {r['passes']}/{r['valid']} |",
        "",
        score["attempts"],
        "", "## Measures (research plan §3.2)", "",
        "| measure | value | how it is read |", "|---|---|---|",
        *(f"| {name} | {value} | {how} |" for name, value, how in card_measures(r)),
        "",
        score["stops"],
    ]
    if r["excluded"]:
        lines += ["", "Excluded, ended by the infrastructure:", ""] + [f"- `{e[:240]}`" for e in r["excluded"]]
    if r["budget_ended"]:
        lines += ["", "Ended by budget, counted as failures:", ""] + [f"- {e}" for e in r["budget_ended"]]
    lines += ["", "## Every probe", "",
              "P passed, · failed, B ended by budget (a failure), X excluded (infrastructure). "
              "Attempts in label order.", "",
              "| probe | tier | attempts | calls | faults | the first failing attempt, as its check read it |",
              "|---|---|---|---|---|---|"]
    for pid, p in r["probes"].items():
        if not p["marks"]:
            lines.append(f"| {pid} | {p['tier']} | — | | | |")
            continue
        lines.append(f"| {pid} | {p['tier']} | {p['marks']} | {_num(p['calls'])} | {p['faults']} | "
                     f"{failing_detail(p).replace('|', chr(92) + '|')} |")
    lines.append("")
    return "\n".join(lines)


def failing_detail(p: Dict[str, Any], limit: int = 220) -> str:
    """A probe's first failing attempt, on one line, cut to ``limit``."""
    detail = p["failing"].replace("\n", " ")
    return detail if len(detail) <= limit else detail[:limit - 3] + "..."


#: the grid's colours: an ordinal blue ramp for 1, 2 and 3 of 3 (validated
#: with the dataviz skill's script, light and dark), a neutral cell for none
SVG_STYLE = """
text { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
.bg { fill: #fcfcfb; } .ink { fill: #0b0b0b; } .ink2 { fill: #52514e; } .rule { stroke: #b4b3ae; }
.c0 { fill: #f0efec; } .c1 { fill: #86b6ef; } .c2 { fill: #2a78d6; } .c3 { fill: #104281; }
.t0 { fill: #52514e; } .t1 { fill: #0b0b0b; } .t2 { fill: #ffffff; } .t3 { fill: #ffffff; }
.none { fill: none; stroke: #b4b3ae; stroke-dasharray: 2 2; }
@media (prefers-color-scheme: dark) {
  .bg { fill: #1a1a19; } .ink { fill: #ffffff; } .ink2 { fill: #c3c2b7; } .rule { stroke: #6b6a65; }
  .c0 { fill: #383835; } .c1 { fill: #184f95; } .c2 { fill: #3987e5; } .c3 { fill: #b7d3f6; }
  .t0 { fill: #c3c2b7; } .t1 { fill: #ffffff; } .t2 { fill: #0b0b0b; } .t3 { fill: #0b0b0b; }
  .none { stroke: #6b6a65; }
}
"""


def _x(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _step(passes: int, attempts: int) -> int:
    if not passes:
        return 0
    share = passes / attempts
    return 3 if share == 1 else 2 if share >= 0.5 else 1


def render_svg(b: Dict[str, Any]) -> str:
    """Every row's probes as a grid of passes over attempts, tiers side by side."""
    rows = b["ranked"] + b["unranked"]
    cell, gap, tier_gap, pitch = 24, 2, 12, 34
    subtitles = [f"{r['class']} · {r['backend']} · {_effort_words(r['effort_label'])}"
                 + ("" if "rank" in r else " · not ranked yet") for r in rows]
    # the row labels' column, wide enough for the longest subtitle (under 5 px a character at 10.5 px)
    left, top = max(250, 28 + 5 * max(map(len, subtitles), default=0)), 210
    xs, x = {}, left
    for t, v in b["tiers"].items():
        for pid in v["probes"]:
            xs[pid] = x
            x += cell + gap
        x += tier_gap
    right = x
    height = top + max(len(rows), 1) * pitch + 64
    width = right + 150
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
           f'height="{height}" role="img" aria-labelledby="title">',
           f"<title id=\"title\">RoadDraft probe board (Track P): probes passed of k = {b['k']} attempts, per model</title>",
           f"<style>{SVG_STYLE}</style>",
           f'<rect class="bg" width="{width}" height="{height}"/>',
           f'<text class="ink" x="16" y="28" font-size="17" font-weight="600">RoadDraft probe board (Track P)</text>',
           f'<text class="ink2" x="16" y="48" font-size="12">probes passed of k = {b["k"]} attempts; '
           f'runs through {_x(b["as_of"] or "")}; capability probes, not the eval; closed 2026-10-27</text>']
    for t, v in b["tiers"].items():
        x0, x1 = xs[v["probes"][0]], xs[v["probes"][-1]] + cell
        out.append(f'<text class="ink" x="{x0}" y="64" font-size="12" font-weight="600">{t} '
                   f'<tspan class="ink2" font-weight="400">{_x(v["name"])}, {len(v["probes"])}</tspan></text>')
        out.append(f'<line class="rule" x1="{x0}" y1="71" x2="{x1}" y2="71" stroke-width="1"/>')
        for pid in v["probes"]:
            cx = xs[pid] + cell / 2 + 3
            out.append(f'<text class="ink2" font-size="10.5" transform="translate({cx:g},{top - 6}) rotate(-55)">'
                       f"{_x(pid)}</text>")
    out.append(f'<text class="ink2" x="{right + 8}" y="{top - 8}" font-size="11">pass rate</text>')
    for i, (r, subtitle) in enumerate(zip(rows, subtitles)):
        y = top + i * pitch
        standing = f"{r['rank']}  " if "rank" in r else ""
        out.append(f'<text class="ink" x="16" y="{y + 15}" font-size="13" font-weight="600">'
                   f"{standing}{_x(r['name'])}</text>")
        out.append(f'<text class="ink2" x="16" y="{y + 29}" font-size="10.5">{_x(subtitle)}</text>')
        for pid, p in r["probes"].items():
            cx = xs[pid]
            tip = (f"{r['name']} · {pid} ({p['tier']}): {p['passes']} of {p['attempts']} passed"
                   + (f" ({p['marks']})" if p["marks"] else ""))
            if not p["attempts"]:
                out.append(f'<g><title>{_x(r["name"])} · {_x(pid)}: not run yet</title>'
                           f'<rect class="none" x="{cx + 0.5}" y="{y + 0.5}" width="{cell - 1}" '
                           f'height="{pitch - gap - 1}" rx="4"/></g>')
                continue
            step = _step(p["passes"], p["attempts"])
            label = str(p["passes"]) if p["attempts"] == b["k"] else f"{p['passes']}/{p['attempts']}"
            size = 12 if len(label) == 1 else 9
            out.append(f'<g><title>{_x(tip)}</title>'
                       f'<rect class="c{step}" x="{cx}" y="{y}" width="{cell}" height="{pitch - gap}" rx="4"/>'
                       f'<text class="t{step}" x="{cx + cell / 2:g}" y="{y + (pitch - gap) / 2 + 4:g}" '
                       f'font-size="{size}" text-anchor="middle">{label}</text></g>')
        score = _pct(r["score"])
        out.append(f'<text class="ink" x="{right + 8}" y="{y + 15}" font-size="13" font-weight="600">{score}</text>')
        out.append(f'<text class="ink2" x="{right + 8}" y="{y + 29}" font-size="10.5">'
                   + (_x(_ci(r)) if "rank" in r else f"{r['passes']}/{r['valid']} so far") + "</text>")
    y = top + max(len(rows), 1) * pitch + 24
    out.append(f'<text class="ink2" x="16" y="{y + 12}" font-size="11">passed, of k = {b["k"]}:</text>')
    x = 118
    for step, label in ((0, "0"), (1, "1"), (2, "2"), (3, "3")):
        out.append(f'<rect class="c{step}" x="{x}" y="{y}" width="{cell}" height="18" rx="4"/>'
                   f'<text class="t{step}" x="{x + cell / 2:g}" y="{y + 13}" font-size="11" '
                   f'text-anchor="middle">{label}</text>')
        x += cell + 6
    out.append(f'<rect class="none" x="{x + 0.5}" y="{y + 0.5}" width="{cell - 1}" height="17" rx="4"/>'
               f'<text class="ink2" x="{x + cell + 6}" y="{y + 13}" font-size="11">not run yet; '
               "a row still short of k shows passes/attempts</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def files(b: Dict[str, Any]) -> Dict[str, str]:
    """Every file the board is, by path under the output folder."""
    out = {"TRACK_P.md": render_board(b),
           "track_p.json": json.dumps(b, indent=1, ensure_ascii=False) + "\n",
           "track_p.svg": render_svg(b)}
    for r in b["ranked"] + b["unranked"]:
        out[r["card"]] = render_card(r, b)
    return out


def write(b: Dict[str, Any], out_dir: Path) -> List[Path]:
    out_dir = Path(out_dir)
    wanted = files(b)
    cards = out_dir / "cards"
    if cards.is_dir():
        for stale in cards.glob("*.md"):
            if f"cards/{stale.name}" not in wanted:
                stale.unlink()
    written = []
    for rel, text in wanted.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)
    return written


def check(b: Dict[str, Any], out_dir: Path) -> List[str]:
    """The paths that differ from what the run folders give: stale, edited, missing or extra."""
    out_dir = Path(out_dir)
    wanted = files(b)
    stale = [rel for rel, text in wanted.items()
             if not (out_dir / rel).exists() or (out_dir / rel).read_text() != text]
    cards = out_dir / "cards"
    if cards.is_dir():
        stale += [f"cards/{p.name}" for p in sorted(cards.glob("*.md")) if f"cards/{p.name}" not in wanted]
    return stale

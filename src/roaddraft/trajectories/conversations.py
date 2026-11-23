"""Eval episode files as training conversations (training plan section 3,
*Format*; section 5, step 3).

A training example is the harness's own conversation: what an E3 LLM agent
sends the model at eval, rebuilt from an episode file.  The grounded
recorder (``trajectories.grounded``) writes ordinary episode files, and so
does every model run, so one code path serves the references now and a
model's rollouts later (T2).  Nothing is copied from the harness: each piece
comes from the harness's own code, so a change there moves the conversation
with it.

- *System*: an LLM agent's header carries the prompt it sent, which is used
  as is.  An episode whose agent had none (the grounded drafter) gets what
  ``agents.llm.system_for`` gives an LLM agent under the episode's mode and
  budgets: ``system_neutral.md`` with its budgets filled.
- *Tools*: ``eval.tools.tool_definitions`` for the episode's mode and scope,
  held to the digest in the episode's header.  They are kept once per digest
  (``tools.json``), in the shape the OpenAI-compatible provider sends them
  (``providers.openai_compat.function_tools``); a conversation names its set
  by digest.
- *Task*: ``tasks.prompts.task_text`` at the episode's level, the task rebuilt
  from its manifest and held to the header's prompt hash.
- *Turns*: the assistant's text and its calls (a call's arguments as an
  object, which a chat template renders), then the turn's results as the
  agent hands them back (``LLMAgent._results``: the bus result as compact
  JSON, a call the turn never ran as ``not_run``) and the ``[harness]`` note
  when few steps or faults are left, laid out as
  ``openai_compat.chat_messages`` lays them out: one ``tool`` message per
  result, the note as a user message after them.
- *End*: the model's last turn, a ``submit`` call whose note is the closing
  report, or text with no call (an implicit submit).  Its results are never
  shown to the model and are not in the conversation.

A model's thinking is not sent back by the harness (``openai_compat``), so it
is not in the conversation either.

A faulted copy of a reference (``trajectories.faults``) converts the same way:
its broken turns' assistant messages carry ``"weight": 0`` (context, never a
target), its header lists the faults (``injected``) and its id ends
``.faults``; the audit leaves the broken turns' own findings out.

**Kept**, and counted by reason when not (``Drop``):

1. the episode ended on ``submit`` in a text-only mode (a vision episode's
   images never reach its file), with no turn the agent had to nudge (the
   record joins a nudged turn's replies into one);
2. the task its manifest rebuilds has the episode's prompt hash, truth and
   starting document, and the tool definitions for its mode and scope have
   its tool digest: the episode is this checkout's task on this checkout's
   tools;
3. its journal, replayed and re-scored by the verifier, scores 100;
4. the grounded audit finds nothing ungrounded, lettering on a twisted sheet
   was made for the twist, and nothing on a revised sheet was left stale:
   the recorder's keep rule, applied again so a rollout is held to it too.

A run given ``--system-extra`` hashes its task text and the extra together
(``eval.episode.prompt_hash``).  Its episodes are held to that hash with the
extra their header records, file and digest: the text is read from the file
where it still has the digest, else from the end of the system prompt as
sent, and held to the digest either way.  The conversation's system prompt
is the prompt as sent, the extra in it.

**Probe tasks.**  The generated reasoning sets (``train-deeds``,
``train-qa``: ``tasks.deeds``, ``tasks.planted``) record their references on
the pilots' harness (``eval.probe_tasks.ProbeEpisode``), and their episode
files convert beside the D1 sets'.  The pieces are that harness's:

- *System*: the agent's own where its header carries one, else what
  ``ProbeEpisode`` hands an agent's ``begin`` under the episode's mode and
  budgets (``probe_tasks.system_prompt``: the MCP server's instructions,
  then how the task runs).
- *Tools*: the list ``ProbeEpisode.reset`` builds, the MCP server's tools and
  the harness's, held to the header's digest.
- *Task*: the text the harness sends (``probe_tasks.brief_text``, the probe
  runner's ``prompting.task_text``), the task rebuilt from its manifest at
  the episode's level.
- *Turns* and *End*: as above; a probe episode runs the same loop.

A probe episode's journal is not a list of commands (the MCP server saves the
files itself), so the episode is played again instead: its recorded calls
through a new ``ProbeEpisode`` on the manifest's task.  It is kept when every
call answers as the episode recorded (the start documents and the engine are
the episode's), the task's own check passes on the files the replay leaves,
and ``trajectories.reasoning.audit`` finds nothing ungrounded.  An episode
that looked at an attachment is dropped as ``vision``: the scan it was sent
is not in its file.

**A model's rollouts (stage T2).**  ``rollouts RUN_DIR --taskset NAME`` converts
a model run on a T2 round's manifest (``eval.t2``).  The grounded audit of rule 4
reads the shown work of the scripted drafter and a model's turns do not pass it
(the plain oracle does not either), so a rollout is held to rules 1 to 3 and to
the two parts of rule 4 that read the finished document and not the turns
(``audit="document"``): lettering on a twisted sheet made for the twist, nothing
left stale on a revised sheet.  ``--audit none`` holds it to rules 1 to 3 alone.
So a rollout is kept when it submitted and its journal re-scores an effective
100 on the manifest's task and this checkout's tools, and is dropped otherwise,
the reasons tallied.  Of several samples of one task at one level the first
kept is written.  Only a T2 manifest's run converts this way: a run on a
held-out set is never training data, and a rollout on a reference set's task
would take a reference's id.

``python -m roaddraft.trajectories.conversations convert`` writes one JSONL
of conversations per training set and level into ``results/training/``,
``tools.json`` and ``summary.json``; ``scripts/training_tokens.py`` counts
their tokens with the subject model's tokenizer (``tokens.json``); ``card``
writes the dataset card, ``benchmarks/training/DATASET_CARD.md``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

FORMAT = "roaddraft-d1-conversation/1"
REPO = Path(__file__).resolve().parents[3]
#: the current recordings, <set>-<level>/ each.  ``results/grounded`` and
#: ``results/faults`` hold the ones made before the tool pin (superseded, see the
#: SUPERSEDED.md in each) and are no longer any command's default.
SOURCE = REPO / "results" / "grounded-v2"
#: the faulted copies of the references (``trajectories.faults``), <set>-<level>/ each
FAULTS = REPO / "results" / "faults-v2"
#: ``run``'s faults when none is named: ``FAULTS`` for the recordings in ``SOURCE``, the
#: references they were made from, and no faulted copies for any other source
PAIRED = "paired"
OUT = REPO / "results" / "training"
CARD = REPO / "benchmarks" / "training" / "DATASET_CARD.md"
LEVELS = ("vague", "explicit")
#: modes whose episodes are text only: a vision episode's images are never written to its file
TEXT_MODES = ("single", "self_correct")
#: ``audit="document"``: the checks of the finished document only (a model's rollout)
DOCUMENT = "document"
#: why an episode is not a training example, in the order the checks run
REASONS = ("not_submitted", "vision", "nudged", "no_task", "prompt", "truth", "start", "tools",
           "replay", "score", "ungrounded", "twist_ignored", "left_stale", "error")


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def tools_sha256(tools: Sequence[dict]) -> str:
    """An episode header's ``tools_sha256``: the digest of the definitions as
    ``Episode.header`` takes it."""
    return digest(json.dumps(list(tools), sort_keys=True))


class Drop(Exception):
    """An episode that is not a training example, and why."""

    def __init__(self, reason: str, detail: str = ""):
        if reason not in REASONS:
            raise ValueError(f"unknown drop reason {reason!r}")
        self.reason, self.detail = reason, detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# ------------------------------------------------------------ the harness's pieces

_CACHE: Dict[str, object] = {}


def _manifest() -> dict:
    if "manifest" not in _CACHE:
        from roaddraft.api.session import Session
        _CACHE["manifest"] = Session().manifest()
    return _CACHE["manifest"]


def tool_set(mode: str, scope: Iterable[str]) -> Tuple[List[dict], str]:
    """The tool definitions an episode in ``mode`` on a task with ``scope``
    is shown, and their digest."""
    key = f"tools|{mode}|{json.dumps(list(scope))}"
    if key not in _CACHE:
        from roaddraft.eval.tools import tool_definitions
        defs = tool_definitions(_manifest(), mode, list(scope))
        _CACHE[key] = (defs, tools_sha256(defs))
    return _CACHE[key]


def function_tools(defs: Sequence[dict]) -> List[dict]:
    """The definitions as the OpenAI-compatible provider sends them."""
    from roaddraft.eval.providers.openai_compat import function_tools as sent
    return sent(list(defs))


def budgets_of(header: dict):
    from roaddraft.eval.budget import Budgets
    known = {f.name for f in fields(Budgets)}
    return Budgets(**{k: v for k, v in (header.get("budgets") or {}).items() if k in known})


def system_text(header: dict, extra=None) -> str:
    """The system prompt the episode's model was sent, or, for an agent that
    had none, the one an LLM agent is sent under the same mode and budgets,
    the run's system extra (``system_extra_of``) after it when it had one."""
    if header.get("system_prompt"):
        return header["system_prompt"]
    from roaddraft.eval.agents.llm import system_for
    context = {"mode": header.get("mode", "single"), "level": header.get("level"),
               "dialect": header.get("dialect", "neutral"), "budgets": budgets_of(header),
               "scope": header.get("scope") or []}
    if extra is not None:
        context["system_extra"] = extra.text
    return system_for(context)


def system_extra_of(header: dict):
    """The system extra the episode's run was given (``--system-extra``), or
    None.  The header records its file and digest, not its text.  The text is
    read from the file where the file still has that digest; else it is taken
    from the end of the system prompt as sent, where the agent put it
    (``prompts.with_extra``), and held to the digest.  ``Drop("prompt")``
    when neither gives the text the run hashed."""
    recorded = header.get("system_extra")
    if not recorded:
        return None
    from roaddraft.eval.prompts import SystemExtra
    want = recorded.get("sha256")
    shown = str(recorded.get("path") or "")
    path = Path(shown)
    if shown:
        try:
            extra = SystemExtra.load(path if path.is_absolute() else REPO / path)
        except ValueError:
            extra = None
        if extra is not None and extra.sha256 == want:
            return extra
    # with_extra puts the stripped text last, after a blank line: the file is that text,
    # with a closing newline or without
    sent = header.get("system_prompt") or ""
    at = sent.find("\n\n")
    while at >= 0:
        tail = sent[at + 2:].strip()
        for text in (tail + "\n", tail):
            if text and digest(text) == want:
                return SystemExtra(path=shown, sha256=want, text=text)
        at = sent.find("\n\n", at + 1)
    raise Drop("prompt", f"the run's system extra ({shown}, {want}) is not on disk with that "
                         "digest and is not the end of the system prompt as sent")


def held_to_prompt(header: dict, brief: str):
    """Hold ``brief`` to the header's prompt hash as the episode took it
    (``eval.episode.prompt_hash``: the task text, and with a system extra the
    two together), or ``Drop("prompt")``.  The run's system extra, or None."""
    from roaddraft.eval.episode import prompt_hash
    extra = system_extra_of(header)
    if prompt_hash(brief, extra) != header.get("prompt_hash"):
        raise Drop("prompt", "the task text at its level is not the one the episode was given")
    return extra


def _agent():
    """An LLM agent, for its ``_results``: how each turn's results go back."""
    if "agent" not in _CACHE:
        from roaddraft.eval.agents.llm import LLMAgent
        from roaddraft.eval.providers.fake import FakeProvider
        _CACHE["agent"] = LLMAgent(FakeProvider(), label="converter")
    return _CACHE["agent"]


def messages(system: str, brief: str, turns: Sequence[dict], budgets) -> List[dict]:
    """The conversation of an episode's turn records, as the model was sent
    it and answered: system, the task, then per turn the assistant message and
    what came back, up to the last assistant message."""
    from roaddraft.eval.providers.base import Call
    from roaddraft.eval.providers.openai_compat import chat_messages
    agent = _agent()
    out: List[dict] = [{"role": "system", "content": system}, {"role": "user", "content": brief}]
    steps = in_a_row = n = 0
    for i, turn in enumerate(turns):
        said = turn.get("assistant") or {}
        calls = []
        for c in said.get("tool_calls") or []:
            n += 1
            calls.append(Call(f"call_{n:04d}", c["name"], dict(c.get("params") or {})))
        text = said.get("text") or ""
        # a closing turn that said nothing is recorded with its submit note as its text
        # (Episode.run): the note is the submit call's argument already, and is written once
        if said.get("submit") and calls and calls[-1].name == "submit" \
                and text == str(calls[-1].params.get("note") or ""):
            text = ""
        message = {"role": "assistant", "content": text}
        if calls:
            message["tool_calls"] = [{"id": c.id, "type": "function",
                                      "function": {"name": c.name, "arguments": c.params}}
                                     for c in calls]
        if (said.get("fault") or {}).get("role") == "broken":
            message["weight"] = 0   # an injected mistake: context for the recovery, never a target
        out.append(message)
        if i == len(turns) - 1:
            break
        results = list(turn.get("results") or [])
        # the budget the observation carries after this turn (BudgetState.remaining)
        steps += len(results)
        if results:
            in_a_row = 0 if any(r.get("ok") for r in results) else in_a_row + 1
        budget = {"steps": max(0, budgets.steps - steps),
                  "faults_before_stop": max(0, budgets.faults - in_a_row)}
        agent._pending = calls
        back = agent._results({"results": results, "budget": budget})
        out.extend(chat_messages("", [back])[1:])
    return out


# ------------------------------------------------------------ one episode

def _entries(taskset: str, root=None) -> Dict[str, dict]:
    key = f"entries|{taskset}" + (f"|{root}" if root else "")
    if key not in _CACHE:
        from roaddraft.eval import taskset as tasksets
        _CACHE[key] = {e["task_id"]: e for e in tasksets.entries(taskset, root=root)}
    return _CACHE[key]


def rebuild_task(taskset: str, task_id: str, level: Optional[str] = None, root=None):
    """The task ``task_id`` of the ``taskset`` manifest (under ``root``; default
    the repo's task sets).  A probe task is its own id at each prompt level
    and is built posed at ``level``; a D1 task is the same at every level."""
    from roaddraft.eval import taskset as tasksets
    entry = _entries(taskset, root).get(task_id)
    if entry is None and level == "vague":
        entry = next((e for e in _entries(taskset, root).values()
                      if e.get("vague_task_id") == task_id), None)
    if entry is None:
        raise Drop("no_task", f"{task_id} is not in the {taskset} manifest")
    if "generated" in entry or "probe" in entry:
        want = entry.get("vague_task_id") if level == "vague" else entry["task_id"]
        if want != task_id:
            raise Drop("no_task", f"{task_id} is not the {taskset} manifest's task at the "
                                  f"{level} level")
        return tasksets.task_from_entry(entry, level=level or "explicit")
    return tasksets.task_from_entry(entry)


@dataclass
class Example:
    """What one episode came to: a conversation and the tool definitions it
    names, or the reason it was dropped."""
    path: str
    task_id: Optional[str] = None
    task_type: Optional[str] = None
    conversation: Optional[dict] = None
    tools: Optional[List[dict]] = None
    drop: Optional[str] = None
    detail: str = ""


def convert_episode(path, taskset: str, audit: Union[bool, str] = True,
                    root=None) -> Tuple[dict, List[dict]]:
    """The training conversation of one episode file and the tool definitions
    it names, or ``Drop``.  ``taskset`` is the manifest that rebuilds its task
    (read under ``root``; default the repo's task sets).  ``audit``: True for
    the whole of keep rule 4, ``"document"`` for its checks of the finished
    document alone (a model's rollout), False for none of it."""
    from roaddraft.eval.trajectory import read_episode, replay_journal
    from roaddraft.tasks.brief import GroundTruth
    from roaddraft.tasks.prompts import task_text
    from roaddraft.verify import VERIFIER_VERSION, verify

    records = read_episode(path)
    header, end, journal = records["header"], records["end"], records["journal"]
    turns = records["turns"]
    if header is None or end is None or journal is None or not turns:
        raise Drop("not_submitted", "the file has no header, end or journal record")
    if end.get("termination") != "submit":
        raise Drop("not_submitted", f"termination {end.get('termination')}")
    mode = header.get("mode", "single")
    if mode not in TEXT_MODES:
        raise Drop("vision", f"mode {mode}: the images it was sent are not in the file")
    nudged = [t["n"] for t in turns if (t.get("assistant") or {}).get("nudges")]
    if nudged:
        raise Drop("nudged", f"turns {nudged}")

    level = header["level"]
    if header.get("probe") or journal.get("probe"):
        return _convert_probe(path, taskset, records, audit, root)
    task = rebuild_task(taskset, header["task_id"], root=root)
    if getattr(task, "probe", None) is not None:
        raise Drop("no_task", f"{header['task_id']} is a probe task of {taskset}, the episode "
                              "is not a probe episode")
    brief = task_text(task.brief, level)
    extra = held_to_prompt(header, brief)
    if task.truth.to_dict() != journal.get("truth"):
        raise Drop("truth", "the manifest's task grades differently from the episode's truth")
    if task.baseline != journal.get("baseline"):
        raise Drop("start", "the manifest's task starts from another document")
    defs, tools_digest = tool_set(mode, header.get("scope") or [])
    if tools_digest != header.get("tools_sha256"):
        raise Drop("tools", f"the tools for its scope digest to {tools_digest}, "
                            f"the episode was shown {header.get('tools_sha256')}")

    session = replay_journal(journal)
    report = verify(session.doc, GroundTruth.from_dict(journal["truth"]),
                    journal=session.bus.journal, prompt_level=level)
    if report.effective_score < 100.0:
        raise Drop("score", f"re-scored {report.effective_score:g}")
    if journal.get("opened"):
        # an episode that changed another document (a revision made in the base drawing):
        # what the sheet file had read of that document when, and so what it ended up
        # showing, is not all in the journal, so the replay can score what the episode did
        # not.  Kept only when the episode's own score, taken as it ended, was 100 too
        live = (records.get("verify") or {}).get("effective_score")
        if live is None or float(live) < 100.0:
            raise Drop("score", f"scored {live} as it ended, {report.effective_score:g} "
                                f"replayed from its journal")
    if audit:
        from roaddraft.tasks.revise import left_stale
        from roaddraft.trajectories import faults, grounded
        # an injected fault's broken turn is wrong on purpose and weighs 0: its own findings are left out
        found = faults.audit_turns(brief, defs, turns) if audit != DOCUMENT else []
        if found:
            raise Drop("ungrounded", json.dumps(found[:3], ensure_ascii=False))
        blind = grounded.twist_ignored(task, session.doc)
        if blind:
            raise Drop("twist_ignored", ", ".join(blind[:5]))
        behind = left_stale(task, session.doc)
        if behind:
            raise Drop("left_stale", ", ".join(behind[:5]))

    system = system_text(header, extra)
    msgs = messages(system, brief, turns, budgets_of(header))
    return _conversation(path, taskset, header, turns, msgs, system, tools_digest,
                         VERIFIER_VERSION, report), defs


def _conversation(path, taskset: str, header: dict, turns: Sequence[dict], msgs: List[dict],
                  system: str, tools_digest: str, verifier: str, report,
                  more: Optional[dict] = None) -> dict:
    """The conversation record of a kept episode: its id, the header of pins
    and counts (``more``: what a kind of episode adds or replaces), and the
    messages."""
    level, mode = header["level"], header.get("mode", "single")
    calls = sum(len((t.get("assistant") or {}).get("tool_calls") or []) for t in turns)
    results = [r for t in turns[:-1] for r in t.get("results") or []]
    held = []
    if any(t.get("usage") for t in turns):
        from roaddraft.eval.agents.llm import prompt_size
        held = [prompt_size(t.get("usage")) for t in turns]
    from roaddraft.trajectories.faults import faults_of
    injected = faults_of(turns)
    head = {
        "task_id": header["task_id"], "taskset": taskset, "task_type": header.get("task_type"),
        "seed": header.get("seed"), "sheets": header.get("sheets"), "level": level, "mode": mode,
        "scope": header.get("scope") or [],
        "source": "reference" if header.get("provider") == "harness" else "rollout",
        "agent": header.get("agent"), "model": header.get("model"),
        "tools_sha256": tools_digest, "prompt_hash": header["prompt_hash"],
        "system_sha256": digest(system),
        "spec_version": header.get("spec_version"), "spec_hash": header.get("spec_hash"),
        "generator_version": header.get("generator_version"),
        "verifier_version": verifier, "harness_version": header.get("harness_version"),
        "recorded_commit": header.get("git_commit"), "recorded_at": header.get("started_at"),
        "score": {"effective": report.effective_score, "rubric": report.rubric_score},
        "counts": {"turns": len(turns), "calls": calls, "results_shown": len(results),
                   "faults": sum(not r.get("ok") for r in results),
                   "notes": sum(1 for m in msgs[2:] if m["role"] == "user"),
                   "masked": sum(1 for m in msgs if m.get("weight") == 0)},
        "episode": _shown_path(path),
    }
    head.update(more or {})
    if header.get("system_extra"):
        # the run's --system-extra, file and digest: its text is in the system prompt
        head["system_extra"] = dict(header["system_extra"])
    if injected:
        head["injected"] = injected   # the faults put in (trajectories.faults): their broken turns weigh 0
    if any(held):
        head["prompt_tokens"] = held   # what the server counted for each request, for calibration
    cid = f"{header['task_id']}.{level}" + (".faults" if injected else "")
    return {"format": FORMAT, "id": cid, "header": head, "messages": msgs}


# ------------------------------------------------------------ one probe episode

#: the MCP server's tool that returns a scan: its image goes to the model and not to the file
ATTACHMENT_TOOL = "view_attachment"


def _replay_agent(turns: Sequence[dict]):
    """An agent that makes an episode's recorded calls again, turn by turn,
    and keeps the context its episode hands ``begin``."""
    from roaddraft.eval.agents import Agent, Submit, ToolCall

    class Replay(Agent):
        name = "replay"

        def __init__(self):
            self.context: dict = {}
            self.n = 0

        def begin(self, context: dict) -> None:
            self.context = dict(context)

        def act(self, observation: dict):
            said = turns[self.n].get("assistant") or {}
            self.n += 1
            calls = said.get("tool_calls") or []
            if not calls:
                return Submit(note=said.get("text") or "", implicit=bool(said.get("implicit_submit")))
            return [ToolCall(c["name"], json.loads(json.dumps(c.get("params") or {}))) for c in calls]

    return Replay()


def _plain(value):
    """``value`` as it reads back from an episode file."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def _convert_probe(path, taskset: str, records: dict, audit: Union[bool, str],
                   root=None) -> Tuple[dict, List[dict]]:
    """``convert_episode`` for a probe-task episode (``eval.probe_tasks``)."""
    from roaddraft.eval.agents.llm import system_for
    from roaddraft.eval.episode import EpisodeConfig
    from roaddraft.eval.probe_tasks import ProbeEpisode

    header, journal, turns = records["header"], records["journal"], records["turns"]
    level, mode = header["level"], header.get("mode", "single")
    looked = [t["n"] for t in turns
              if any(c.get("name") == ATTACHMENT_TOOL
                     for c in (t.get("assistant") or {}).get("tool_calls") or [])]
    if looked:
        raise Drop("vision", f"turns {looked} looked at an attachment: the scan is not in the file")
    task = rebuild_task(taskset, header["task_id"], level, root)
    probe = getattr(task, "probe", None)
    if probe is None:
        raise Drop("no_task", f"{header['task_id']} is not a probe task of {taskset}")
    brief = task.brief
    extra = held_to_prompt(header, brief)
    if (probe.id, probe.start) != (journal.get("probe"), journal.get("start")):
        raise Drop("start", f"the manifest's task is probe {probe.id} on start {probe.start}, the "
                            f"episode ran {journal.get('probe')} on {journal.get('start')}")

    # the episode again, on the manifest's task: the harness builds the start, the tool list
    # and the system prompt itself, and every recorded call is made on them
    budgets = budgets_of(header)
    agent = _replay_agent(turns)
    episode = ProbeEpisode(task, agent, EpisodeConfig(
        level=level, mode=mode, dialect=header.get("dialect", "neutral"), budgets=budgets,
        sample=int(header.get("sample") or 0), system_extra=extra))
    result = episode.run()
    defs = _plain(episode.tools)
    tools_digest = tools_sha256(defs)
    if tools_digest != header.get("tools_sha256"):
        raise Drop("tools", f"the task's tools digest to {tools_digest}, "
                            f"the episode was shown {header.get('tools_sha256')}")
    again = _plain(episode.turns)
    for was, now in zip(turns, again):
        got, want = now.get("results") or [], was.get("results") or []
        if got != want:
            k = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            name = (want[k] if k < len(want) else got[k]).get("name")
            raise Drop("replay", f"turn {was.get('n')}, call {k + 1} ({name}) answers differently "
                                 "on the manifest's task: the start documents or the engine are "
                                 "not the episode's")
    if result.termination != "submit" or len(again) != len(turns):
        raise Drop("replay", f"played again it ended on {result.termination} after {len(again)} "
                             f"turns ({result.error or 'no error'}), the episode submitted after "
                             f"{len(turns)}")
    report = result.report
    if report.effective_score < 100.0:
        raise Drop("score", f"the task's check fails on the replayed files: "
                            f"{str(getattr(report, 'detail', ''))[:160]}")
    if audit and audit != DOCUMENT:
        from roaddraft.trajectories import faults, reasoning
        broken = faults.broken_turns(turns)
        found = [f for f in reasoning.audit(brief, defs, turns) if f.get("turn") not in broken]
        if found:
            raise Drop("ungrounded", json.dumps(found[:3], ensure_ascii=False))

    # an agent's own system prompt as sent; else what the harness's begin context asks for
    system = header.get("system_prompt") or system_for(agent.context)
    msgs = messages(system, brief, turns, budgets)
    more = {"harness": "probe", "probe": probe.id, "start": probe.start,
            "seed": _entry_seed(taskset, header["task_id"], header.get("seed"), root)}
    return _conversation(path, taskset, header, turns, msgs, system, tools_digest,
                         report.verifier_version, report, more), defs


def _entry_seed(taskset: str, task_id: str, default=None, root=None):
    """The seed a generated probe task was made from, which its episode header does not
    carry: the manifest entry's."""
    for e in _entries(taskset, root).values():
        if task_id in (e.get("task_id"), e.get("vague_task_id")):
            return e.get("seed", default)
    return default


def _shown_path(path) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def convert(path, taskset: str, audit: Union[bool, str] = True, root=None) -> Example:
    """``convert_episode`` with a drop, or any failure, kept as the reason."""
    ex = Example(path=str(path))
    try:
        conversation, defs = convert_episode(path, taskset, audit=audit, root=root)
    except Drop as d:
        ex.drop, ex.detail = d.reason, d.detail
    except Exception as exc:  # a broken file is counted, not fatal to the set
        ex.drop, ex.detail = "error", f"{type(exc).__name__}: {exc}"
    else:
        ex.conversation, ex.tools = conversation, defs
        ex.task_id, ex.task_type = conversation["header"]["task_id"], conversation["header"]["task_type"]
    return ex


def _convert_job(job: tuple) -> Example:
    return convert(*job)


# ------------------------------------------------------------ a set

def sources(src: Path) -> Tuple[List[Path], dict]:
    """The episode files of a recording folder to convert, and what the
    recorder said of the rest: with an ``index.json`` (the grounded recorder)
    its kept rows; without one, every episode file."""
    index_path = src / "index.json"
    if not index_path.exists():
        return sorted((src / "episodes").glob("*.jsonl")), {}
    index = json.loads(index_path.read_text())
    paths, rows = [], index.get("rows") or []
    for row in rows:
        if row.get("kept"):
            paths.append(src / "episodes" / Path(row["path"]).name)
    # the reasoning recorder (probe tasks) has no notion of covered: every task has a drafter
    covered = sum(bool(r.get("covered")) for r in rows) if any("covered" in r for r in rows) else None
    recorder = {"tasks": index.get("tasks", len(rows)),
                "covered": index.get("covered", covered),
                "kept": index.get("kept", len(paths)),
                "taskset": index.get("taskset"), "level": index.get("level")}
    return paths, recorder


def _stats(values: Sequence[int]) -> dict:
    if not values:
        return {}
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def convert_set(src: Path, taskset: str, out_file: Path, jobs: int = 1,
                audit: Union[bool, str] = True,
                limit: Optional[int] = None, pins: Optional[dict] = None,
                log=None, paths: Optional[Sequence[Path]] = None, root=None,
                one_per_id: bool = False) -> Tuple[dict, Dict[str, List[dict]]]:
    """Convert one recording folder into ``out_file`` (JSONL, one conversation
    a line, by task id): the set's tally and the tool sets it names.  With
    ``paths``, those episode files of the folder and no other; ``root`` is
    where the ``taskset`` manifest is read; ``one_per_id`` writes the first
    kept conversation of an id (a run of several samples a task) and counts
    the rest under ``more_samples``."""
    if paths is None:
        paths, recorder = sources(Path(src))
    else:
        paths, recorder = list(paths), {}
    paths = paths[:limit] if limit is not None else paths
    jobs_list = [(str(p), taskset, audit) + ((str(root),) if root else ()) for p in paths]
    if jobs > 1 and len(jobs_list) > 1:
        from multiprocessing import get_context
        with get_context("spawn").Pool(jobs) as pool:
            examples = pool.map(_convert_job, jobs_list, chunksize=8)
    else:
        examples = [_convert_job(j) for j in jobs_list]
    kept = sorted((e for e in examples if e.conversation), key=lambda e: e.task_id)
    dropped = [e for e in examples if not e.conversation]
    more = 0
    if one_per_id:
        first: Dict[str, Example] = {}
        for e in kept:   # (the sort is stable: a task's samples stay in file order)
            first.setdefault(e.conversation["id"], e)
        more, kept = len(kept) - len(first), list(first.values())
    tools: Dict[str, List[dict]] = {}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(out_file.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for e in kept:
            conv = e.conversation
            if pins:
                conv["header"]["git_commit"] = pins.get("commit")
                conv["header"]["git_dirty"] = bool(pins.get("dirty"))
            tools.setdefault(conv["header"]["tools_sha256"], e.tools)
            fh.write(json.dumps(conv, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(out_file)
    heads = [e.conversation["header"] for e in kept]
    reasons = Counter(e.drop for e in dropped)
    tally = {
        "file": out_file.name, "source": _shown_path(src), "taskset": taskset,
        "level": recorder.get("level") or (heads[0]["level"] if heads else None),
        "recorder": recorder, "episodes": len(paths), "kept": len(kept),
        "dropped": {r: reasons[r] for r in REASONS if reasons[r]},
        "dropped_examples": {r: [(Path(e.path).name, e.detail[:200]) for e in dropped if e.drop == r][:5]
                             for r in REASONS if reasons[r]},
        "by_type": dict(sorted(Counter(h["task_type"] for h in heads).items())),
        "seeds": [min(h["seed"] for h in heads), max(h["seed"] for h in heads)] if heads else None,
        "tools": dict(Counter(h["tools_sha256"] for h in heads)),
        "turns": _stats([h["counts"]["turns"] for h in heads]),
        "calls": _stats([h["counts"]["calls"] for h in heads]),
        "with_notes": sum(1 for h in heads if h["counts"]["notes"]),
    }
    if any(h.get("harness") == "probe" for h in heads):
        tally["harness"] = "probe"   # episodes of the pilots' harness (eval.probe_tasks)
    if one_per_id:
        tally["more_samples"] = more   # kept too, and not written: a later sample of a written task
    kinds = Counter(f["kind"] for h in heads for f in h.get("injected") or [])
    if kinds:
        tally["injected"] = dict(sorted(kinds.items()))
        tally["masked"] = sum(h["counts"].get("masked", 0) for h in heads)
    if log:
        log(f"{out_file.name}: {len(kept)} kept of {len(paths)} episodes"
            + (f"; dropped {dict(reasons)}" if reasons else ""))
    return tally, tools


def manifest_seeds(taskset: str, root=None) -> Optional[List[int]]:
    from roaddraft.eval import taskset as tasksets
    seeds = [e["seed"] for e in tasksets.entries(taskset, root=root) if "seed" in e]
    return [min(seeds), max(seeds)] if seeds else None


def write_tools(out: Path, tools: Dict[str, List[dict]]) -> Path:
    """``tools.json``: each tool set once, by digest: the harness's
    definitions (what the digest is over) and the function tools the
    OpenAI-compatible provider sends."""
    path = out / "tools.json"
    doc = {}
    if path.exists():
        doc = json.loads(path.read_text())
    for dig, defs in sorted(tools.items()):
        doc[dig] = {"count": len(defs), "names": [d["name"] for d in defs],
                    "definitions": defs, "function_tools": function_tools(defs)}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return path


def run(sets: Sequence[str], levels: Sequence[str] = LEVELS, source: Path = SOURCE,
        out: Path = OUT, jobs: int = 1, audit: bool = True, limit: Optional[int] = None,
        log=print, faults: Union[Path, str, None] = PAIRED) -> dict:
    """Convert every ``<set>-<level>`` recording folder under ``source`` and,
    where ``faults`` holds one, its faulted copies (``trajectories.faults``)
    into ``<set>-<level>-faults.jsonl``.  With no ``faults`` named, the
    recordings in ``SOURCE`` take the copies in ``FAULTS`` and any other
    source takes none.  ``summary.json`` describes every set the folder
    holds: a set an earlier call wrote and this one did not keeps its tally."""
    from roaddraft import __version__
    from roaddraft.eval.episode import HARNESS_VERSION
    from roaddraft.runners.core import pins as current_pins
    from roaddraft.verify import VERIFIER_VERSION
    out = Path(out)
    if isinstance(faults, str) and faults == PAIRED:
        faults = FAULTS if Path(source).resolve() == SOURCE.resolve() else None
    pins = current_pins()
    started = time.time()
    summary = {"format": FORMAT, "made_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "roaddraft": __version__, "git_commit": pins.get("commit"),
               "git_dirty": pins.get("dirty") or [], "verifier_version": VERIFIER_VERSION,
               "harness_version": HARNESS_VERSION, "audit": audit, "sets": {}}
    all_tools: Dict[str, List[dict]] = {}
    for name in sets:
        for level in levels:
            src = Path(source) / f"{name}-{level}"
            if not (src / "episodes").exists():
                log(f"{src}: no episodes, skipped")
                continue
            tally, tools = convert_set(src, name, out / f"{name}-{level}.jsonl", jobs=jobs,
                                       audit=audit, limit=limit, pins=pins, log=log)
            tally["manifest_seeds"] = manifest_seeds(name)
            summary["sets"][f"{name}-{level}"] = _stamped(tally, summary)
            for dig, defs in tools.items():
                all_tools.setdefault(dig, defs)
            faulted = Path(faults) / f"{name}-{level}" if faults else None
            if faulted is None or not (faulted / "episodes").exists():
                continue
            tally, tools = convert_set(faulted, name, out / f"{name}-{level}-faults.jsonl", jobs=jobs,
                                       audit=audit, limit=limit, pins=pins, log=log)
            tally["variant"] = "faults"
            summary["sets"][f"{name}-{level}-faults"] = _stamped(tally, summary)
            for dig, defs in tools.items():
                all_tools.setdefault(dig, defs)
    held = json.loads(write_tools(out, all_tools).read_text())
    _carry_forward(out, summary, log)
    # tools.json keeps the tool sets of every call, and so does the summary
    summary["tools"] = {dig: row["count"] for dig, row in sorted(held.items())}
    summary["seconds"] = round(time.time() - started, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def _level_of(path) -> Optional[str]:
    """The prompt level of an episode file, from its header (its first record)."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            first = json.loads(fh.readline() or "{}")
    except (OSError, ValueError):
        return None
    return first.get("level", "explicit") if first.get("type") == "header" else None


def run_rollouts(run_dir, taskset: str, out: Path = OUT, tasksets_root=None, jobs: int = 1,
                 audit: Union[bool, str] = DOCUMENT, limit: Optional[int] = None,
                 log=print) -> dict:
    """Convert a model's run on the T2 manifest ``taskset`` (``eval.t2``) into
    ``<taskset>-<level>.jsonl`` under ``out``, a file a prompt level, beside
    the references: the keep rule of the module's docstring, *A model's
    rollouts*.  ``summary.json`` and ``tools.json`` are carried on as ``run``
    carries them.  ``ValueError`` for a set that is not a T2 round's, a
    manifest that shares anything with another set, or a run made on another
    set."""
    from roaddraft import __version__
    from roaddraft.eval import taskset as tasksets
    from roaddraft.eval.episode import HARNESS_VERSION
    from roaddraft.runners.core import pins as current_pins
    from roaddraft.verify import VERIFIER_VERSION
    run_dir, out = Path(run_dir), Path(out)
    if not tasksets.is_t2(taskset):
        raise ValueError(f"{taskset}: rollouts convert for a T2 round's set only "
                         f"({tasksets.T2_PREFIX}<tag>): a run on a held-out set is never training "
                         "data, and a rollout on a reference set's task would take its reference's id")
    shared = tasksets.t2_overlap(tasksets.load(taskset, tasksets_root), tasksets_root)
    if shared:
        raise ValueError(f"{taskset} shares with another set; nothing converted: " + "; ".join(shared))
    meta_path = run_dir / "run.json"
    ran = ((json.loads(meta_path.read_text()).get("spec") or {}).get("taskset")
           if meta_path.exists() else None)
    if ran is not None and ran != taskset:
        raise ValueError(f"{run_dir} is a run on {ran}, not on {taskset}")
    files = sorted((run_dir / "episodes").glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"{run_dir}: no episodes under {run_dir / 'episodes'}")
    by_level: Dict[str, List[Path]] = {}
    unread = 0
    for path in files:
        level = _level_of(path)
        if level is None:
            unread += 1
        else:
            by_level.setdefault(level, []).append(path)
    pins = current_pins()
    started = time.time()
    summary = {"format": FORMAT, "made_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "roaddraft": __version__, "git_commit": pins.get("commit"),
               "git_dirty": pins.get("dirty") or [], "verifier_version": VERIFIER_VERSION,
               "harness_version": HARNESS_VERSION, "audit": audit, "sets": {}}
    all_tools: Dict[str, List[dict]] = {}
    for level in sorted(by_level, key=lambda lv: (LEVELS.index(lv) if lv in LEVELS else 99, lv)):
        tally, tools = convert_set(run_dir, taskset, out / f"{taskset}-{level}.jsonl", jobs=jobs,
                                   audit=audit, limit=limit, pins=pins, log=log,
                                   paths=by_level[level], root=tasksets_root, one_per_id=True)
        tally["level"] = level
        tally["variant"] = "rollouts"
        tally["run_id"] = run_dir.name
        tally["manifest_seeds"] = manifest_seeds(taskset, tasksets_root)
        summary["sets"][f"{taskset}-{level}"] = _stamped(tally, summary)
        for dig, defs in tools.items():
            all_tools.setdefault(dig, defs)
    if unread and log:
        log(f"{run_dir}: {unread} episode file(s) with no header, left out")
    out.mkdir(parents=True, exist_ok=True)
    held = json.loads(write_tools(out, all_tools).read_text())
    _carry_forward(out, summary, log)
    summary["tools"] = {dig: row["count"] for dig, row in sorted(held.items())}
    summary["seconds"] = round(time.time() - started, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def _stamped(tally: dict, summary: dict) -> dict:
    """The tally with the call that wrote its file: the summary's own pins are
    the last call's, and a folder converted set by set holds files of several."""
    for key in ("made_at", "git_commit", "audit"):
        tally[key] = summary[key]
    return tally


def _carry_forward(out: Path, summary: dict, log) -> None:
    """Into ``summary`` the tallies of the folder's own ``summary.json`` for
    the files this call did not write and that are still there, in the order
    they were first written; a conversations file no summary describes is
    logged."""
    path = out / "summary.json"
    sets = summary["sets"]
    if path.exists():
        prior = json.loads(path.read_text())
        merged = {}
        for key, tally in (prior.get("sets") or {}).items():
            if key in sets:
                merged[key] = sets[key]
            elif (out / (tally.get("file") or f"{key}.jsonl")).exists():
                for field in ("made_at", "git_commit", "audit"):   # a summary from before the stamps
                    tally.setdefault(field, prior.get(field))
                merged[key] = tally
        merged.update((k, t) for k, t in sets.items() if k not in merged)
        sets.clear()
        sets.update(merged)
    described = {t.get("file") for t in sets.values()}
    for file in sorted(out.glob("*.jsonl")):
        if file.name not in described:
            log(f"{file.name}: in {out}, in no summary.json")


# ------------------------------------------------------------ the card

def _bar(n: int, top: int, width: int = 28) -> str:
    return "█" * max(1 if n else 0, round(width * n / top)) if top else ""


def histogram(values: Sequence[int], edges: Sequence[int]) -> List[Tuple[str, int]]:
    """Counts of ``values`` in ``[edges[i], edges[i+1])``, labelled in thousands
    of tokens; the last bin is open."""
    rows = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        n = sum(1 for v in values if v >= lo and (hi is None or v < hi))
        label = f"{lo / 1000:g}k-{hi / 1000:g}k" if hi is not None else f"{lo / 1000:g}k+"
        rows.append((label, n))
    while rows and rows[-1][1] == 0:
        rows.pop()
    while rows and rows[0][1] == 0:
        rows.pop(0)
    return rows


#: the probe-task training sets, in the card's order
PROBE_ORDER = ("train-deeds", "train-qa", "train-striping", "train-profile")
EDGES = (0, 26000, 28000, 30000, 32000, 36000, 40000, 48000, 56000, 64000, 80000, 96000, 131072)


def _pct(values: Sequence[int], q: float) -> int:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else 0


def card(out: Path = OUT, path: Path = CARD) -> Path:
    """The dataset card from ``summary.json``, ``tools.json`` and, when
    ``scripts/training_tokens.py`` has run, ``tokens.json``."""
    out = Path(out)
    summary = json.loads((out / "summary.json").read_text())
    tools = json.loads((out / "tools.json").read_text())
    tokens_path = out / "tokens.json"
    tokens = json.loads(tokens_path.read_text()) if tokens_path.exists() else None
    counts = (tokens or {}).get("conversations") or {}
    sets = summary["sets"]
    probe_sets = sorted({t["taskset"] for t in sets.values() if t.get("harness") == "probe"},
                        key=lambda n: (PROBE_ORDER.index(n) if n in PROBE_ORDER else 99, n))
    names = sorted({t["taskset"] for t in sets.values()} - set(probe_sets),
                   key=lambda n: ["d1-train", "d1-train-hard", "d1-train-twist", "d1-train-crowd",
                                  "d1-train-revise"].index(n)
                   if n in ("d1-train", "d1-train-hard", "d1-train-twist", "d1-train-crowd",
                            "d1-train-revise") else 99)
    names += probe_sets   # the probe-task sets after the D1 sets
    L: List[str] = []
    w = L.append
    w("# RoadDraft training data: dataset card")
    w("")
    w("*Generated by `python -m roaddraft.trajectories.conversations card` from "
      "`results/training/` (gitignored). Do not edit by hand; regenerate.*")
    w("")
    w("## What it is")
    w("")
    w("Stage C0 of `RoadDraft_Training_Plan.md`: every grounded reference the recorder kept "
      "(`python -m roaddraft.trajectories.grounded`), turned into the conversation the eval "
      "harness would have had with a model on the same task (`roaddraft.trajectories.conversations`). "
      "One JSONL line per conversation: a header of pins and counts, then chat-completions "
      "messages (system; the task; per turn the assistant's text and tool calls, one `tool` "
      "message per result as compact JSON, and the harness's `[harness]` note when few steps are "
      "left; the closing `submit` call). The tool definitions are in `tools.json`, once per digest, "
      "in the function-tool shape the OpenAI-compatible provider sends.")
    w("")
    if any(t.get("variant") == "faults" for t in sets.values()):
        w("Beside each set's references, `<set>-<level>-faults.jsonl` holds their faulted copies: "
          "the same conversations with one or two of the subject model's own mistakes put in and "
          "recovered from (see *Injected faults* below).")
        w("")
    w("Every conversation was re-scored before it was written: its task rebuilt from the "
      "training manifest and held to the episode's prompt hash, truth and starting document; its "
      "tool list held to the episode's tool digest; its journal replayed through the verifier "
      "(100 or dropped); and the grounded audit run again (nothing ungrounded, lettering made for "
      "a twisted sheet, nothing left stale on a revised one).")
    w("")
    rolled = sorted({t["taskset"] for t in sets.values() if t.get("variant") == "rollouts"})
    if rolled:
        w(", ".join(f"`{n}`" for n in rolled) + " are a model's own rollouts (stage T2, "
          "`conversations rollouts`), not references: each submitted and re-scored 100 on its "
          "manifest's task and tools as above, and was held to the checks of the finished document "
          "(lettering made for a twisted sheet, nothing left stale on a revised one) where its "
          "tally's `audit` is `document`; the grounded audit of the turns is the scripted drafter's "
          "and was not run on them.")
        w("")
    if probe_sets:
        w(", ".join(f"`{n}`" for n in probe_sets) + " are probe tasks: they run on the pilots' harness "
          "(`roaddraft.eval.probe_tasks`), on the MCP server's own tools and that harness's system "
          "prompt, each graded by its task's own pass/fail check. Their conversations are laid out "
          "the same way. Such an episode has no command journal to replay, so each was played again "
          "before it was written: its recorded calls made through a new episode on the task rebuilt "
          "from the manifest, kept when every call answered as recorded, the check passed on the "
          "files the replay left, and the audit (`roaddraft.trajectories.reasoning.audit`) found "
          "nothing ungrounded.")
        w("")
    w("## Pins")
    w("")
    w("| pin | value |")
    w("|---|---|")
    commit = summary.get("git_commit") or "none"
    dirty = summary.get("git_dirty") or []
    w(f"| git commit at conversion | `{commit[:10]}`"
      + (f", with {len(dirty)} files under `src/` changed past it (uncommitted training work)" if dirty else "")
      + " |")
    w(f"| roaddraft | {summary.get('roaddraft')} |")
    heads = _first_headers(out, sets)
    for key, label in (("spec_version", "drafting spec"), ("spec_hash", "spec hash"),
                       ("generator_version", "generator"), ("verifier_version", "verifier"),
                       ("harness_version", "harness")):
        vals = sorted({h.get(key) for h in heads if h.get(key)})
        w(f"| {label} | {', '.join(f'`{v}`' for v in vals) or 'n/a'} |")
    systems = sorted({h.get("system_sha256") for h in heads
                      if h.get("system_sha256") and h.get("harness") != "probe"})
    if systems:
        w(f"| system prompt | {', '.join(f'`{s[:19]}`' for s in systems)} (`system_neutral.md`, single "
          "mode, 150 steps, 8 faults) |")
    systems = sorted({h.get("system_sha256") for h in heads
                      if h.get("system_sha256") and h.get("harness") == "probe"})
    if systems:
        w(f"| system prompt, probe tasks | {', '.join(f'`{s[:19]}`' for s in systems)} (the MCP "
          "server's instructions, then how the task runs: `probe_tasks.system_prompt`, under each "
          "episode's mode and budgets) |")
    probe_tools = {dig for t in sets.values() if t.get("harness") == "probe" for dig in t["tools"]}
    seeded = [set(r["names"]) for dig, r in tools.items() if dig not in probe_tools]
    for dig, row in tools.items():
        if dig in probe_tools:
            w(f"| tools `{dig[:19]}` | {row['count']} definitions (probe tasks: the MCP server's "
              "tools and the harness's) |")
            continue
        extra = sorted(set(row["names"]) - set.intersection(*seeded))
        w(f"| tools `{dig[:19]}` | {row['count']} definitions"
          + (f" (adds {', '.join(f'`{e}`' for e in extra)})" if extra else "") + " |")
    w(f"| converted | {summary.get('made_at')}, {summary.get('seconds')} s |")
    w("")
    w("Each conversation's header carries its own: `tools_sha256`, `prompt_hash` (the task text at "
      "its level, as the eval header has it), `system_sha256`, the spec, generator, verifier and "
      "harness versions, `git_commit` (conversion) and `recorded_commit` (the recording's; the "
      "grounded recorder writes none).")
    w("")
    w("## Sources and counts")
    w("")
    w("| set | seeds (manifest) | level | tasks | covered | kept by the recorder | converted | dropped |")
    w("|---|---|---|---:|---:|---:|---:|---|")
    total = Counter()
    for name in names:
        for level in LEVELS:
            t = sets.get(f"{name}-{level}")
            if not t:
                continue
            rec = t.get("recorder") or {}
            seeds = t.get("manifest_seeds")
            seeds = f"{seeds[0]}-{seeds[1]}" if seeds else ""
            drops = ", ".join(f"{r} {n}" for r, n in t["dropped"].items()) or "0"
            covered = rec.get("covered", "")
            w(f"| `{name}` | {seeds} | {level} | {rec.get('tasks', '')} | "
              f"{'' if covered is None else covered} | {rec.get('kept', t['episodes'])} | {t['kept']} | {drops} |")
            total[level] += t["kept"]
            total["tasks_" + level] += rec.get("tasks", 0)
    w(f"| all | | vague | {total['tasks_vague']} | | | {total['vague']} | |")
    w(f"| all | | explicit | {total['tasks_explicit']} | | | {total['explicit']} | |")
    w("")
    w("Tasks not covered wait on drafter phases not built yet (the width dimensions: `pavement`, "
      "`pavement-widths`, `plan-sheet-pavement`); covered and not kept are where the drafter "
      "stopped rather than guess. Both are the recorder's (`results/grounded-v2/<set>-<level>/index.json`).")
    w("")
    same = all(sets.get(f"{n}-vague", {}).get("by_type") == sets.get(f"{n}-explicit", {}).get("by_type")
               for n in names)
    shown_levels = ("vague",) if same else LEVELS
    w("**Kept by task type**" + (" (the same at both levels):" if same else ", by level:"))
    w("")
    types = sorted({ty for t in sets.values() for ty in t["by_type"]})
    cols = [(n, lv) for n in names for lv in shown_levels]
    w("| type | " + " | ".join(f"`{n}`" + ("" if same else f" {lv}") for n, lv in cols) + " |")
    w("|---|" + "---:|" * len(cols))
    for ty in types:
        cells = [str(sets.get(f"{n}-{lv}", {}).get("by_type", {}).get(ty, "")) for n, lv in cols]
        w(f"| `{ty}` | " + " | ".join(cells) + " |")
    w("")
    w("**Turns and calls** (median, and the most in brackets):")
    w("")
    w("| set | level | turns | calls | with a `[harness]` note |")
    w("|---|---|---|---|---:|")
    for name in names:
        for level in LEVELS:
            t = sets.get(f"{name}-{level}")
            if t and t["turns"]:
                w(f"| `{name}` | {level} | {t['turns']['median']:g} ({t['turns']['max']}) | "
                  f"{t['calls']['median']:g} ({t['calls']['max']}) | {t['with_notes']} |")
    w("")
    faulted = {k: t for k, t in sets.items() if t.get("variant") == "faults"}
    if faulted:
        _faults_section(w, names, sets, faulted)
    w("## Token lengths")
    w("")
    if not tokens:
        w("Not counted yet: run `scripts/training_tokens.py` (it needs the `tokenizers`, `gguf` and "
          "`jinja2` packages, which the repo's venv does not carry), then `card` again.")
    else:
        tk = tokens.get("tokenizer") or {}
        tp = tokens.get("template") or {}
        w(f"Counted with {tk.get('description', 'the tokenizer')} "
          f"(`{tk.get('source', '')}`, {tk.get('vocab', '?')} tokens, sha256 `{str(tk.get('sha256', ''))[:16]}`), "
          f"over each conversation rendered through {tp.get('description', 'the chat template')} "
          f"(`{tp.get('source', '')}`, sha256 `{str(tp.get('sha256', ''))[:16]}`) with its tools, "
          "no generation prompt: the length of the training sequence.")
        cal = tokens.get("calibration")
        if cal:
            w("")
            w(f"**Calibration.** {cal.get('text', '')}")
        w("")
        all_totals = []
        for name in names:
            ids = []
            for level in LEVELS:
                t = sets.get(f"{name}-{level}")
                if t:
                    ids += [i for i in _ids(out, t["file"])]
            totals = [counts[i][0] for i in ids if i in counts]
            prompts = [counts[i][1] for i in ids if i in counts]
            losses = [counts[i][2] for i in ids if i in counts]
            if not totals:
                continue
            all_totals += totals
            w(f"### `{name}` ({len(totals)} conversations, both levels)")
            w("")
            w(f"Fixed prompt (system, tools, task) {min(prompts):,}-{max(prompts):,} tokens; whole "
              f"conversation median {statistics.median(totals):,.0f}, p90 {_pct(totals, 0.9):,}, most "
              f"{max(totals):,}; assistant tokens (the loss) median {statistics.median(losses):,.0f}, "
              f"most {max(losses):,}.")
            w("")
            w("```")
            rows = histogram(totals, EDGES)
            top = max(n for _, n in rows) if rows else 0
            for label, n in rows:
                w(f"{label:>12} {n:6d} {_bar(n, top)}")
            w("```")
            w("")
        if all_totals:
            w(f"**All sets:** {len(all_totals):,} conversations, {sum(all_totals):,} tokens; median "
              f"{statistics.median(all_totals):,.0f}, p90 {_pct(all_totals, 0.9):,}, p99 "
              f"{_pct(all_totals, 0.99):,}, most {max(all_totals):,}. "
              f"{sum(1 for v in all_totals if v > 65536)} are past 65,536 and "
              f"{sum(1 for v in all_totals if v > 131072)} past 131,072.")
            w("")
        ids = [i for t in sets.values() if t.get("variant") == "faults" for i in _ids(out, t["file"])]
        rows = [counts[i] for i in ids if i in counts]
        if rows:
            totals = [r[0] for r in rows]
            w(f"**Faulted copies:** {len(totals):,} conversations, {sum(totals):,} tokens; median "
              f"{statistics.median(totals):,.0f}, most {max(totals):,}; "
              f"{sum(1 for v in totals if v > 65536)} past 65,536 and "
              f"{sum(1 for v in totals if v > 131072)} past 131,072. Assistant tokens trained on "
              f"(the broken turns, weight 0, left out) median {statistics.median(r[2] for r in rows):,.0f}.")
            w("")
    w("## How to rebuild")
    w("")
    w("```bash")
    w('PYTHONPATH="$PWD/src" .venv/bin/python -m roaddraft.trajectories.conversations convert --jobs 6')
    w("PYTHON_WITH_TOKENIZERS -I scripts/training_tokens.py results/training")
    w('PYTHONPATH="$PWD/src" .venv/bin/python -m roaddraft.trajectories.conversations card')
    w("```")
    w("")
    w("## Open for T1")
    w("")
    w("- *Thinking.* The references carry their reasoning as one line of shown work in the "
      "assistant's text. Qwen3.5's template renders every assistant turn after the last user "
      "message with an empty `<think></think>` block, so trained as is the model learns to think "
      "in the visible text, not in the think block. The T1 smoke decides whether to keep that or "
      "move the shown work into `reasoning_content`.")
    w("- *Turns hold several calls.* The drafter often asks two or three queries in one turn; "
      "the conversation keeps them in one assistant message, as the harness ran them.")
    w("- *The `[harness]` note* is a user message, so Qwen3.5's template treats it as the last "
      "query: the assistant turns before it render without the think block.")
    w("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    return path


def _faults_section(w, names: Sequence[str], sets: dict, faulted: dict) -> None:
    from roaddraft.trajectories.faults import KINDS
    w("## Injected faults")
    w("")
    w("A faulted copy of each reference (`python -m roaddraft.trajectories.faults inject`; training "
      "plan §3, *Data*): at one or two places a call broken the way the 9B breaks it on its board rows, "
      "the engine's own error for it, then the reference's call with a line of shown work that reads "
      "the error. The broken turn's assistant message carries `\"weight\": 0`: it is context for the "
      "recovery and never a training target. Each copy was played through the episode loop and "
      "checked as it ran: every broken call failed, every other result and the final journal equal "
      "the reference's, it scores 100, and nothing outside the broken turns is ungrounded. The "
      "conversation's id ends `.faults` and its header lists the faults (`injected`).")
    w("")
    w("| set | level | references | faulted copies | faults | dropped |")
    w("|---|---|---:|---:|---:|---|")
    total = Counter()
    for name in names:
        for level in LEVELS:
            t = faulted.get(f"{name}-{level}-faults")
            if not t:
                continue
            rec = t.get("recorder") or {}
            n = sum((t.get("injected") or {}).values())
            drops = ", ".join(f"{r} {k}" for r, k in t["dropped"].items()) or "0"
            w(f"| `{name}` | {level} | {rec.get('tasks', '')} | {t['kept']} | {n} | {drops} |")
            total["copies"] += t["kept"]
            total["faults"] += n
            for kind, k in (t.get("injected") or {}).items():
                total[kind] += k
    w(f"| all | | | {total['copies']} | {total['faults']} | |")
    w("")
    w("| mistake | what goes wrong | how it goes in | the 9B's failed calls of the kind | in the data |")
    w("|---|---|---|---:|---:|")
    for kind in KINDS:
        w(f"| `{kind.name}` | {kind.what} | {kind.layout} | {sum(kind.tools.values())} | "
          f"{total[kind.name]} |")
    w("")
    w("The 9B's counts are its failed calls of each kind over its six board rows (`d1-test` and "
      "`d1-real` at both levels, `d1-test-hard` and `d1-real-hard` vague); only the shape of each "
      "mistake is taken from them, and each broken call is made from the training reference's own. "
      "A reference with no place for any of them (a title block, a reference attached, layers set "
      "up and nothing after) has no faulted copy.")
    w("")


def _ids(out: Path, file: str) -> List[str]:
    p = out / file
    if not p.exists():
        return []
    ids = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            # the id is the second key; read it without parsing the whole line
            start = line.find('"id":"')
            if start >= 0:
                ids.append(line[start + 6:line.index('"', start + 6)])
    return ids


def _first_headers(out: Path, sets: dict) -> List[dict]:
    heads = []
    for t in sets.values():
        p = out / t["file"]
        if p.exists():
            with p.open(encoding="utf-8") as fh:
                line = fh.readline()
            if line.strip():
                heads.append(json.loads(line)["header"])
    return heads


# ------------------------------------------------------------ CLI

def main(argv=None) -> int:
    from roaddraft.eval import taskset as tasksets
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories.conversations",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("convert", help="episode files -> conversations JSONL, tools.json, summary.json")
    every = tuple(tasksets.TRAIN_NAMES) + tuple(tasksets.PROBE_TRAIN_NAMES)
    c.add_argument("--set", action="append", dest="sets", choices=every,
                   help="a training set (default: every D1 training set and the probe-task "
                        "sets, train-deeds and train-qa)")
    c.add_argument("--level", action="append", dest="levels", choices=LEVELS)
    c.add_argument("--source", type=Path, default=SOURCE, help="the recordings, <set>-<level>/ each")
    c.add_argument("--out", type=Path, default=OUT)
    c.add_argument("--jobs", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 2)))
    c.add_argument("--limit", type=int, help="convert the first N episodes of each folder")
    c.add_argument("--no-audit", dest="audit", action="store_false",
                   help="skip the grounded audit (score and pins are still checked)")
    c.add_argument("--faults", type=Path, default=argparse.SUPPRESS,
                   help="the faulted copies, <set>-<level>/ each (trajectories.faults); default: "
                        "results/faults-v2 for the default --source, none for any other")
    c.add_argument("--no-faults", dest="faults", action="store_const", const=None,
                   default=argparse.SUPPRESS,
                   help="convert the references only")
    r = sub.add_parser("rollouts", help="a model's run on a T2 round's manifest -> conversations "
                                        "(kept: submitted and re-scored 100)")
    r.add_argument("run_dir", type=Path, help="the run folder, results/<run_id>")
    r.add_argument("--taskset", required=True, help="the round's manifest (python -m roaddraft.eval t2 plan)")
    r.add_argument("--tasksets-root", type=Path, help="where that manifest is (default benchmarks/tasksets)")
    r.add_argument("--out", type=Path, default=OUT)
    r.add_argument("--jobs", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 2)))
    r.add_argument("--limit", type=int, help="convert the first N episodes of each level")
    r.add_argument("--audit", choices=(DOCUMENT, "none"), default=DOCUMENT,
                   help="document (default): also drop lettering not made for a twisted sheet and "
                        "anything left stale on a revised one; none: submitted and 100 alone")
    k = sub.add_parser("card", help="write the dataset card from results/training")
    k.add_argument("--out", type=Path, default=OUT)
    k.add_argument("--card", type=Path, default=CARD)
    args = parser.parse_args(argv)
    if args.command == "convert":
        summary = run(args.sets or list(every), args.levels or list(LEVELS),
                      args.source, args.out, jobs=args.jobs, audit=args.audit, limit=args.limit,
                      faults=getattr(args, "faults", PAIRED))
        kept = sum(t["kept"] for t in summary["sets"].values())
        dropped = sum(sum(t["dropped"].values()) for t in summary["sets"].values())
        print(f"{kept} conversations written to {args.out}, {dropped} dropped, "
              f"{len(summary['tools'])} tool set(s), {summary['seconds']} s")
        return 0
    if args.command == "rollouts":
        try:
            summary = run_rollouts(args.run_dir, args.taskset, args.out, args.tasksets_root,
                                   jobs=args.jobs, audit=False if args.audit == "none" else DOCUMENT,
                                   limit=args.limit)
        except (ValueError, FileNotFoundError) as why:
            print(f"rollouts: {why}", file=sys.stderr)
            return 2
        mine = [t for t in summary["sets"].values() if t.get("run_id") == Path(args.run_dir).name
                and t.get("taskset") == args.taskset]
        for t in mine:
            drops = ", ".join(f"{reason} {n}" for reason, n in t["dropped"].items()) or "none"
            print(f"{t['file']}: {t['kept']} kept of {t['episodes']} episodes; dropped: {drops}"
                  + (f"; {t['more_samples']} later samples of a kept task not written"
                     if t.get("more_samples") else ""))
        print(f"{sum(t['kept'] for t in mine)} conversations written to {args.out}")
        return 0
    path = card(args.out, args.card)
    print(f"wrote {path}")
    return 0


__all__ = ["FORMAT", "REASONS", "Drop", "Example", "digest", "tools_sha256", "tool_set",
           "function_tools", "system_text", "system_extra_of", "held_to_prompt", "rebuild_task",
           "budgets_of", "messages", "convert_episode", "convert",
           "convert_set", "sources", "run", "write_tools", "card", "histogram", "main",
           "DOCUMENT", "run_rollouts"]

if __name__ == "__main__":
    sys.exit(main())

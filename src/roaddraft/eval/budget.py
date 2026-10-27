"""Episode budgets (eval plan section 4.1): steps, ``run_check`` uses,
consecutive faults, output tokens, wall clock and, for an LLM agent, the
context.  Every one is recorded with the episode; tripping one ends the
episode with ``termination = "budget"`` and the budget's name, which is an
outcome, not an error.  The per-run cost cap belongs to the runner, not the
episode.

``context_tokens`` is the prompt size an episode may send, normally the
context window the row is served at.  A server that refuses an oversize
request (vLLM) ends the episode as ``context`` by itself; one that
truncates the prompt and answers (LM Studio: eight of the 9B's first 38
d1-real episodes ran on cut transcripts at 65,536, up to 159,505 tokens)
never would, so the LLM agent holds the budget itself (``agents/llm.py``):
the reply's own prompt count past it, or a next request that cannot fit,
ends the episode the same way and runs none of that turn's calls.  None
leaves only the server's limit.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace
from typing import Dict, Optional


@dataclass(frozen=True)
class Budgets:
    steps: int = 150               # tool calls, harness tools included
    run_checks: int = 3            # 0 in single mode
    faults: int = 8                # consecutive failed calls
    output_tokens: int = 60000     # per episode, LLM agents only
    wall_clock_s: float = 1200.0   # 20 minutes
    context_tokens: Optional[int] = None  # prompt tokens a request may hold; None: the server's limit

    def for_mode(self, mode: str) -> "Budgets":
        return replace(self, run_checks=0) if mode == "single" else self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BudgetState:
    """What an episode has used so far."""
    steps: int = 0
    run_check_uses: int = 0
    consecutive_faults: int = 0
    faults: int = 0
    output_tokens: int = 0
    started: float = field(default_factory=time.monotonic)

    def note_call(self, ok: bool) -> None:
        self.steps += 1
        if ok:
            self.consecutive_faults = 0
        else:
            self.faults += 1
            self.consecutive_faults += 1

    def note_check(self) -> None:
        self.run_check_uses += 1

    def note_usage(self, usage: Optional[Dict[str, int]]) -> None:
        if usage:
            self.output_tokens += int(usage.get("output_tokens", 0) or 0)

    def elapsed_s(self, now: Optional[float] = None) -> float:
        return (time.monotonic() if now is None else now) - self.started

    def tripped(self, budgets: Budgets, now: Optional[float] = None) -> Optional[str]:
        """The name of the budget that has run out, or None."""
        if self.steps >= budgets.steps:
            return "steps"
        if self.consecutive_faults >= budgets.faults:
            return "faults"
        if budgets.output_tokens and self.output_tokens >= budgets.output_tokens:
            return "output_tokens"
        if budgets.wall_clock_s and self.elapsed_s(now) >= budgets.wall_clock_s:
            return "wall_clock"
        return None

    def remaining(self, budgets: Budgets) -> dict:
        return {"steps": max(0, budgets.steps - self.steps),
                "run_checks": max(0, budgets.run_checks - self.run_check_uses),
                "faults_before_stop": max(0, budgets.faults - self.consecutive_faults),
                "seconds": max(0.0, round(budgets.wall_clock_s - self.elapsed_s(), 1))}

    def to_dict(self) -> dict:
        return {"steps": self.steps, "run_check_uses": self.run_check_uses,
                "faults": self.faults, "output_tokens": self.output_tokens,
                "elapsed_ms": int(round(self.elapsed_s() * 1000))}


__all__ = ["Budgets", "BudgetState"]

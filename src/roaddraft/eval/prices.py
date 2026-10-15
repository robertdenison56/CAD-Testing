"""The price table (eval plan section 4.4): usage is recorded per turn, and
dollars come from ``prices.json``, dated to when it was checked, never from a
number in the code.  The episode writes its estimate into the ``end`` record
(``cost_usd``, ``prices_checked``) for the runner's cost cap; a report can
recompute it from the turns with a newer table.

Cost is per request: a tiered price (Haiku 5.5 past 100k prompt tokens)
depends on the size of one prompt, so an episode's cost is the sum over its
turns, ``episode_cost``, not the cost of its total usage.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Dict, Iterable, Optional

PRICES_PATH = Path(__file__).with_name("prices.json")


@functools.lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load(path=None) -> dict:
    """The table: ``checked``, ``source``, default cache multipliers, ``models``."""
    return _load(str(path or PRICES_PATH))


def rates(model: str, table: Optional[dict] = None, prompt_tokens: int = 0) -> Optional[Dict[str, float]]:
    """Dollars per million tokens for ``model`` -- input, output, cache_read,
    cache_write -- at the tier a prompt of ``prompt_tokens`` falls in; None
    for a model the table does not price."""
    table = table or load()
    row = (table.get("models") or {}).get(model)
    if row is None:
        return None
    base_in, out = float(row["input"]), float(row["output"])
    read = row.get("cache_read")
    write = row.get("cache_write")
    scale = 1.0
    for tier in row.get("tiers") or []:
        if prompt_tokens > tier["above_prompt_tokens"]:
            scale = float(tier["input"]) / base_in
            out = float(tier["output"])
    inp = base_in * scale
    return {"input": inp, "output": out,
            "cache_read": float(read) * scale if read is not None else inp * table.get("cache_read", 0.1),
            "cache_write": float(write) * scale if write is not None else inp * table.get("cache_write", 1.25)}


def cost_usd(model: str, usage: Optional[Dict[str, int]], table: Optional[dict] = None) -> Optional[float]:
    """The dollars one request's ``usage`` cost, or None for an unpriced model."""
    usage = usage or {}
    inp = int(usage.get("input_tokens", 0) or 0)
    read = int(usage.get("cache_read_input_tokens", 0) or 0)
    write = int(usage.get("cache_creation_input_tokens", 0) or 0)
    r = rates(model, table, prompt_tokens=inp + read + write)
    if r is None:
        return None
    dollars = (inp * r["input"] + read * r["cache_read"] + write * r["cache_write"]
               + int(usage.get("output_tokens", 0) or 0) * r["output"]) / 1_000_000
    return round(dollars, 6)


def episode_cost(model: str, turn_usages: Iterable[Optional[Dict[str, int]]],
                 table: Optional[dict] = None) -> Optional[float]:
    """The sum of ``cost_usd`` over an episode's turns; None if unpriced."""
    if rates(model, table) is None:
        return None
    return round(sum(cost_usd(model, u, table) or 0.0 for u in turn_usages), 6)


__all__ = ["PRICES_PATH", "load", "rates", "cost_usd", "episode_cost"]

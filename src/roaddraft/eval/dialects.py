"""Dialects (eval plan section 4.5): tool-name skins over the same surface.

``neutral`` shows the canonical names.  ``c3d`` and ``ord`` show the names a
Civil 3D or an OpenRoads Designer user knows, taken from the aliases every
command spec carries (``commands.bus``): ``LAYER``, ``TEXT``, ``MLEADER``;
``level_create``, ``place_text``, ``place_note``.  The harness presents the
skin's names and resolves each call back to the canonical command, so the
journal, the verifier and the score never see a skin.

A skin name is the first of a command's aliases in that program's list that
is a valid tool name for every vendor (letters, digits, ``_`` and ``-``, at
most 64; an ORD phrase has its spaces written as ``_``) and not already
taken -- by an earlier tool in name order, or by another tool's canonical
name.  A command with no usable alias, a query (queries carry none) and the
harness's own tools keep their canonical names.  ``text`` rewrites the
canonical names of the renamed tools in what the harness says -- the system
prompt, the task text, the tool descriptions -- so the words match the
tools; a one-word name (``trim``, ``undo``) is left alone in prose, where it
is usually the English word.  Tool results are the engine's and stay
verbatim.

The transfer runs themselves, and anything a skin needs beyond the names
(each program's vocabulary in the prompts), are E5.
"""
from __future__ import annotations

import functools
import re
from typing import Dict, Iterable, List

DIALECTS = ("neutral", "c3d", "ord")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _tool_name(alias: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", alias.strip().replace(" ", "_"))


@functools.lru_cache(maxsize=1)
def _command_aliases() -> Dict[str, Dict[str, List[str]]]:
    from roaddraft.commands.bus import CommandBus
    return {c["name"]: c.get("aliases") or {} for c in CommandBus.manifest()}


class Dialect:
    """One skin over one episode's tools: canonical name <-> shown name."""

    def __init__(self, name: str, shown: Dict[str, str]):
        self.name = name
        self.shown = dict(shown)                        # canonical -> shown (renamed ones only)
        self.canonical_of = {v: k for k, v in self.shown.items()}
        # one-word names (trim, extend, undo) are also English words: prose keeps them
        names = sorted((n for n in self.shown if "_" in n), key=len, reverse=True)
        self._pattern = (re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, names))
                                    + r")(?![A-Za-z0-9_])") if names else None)

    @classmethod
    def build(cls, name: str, tools: Iterable[str]) -> "Dialect":
        """The skin ``name`` over the canonical tool names ``tools``."""
        if name not in DIALECTS:
            raise ValueError(f"unknown dialect {name!r}; dialects: {', '.join(DIALECTS)}")
        tools = sorted(set(tools))
        if name == "neutral":
            return cls(name, {})
        aliases = _command_aliases()
        taken = set(tools)
        shown: Dict[str, str] = {}
        for tool in tools:
            for alias in (aliases.get(tool) or {}).get(name, []):
                candidate = _tool_name(alias) if name == "ord" else alias.strip()
                if NAME_RE.match(candidate) and candidate not in taken:
                    shown[tool] = candidate
                    taken.add(candidate)
                    break
        return cls(name, shown)

    def present(self, canonical: str) -> str:
        return self.shown.get(canonical, canonical)

    def canonical(self, name: str) -> str:
        """The canonical name of a shown name; anything else as it is (so a
        canonical name still works under a skin)."""
        return self.canonical_of.get(name, name)

    def text(self, text: str) -> str:
        if not self._pattern or not text:
            return text
        return self._pattern.sub(lambda m: self.shown[m.group(1)], text)

    def tools(self, definitions: List[dict]) -> List[dict]:
        """The tool definitions as this skin shows them, sorted by the shown
        name; a renamed tool keeps its canonical name under ``canonical``.
        ``neutral`` returns them unchanged."""
        if not self.shown:
            return [dict(d) for d in definitions]
        out = []
        for d in definitions:
            shown = dict(d)
            if d["name"] in self.shown:
                shown["canonical"] = d["name"]
                shown["name"] = self.shown[d["name"]]
            shown["description"] = self.text(d.get("description", ""))
            out.append(shown)
        return sorted(out, key=lambda d: d["name"])


def get(name: str, tools: Iterable[str]) -> Dialect:
    return Dialect.build(name, tools)


__all__ = ["DIALECTS", "NAME_RE", "Dialect", "get"]

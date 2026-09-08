"""The design model stored on a document: alignments and profiles by name."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment
from roaddraft.design.vertical import Profile


@dataclass
class DesignModel:
    """Container for every alignment and profile of a document."""

    alignments: Dict[str, Alignment] = field(default_factory=dict)
    profiles: Dict[str, Profile] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"alignments": {name: a.to_dict() for name, a in self.alignments.items()},
                "profiles": {name: p.to_dict() for name, p in self.profiles.items()}}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DesignModel":
        """Build from a stored dict; ``d`` may be ``None``, ``{}`` or lack keys."""
        d = d or {}
        if not isinstance(d, dict):
            raise DesignError("design must be an object with alignments and profiles")
        model = cls()
        for name, a in (d.get("alignments") or {}).items():
            if isinstance(a, dict) and "name" not in a:
                a = dict(a, name=name)
            model.alignments[name] = Alignment.from_dict(a)
        for name, p in (d.get("profiles") or {}).items():
            if isinstance(p, dict) and "name" not in p:
                p = dict(p, name=name)
            model.profiles[name] = Profile.from_dict(p)
        return model

    def profiles_of(self, alignment_name: str) -> List[Profile]:
        """Profiles bound to ``alignment_name`` (dictionary order)."""
        return [p for p in self.profiles.values() if p.alignment == alignment_name]

    def fingerprint(self) -> str:
        """``"sha256:" + sha256`` of the canonical JSON of ``to_dict()``."""
        text = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["DesignModel"]

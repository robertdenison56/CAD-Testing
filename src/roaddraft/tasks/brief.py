"""Task briefs, ground truth, and task ids (spec section 7.3).

A ``TaskBrief`` is everything the agent sees: the project, the pre-seeded
design, the deliverable, the drafting spec subset, and plain instructions.
A ``GroundTruth`` is verifier-only: every label/tick/element the reference
solution produces, computed by the same design functions.  A ``Task`` bundles
both with the baseline document (design pre-seeded, nothing drawn).

Task ids are ``{level}-{seed:06d}-{sha256[:12]}`` where the hash covers the
generator version, the spec hash, the project, the design and the
deliverable (not the instructions, not the truth), so a corrected spec or
generator mints new ids instead of silently re-scoring old ones.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List

GENERATOR_VERSION = "d1-v1"


def round_floats(obj, ndigits: int = 6):
    """Recursively round floats (for canonical hashing)."""
    if isinstance(obj, float):
        r = round(obj, ndigits)
        return 0.0 if r == 0 else r  # fold -0.0
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, ndigits) for v in obj]
    return obj


def canonical_json(obj) -> str:
    """Deterministic JSON: floats rounded to 6 places, sorted keys, no spaces."""
    return json.dumps(round_floats(obj, 6), sort_keys=True, separators=(",", ":"))


def compute_task_id(seed: int, level: str, payload: dict) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{level}-{int(seed):06d}-{digest[:12]}"


@dataclass
class TaskBrief:
    """Agent-visible task description."""

    task_id: str
    seed: int
    level: str
    generator_version: str
    spec_version: str
    spec_hash: str
    project: dict
    design: dict
    deliverable: dict
    drafting_spec: dict
    instructions: str

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "seed": self.seed, "level": self.level,
                "generator_version": self.generator_version, "spec_version": self.spec_version,
                "spec_hash": self.spec_hash, "project": self.project, "design": self.design,
                "deliverable": self.deliverable, "drafting_spec": self.drafting_spec,
                "instructions": self.instructions}

    @classmethod
    def from_dict(cls, d: dict) -> "TaskBrief":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @property
    def alignment_name(self) -> str:
        return next(iter(self.design["alignments"]))


@dataclass
class GroundTruth:
    """Verifier-only expected output for a task."""

    task_id: str
    design_fingerprint: str
    labels: List[dict] = field(default_factory=list)
    ticks: List[dict] = field(default_factory=list)
    elements: List[dict] = field(default_factory=list)
    curve_table: dict = field(default_factory=dict)
    sheet: dict = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GroundTruth":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class Task:
    brief: TaskBrief
    truth: GroundTruth
    baseline: dict  # Document JSON with the design pre-seeded

    @property
    def task_id(self) -> str:
        return self.brief.task_id


__all__ = ["GENERATOR_VERSION", "round_floats", "canonical_json", "compute_task_id",
           "TaskBrief", "GroundTruth", "Task"]

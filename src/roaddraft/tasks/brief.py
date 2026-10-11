"""Task briefs, ground truth, and task ids (spec section 7.3).

A ``TaskBrief`` is everything the agent sees: the project, the pre-seeded
design, the deliverable, the drafting spec subset, and plain instructions.
A ``GroundTruth`` is verifier-only: every label/tick/element the reference
solution produces, computed by the same design functions.  A ``Task`` bundles
both with the baseline document (design pre-seeded, nothing drawn).

Task ids are ``{level}-{seed:06d}-{sha256[:12]}`` where the hash covers the
generator version, the spec hash, the project, the design and the
deliverable -- which names the task type and the sheets -- (not the
instructions, not the truth), so a corrected spec or generator mints new ids
instead of silently re-scoring old ones.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List

# d1-v2 (2026-10-10): tangent floor 120 ft, C-n callouts at 2x the label offset, so
# every reference sheet is legible (verifier D1-08 = 1); d1-v3 (2026-10-10): task types
# (a starting document with some phases done) and two-sheet layouts with match lines
GENERATOR_VERSION = "d1-v3"


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
    instructions: str  # the explicit-level prompt
    #: the natural-language prompt at each of the spec's prompt levels (tasks.prompts)
    prompts: Dict[str, str] = field(default_factory=dict)
    task_type: str = "plan-sheet"  # what the drafter starts with and is asked for (tasks.types)
    sheets: int = 1                # plan sheets the alignment is laid out on

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "seed": self.seed, "level": self.level,
                "task_type": self.task_type, "sheets": self.sheets,
                "generator_version": self.generator_version, "spec_version": self.spec_version,
                "spec_hash": self.spec_hash, "project": self.project, "design": self.design,
                "deliverable": self.deliverable, "drafting_spec": self.drafting_spec,
                "instructions": self.instructions, "prompts": dict(self.prompts)}

    @classmethod
    def from_dict(cls, d: dict) -> "TaskBrief":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @property
    def alignment_name(self) -> str:
        return next(iter(self.design["alignments"]))


@dataclass
class GroundTruth:
    """Verifier-only expected output for a task.

    ``scope`` lists the truth groups the task asks for (``tasks.types``);
    the verifier grades those and ignores the rest.  ``sheets`` describes
    every deliverable sheet (its viewport, station range, title block and
    match line) and ``curve_tables`` the table each one carries."""

    task_id: str
    design_fingerprint: str
    labels: List[dict] = field(default_factory=list)
    ticks: List[dict] = field(default_factory=list)
    elements: List[dict] = field(default_factory=list)
    curve_tables: List[dict] = field(default_factory=list)
    sheets: List[dict] = field(default_factory=list)
    edges: List[dict] = field(default_factory=list)       # offset pieces of the pavement edges
    dimensions: List[dict] = field(default_factory=list)  # width dimensions, one per tangent
    references: List[dict] = field(default_factory=list)  # base drawings to attach
    layers: List[str] = field(default_factory=list)       # the standard layer set
    scope: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def sheet(self) -> dict:
        """The first deliverable sheet."""
        return self.sheets[0] if self.sheets else {}

    @property
    def curve_table(self) -> dict:
        """The first sheet's curve table."""
        return self.curve_tables[0] if self.curve_tables else {}

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
    baseline: dict  # Document JSON: the starting document (design pre-seeded, given phases drawn)
    #: other files the task ships, by file name: a base drawing to attach, as Document JSON
    files: Dict[str, dict] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.brief.task_id


__all__ = ["GENERATOR_VERSION", "round_floats", "canonical_json", "compute_task_id",
           "TaskBrief", "GroundTruth", "Task"]

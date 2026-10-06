"""Fixtures shared across the test modules.

Sheet L-2 takes about 20 s to build, so the tests that start from it build it
once and keep it in the pytest cache, keyed by a hash of the code that builds it.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import roaddraft
from roaddraft.probes import fixture

SRC = Path(roaddraft.__file__).resolve().parent

#: package code the L-2 build cannot reach: editing it need not rebuild L-2
NOT_IN_THE_BUILD = ("tasks", "web", "mcp", "cli", "render")


def _in_the_build(path: Path) -> bool:
    rel = path.relative_to(SRC).parts
    if rel[0] in NOT_IN_THE_BUILD:
        return False
    if rel[0] == "probes":
        return rel[1:2] == ("l2",) or rel[1:] == ("fixture.py",)
    return True


@pytest.fixture(scope="session")
def l2_build(request):
    """A built L-2 start, cached across runs until the code that builds it
    changes: the engine, the L-2 builders and the probe fixture."""
    digest = hashlib.sha256()
    for path in sorted(SRC.rglob("*")):
        if (path.suffix in (".py", ".json") and "__pycache__" not in path.parts
                and _in_the_build(path)):
            digest.update(str(path.relative_to(SRC)).encode())
            digest.update(path.read_bytes())
    cache = Path(str(request.config.cache.mkdir("roaddraft-l2"))) / digest.hexdigest()[:16]
    if not (cache / fixture.L2_SHEET_FILE).exists():
        if cache.exists():
            shutil.rmtree(cache)
        fixture.start_document(cache, "l2")
    return cache

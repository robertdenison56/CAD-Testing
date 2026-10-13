"""Build the catalogue of D1 tasks on the redrafted example plan sheets.

    PYTHONPATH=src .venv/bin/python scripts/real_tasks.py [--out benchmarks/real_tasks/catalog.json]

Every (sheet, alignment, task type) pairing ``roaddraft.tasks.real.candidates``
finds is built and validated (reference solution 100, starting document 0, at
both prompt levels); the catalogue lists the tasks that pass, with their ids,
and every pairing left out with the reason.  Rebuild it whenever the redrafts,
the spec, the generator or the verifier change.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

from roaddraft.tasks.real import catalog


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="benchmarks/real_tasks/catalog.json")
    ap.add_argument("--quiet", action="store_true")
    ns = ap.parse_args(argv)
    t0 = time.time()

    def progress(row):
        if not ns.quiet:
            mark = "ok " if "task_id" in row and "why" not in row else "-- "
            print(mark, row["sheet_id"], row["alignment"], row["type"], row.get("why", ""),
                  flush=True)

    cat = catalog(progress)
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    tasks = cat["tasks"]
    by_agency = collections.Counter(t["agency"] for t in tasks)
    by_type = collections.Counter(t["type"] for t in tasks)
    print(f"{len(tasks)} tasks ({len(cat['excluded'])} pairings left out) on "
          f"{len({t['sheet_id'] for t in tasks})} sheets, "
          f"{len({(t['sheet_id'], t['alignment']) for t in tasks})} alignments, "
          f"in {time.time() - t0:.0f} s -> {out}")
    print("  by agency:", dict(by_agency))
    print("  by type:", dict(by_type))
    return 0


if __name__ == "__main__":
    sys.exit(main())

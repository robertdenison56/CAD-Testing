"""Build the Track D (D1) leaderboard from the published runs.

    python scripts/make_leaderboard.py [--runs benchmarks/runs] [--readme README.md] [--check]

Reads every ``benchmarks/runs/<run_id>/summary.json`` (written by
``python -m roaddraft.eval report results/<run_id> --publish``) and writes

    benchmarks/runs/LEADERBOARD.md    the ranked rows, the reference agents, every
                                      published run that is not ranked and why
    benchmarks/runs/leaderboard.json  the same, for the tracker
    README.md                         the board between the d1-leaderboard markers

A row is ranked only from a run on d1-test under a frozen spec with one
verifier throughout (eval plan sections 4.8, 4.9 and 9); the files are
generated, never edited by hand.  ``--check`` writes nothing and exits 1 when
any of them is out of date.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from roaddraft.eval import report  # noqa: E402


def outputs(runs: Path, readme: Path) -> dict:
    b = report.board(report.published(runs))
    out = {runs / "LEADERBOARD.md": report.render_board(b),
           runs / "leaderboard.json": json.dumps(b, indent=1, ensure_ascii=False) + "\n"}
    if readme.exists():
        out[readme] = report.replace_block(readme.read_text(encoding="utf-8"),
                                           report.render_board(b, readme=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", default=str(report.RUNS_DIR))
    ap.add_argument("--readme", default=str(REPO / "README.md"))
    ap.add_argument("--check", action="store_true", help="exit 1 if a file is out of date")
    args = ap.parse_args(argv)
    runs, readme = Path(args.runs), Path(args.readme)
    stale = []
    for path, text in outputs(runs, readme).items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for p in stale:
        print(("stale: " if args.check else "wrote ") + str(p))
    if not stale:
        print("leaderboard current")
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())

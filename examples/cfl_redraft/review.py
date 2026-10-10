"""Review images for a redrafted CFL sheet: the overlay (published blue, redraft red,
black where they agree), downscaled whole and cut into quadrants.

    .venv/bin/python examples/cfl_redraft/review.py CFL-D-Plan-and-Profile [--bases]

See wfl_redraft/review.py; this one points at the CFL folders.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "wfl_redraft"))

import review                                    # noqa: E402

review.REDRAFT = REPO / "examples" / "Exmple Plans" / "Redraft" / "CFL"
review.RESULTS = REPO / "examples" / "output" / "cfl_redraft" / "results"

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--out" not in args:
        args += ["--out", str(REPO / "examples" / "output" / "cfl_redraft" / "review")]
    review.main(args)

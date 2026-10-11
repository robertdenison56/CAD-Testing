"""Review images for a redrafted FDOT sheet (see wfl_redraft/review.py).

    .venv/bin/python examples/fdot_redraft/review.py FDOT-915-1-Roadway-Plan-Profile [--bases]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "wfl_redraft"))

import review                                    # noqa: E402

review.REDRAFT = REPO / "examples" / "Exmple Plans" / "Redraft" / "FDOT-NexGen"
review.RESULTS = REPO / "examples" / "output" / "fdot_redraft" / "results"

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--out" not in args:
        args += ["--out", str(REPO / "examples" / "output" / "fdot_redraft" / "review")]
    review.main(args)

"""Redraft the WFL sample plan sheets in bulk.

    .venv/bin/python examples/wfl_redraft/run_wfl.py --all [--workers 6]
    .venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p14 ...
    .venv/bin/python examples/wfl_redraft/run_wfl.py --family plan-profile

Each sheet is digitised (wflsheet), built (wflbuild), plotted, exported and overlaid on
its published sheet, into examples/Exmple Plans/Redraft/WFL/<source>/<sheet>/ (flhrun).
Per-sheet settings live in configs/<sheet>.json.  --summary collects the per-sheet results
into examples/Exmple Plans/Redraft/WFL/redraft-manifest.csv.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from flhrun import Pipeline                      # noqa: E402
import wflbuild                                  # noqa: E402
import wflsheet                                  # noqa: E402

PIPELINE = Pipeline(
    name="wfl", script=__file__,
    sheets_dir=REPO / "examples" / "Exmple Plans" / "Sheets" / "WFL",
    redraft_dir=REPO / "examples" / "Exmple Plans" / "Redraft" / "WFL",
    work_dir=REPO / "examples" / "output" / "wfl_redraft",
    configs_dir=HERE / "configs",
    std=wflsheet.Standard(), naming=wflbuild.Naming(),
    manual="the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming)",
    roles={"SUR": "Survey file (\"_sur\"): existing features -- the sheet's dashed linework and contour elevations.",
           "ALI": "Alignments file (\"_ali\"):",
           "HYD": "Drainage design file (\"_hyd_cor\"): the drainage system drawn heavy on the plan.",
           "COR": "Corridor file (\"_cor\"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files."},
    readme_dir="examples/wfl_redraft/README.md")


if __name__ == "__main__":
    raise SystemExit(PIPELINE.main())

"""Redraft the FDOT FDM 900-series exhibit sheets in bulk.

    .venv/bin/python examples/fdot_redraft/run_fdot.py --all [--workers 6]
    .venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-915-1-Roadway-Plan-Profile ...

Each sheet is digitised (wflsheet under the FDOT standard), built (wflbuild under the
FDOT naming), plotted, exported and overlaid on its published sheet, into
examples/Exmple Plans/Redraft/FDOT-NexGen/<sheet>/ (wfl_redraft/flhrun).  Per-sheet
settings live in configs/<sheet>.json.  --summary collects the per-sheet results into
examples/Exmple Plans/Redraft/FDOT-NexGen/redraft-manifest.csv.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "wfl_redraft"))

from flhrun import Pipeline                      # noqa: E402
import fdotbuild                                 # noqa: E402
import fdotsheet                                 # noqa: E402

PIPELINE = Pipeline(
    name="fdot", script=__file__,
    sheets_dir=REPO / "examples" / "Exmple Plans" / "Sheets" / "FDOT-NexGen",
    redraft_dir=REPO / "examples" / "Exmple Plans" / "Redraft" / "FDOT-NexGen",
    work_dir=REPO / "examples" / "output" / "fdot_redraft",
    configs_dir=HERE / "configs",
    std=fdotsheet.FDOT, naming=fdotbuild.FDOT,
    manual="the FDOT CADD Manual's standard file names (<type><discipline><sequence>)",
    roles={"SUR": "Survey development model (SURVRD01): existing features -- the sheet's dashed linework and contour elevations.",
           "ALI": "Alignment geometry (ALGNRD01):",
           "HYD": "Drainage structures, proposed (DRPRRD01): the drainage system drawn heavy on the plan.",
           "COR": "2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01."},
    readme_dir="examples/fdot_redraft/README.md")


if __name__ == "__main__":
    raise SystemExit(PIPELINE.main())

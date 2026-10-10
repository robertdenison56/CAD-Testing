"""Redraft the CFL sample plan sheets in bulk.

    .venv/bin/python examples/cfl_redraft/run_cfl.py --all [--workers 6]
    .venv/bin/python examples/cfl_redraft/run_cfl.py CFL-D-Plan-and-Profile ...

Each sheet is digitised (wflsheet under the CFL standard), built (wflbuild under the CFL
naming), plotted, exported and overlaid on its published sheet, into
examples/Exmple Plans/Redraft/CFL/<source>/<sheet>/ (wfl_redraft/flhrun).  Per-sheet
settings live in configs/<sheet>.json.  --summary collects the per-sheet results into
examples/Exmple Plans/Redraft/CFL/redraft-manifest.csv.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "wfl_redraft"))

from flhrun import Pipeline                      # noqa: E402
import cflbuild                                  # noqa: E402
import cflsheet                                  # noqa: E402

PIPELINE = Pipeline(
    name="cfl", script=__file__,
    sheets_dir=REPO / "examples" / "Exmple Plans" / "Sheets" / "CFL",
    redraft_dir=REPO / "examples" / "Exmple Plans" / "Redraft" / "CFL",
    work_dir=REPO / "examples" / "output" / "cfl_redraft",
    configs_dir=HERE / "configs",
    std=cflsheet.CFL, naming=cflbuild.CFL,
    manual="the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter)",
    roles={"SUR": "Terrain file (TER): existing features -- the sheet's dashed linework and contour elevations.",
           "ALI": "Alignment design file (ALI):",
           "HYD": "Drainage design file (DRN): the drainage system drawn heavy on the plan.",
           "COR": "Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files."},
    readme_dir="examples/cfl_redraft/README.md")


if __name__ == "__main__":
    raise SystemExit(PIPELINE.main())

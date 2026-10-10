"""Review images for a redrafted WFL sheet: the overlay (published blue, redraft red,
black where they agree), downscaled whole and cut into quadrants for a closer look.

    .venv/bin/python examples/wfl_redraft/review.py WFL-Plan-Profile-Sheets-p14 [--out DIR] [--bases]

Writes <out>/<sheet>-overlay.png (1700 px wide) and <sheet>-q1..q4.png (the four quarters
at 1500 px), and prints the sheet's build summary.  --bases also renders each design file
alone (<sheet>-SUR.png, -ALI.png, -COR.png).  Sheet inches for a pixel in a quarter image
of a 17 x 11 sheet: x = x0 + px / 1500 * 8.5, y = y1 - py / qh * 5.5, where (x0, y1) is
the quarter's top-left (q1: 0, 11; q2: 8.5, 11; q3: 0, 5.5; q4: 8.5, 5.5).
"""
import argparse
import json
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REDRAFT = REPO / "examples" / "Exmple Plans" / "Redraft" / "WFL"
RESULTS = REPO / "examples" / "output" / "wfl_redraft" / "results"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--out", default=str(REPO / "examples" / "output" / "wfl_redraft" / "review"))
    ap.add_argument("--bases", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for pid in a.ids:
        res = json.loads((RESULTS / f"{pid}.json").read_text()) if (RESULTS / f"{pid}.json").exists() else {}
        print(json.dumps({k: res.get(k) for k in ("id", "status", "kind", "family", "fpi", "twist", "twist_how",
                                                   "template", "title_box", "sheet_file", "bases", "alignments",
                                                   "callouts", "paths", "texts", "fields", "error")}, default=str))
        hits = list(REDRAFT.glob(f"*/{pid}/*-overlay.png")) + list(REDRAFT.glob(f"{pid}/*-overlay.png"))
        if not hits:
            print(f"{pid}: no overlay")
            continue
        im = Image.open(hits[0])
        W, H = im.size
        small = im.copy()
        small.thumbnail((1700, 1100))
        small.save(out / f"{pid}-overlay.png")
        for i, (x0, y0) in enumerate(((0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2)), 1):
            q = im.crop((x0, y0, x0 + W // 2, y0 + H // 2))
            q.thumbnail((1500, 1000))
            q.save(out / f"{pid}-q{i}.png")
        print(f"{pid}: {out / (pid + '-overlay.png')} and q1..q4")
        if a.bases and res.get("bases"):
            from roaddraft.api.session import Session
            folder = hits[0].parent
            for code, name in res["bases"].items():
                s = Session.load(folder / name, out_dir=out)
                png = out / f"{pid}-{code}.png"
                r = s.query("render_model", {"dpi": 60, "path": str(png)})
                if r.get("ok"):
                    b = Image.open(png)
                    b.thumbnail((1500, 1000))
                    b.save(png)
                    print(f"{pid}: {code} -> {png}")
                else:
                    print(f"{pid}: {code} render failed: {r.get('error')}")


if __name__ == "__main__":
    main()

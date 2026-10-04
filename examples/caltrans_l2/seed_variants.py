"""Seeded-error variants of the rebuilt sheet L-2, with the truth written down.

    python examples/caltrans_l2/seed_variants.py [--out DIR]

The rebuild aims every callout's leader at the station and offset its text names, so the sheet
is correct by construction. Each variant here breaks that in a known way:

* ``labels``: the text is edited (a station or offset changed by a known amount, a side
  swapped, digits transposed) while the leader still points at the true place;
* ``tips``: the text is left alone and the leader is aimed somewhere else (a tip drawn ahead
  of the end it marks, on the wrong side of the line, a few feet off), as happens when a
  drafter snaps to a wall rather than its end;
* ``clean``: nothing changed, the precision baseline.

For each variant a PDF is exported and a seed list is written in the stacheck engine's
``SeedList`` format (StaOffsetChecker/engine, ``stacheck seed VARIANT.pdf --seeds
VARIANT.seeds.json``): one entry per wrong callout with ``delta_ft`` = labeled minus drawn, on
the station or on the signed offset (right positive). Every other callout on the sheet is right,
so any flag on it is a false flag.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_sheet                                                 # noqa: E402
import sheet_content as C                                          # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output" / "seeded"
STATION_RE = re.compile(r"(\d+)\+(\d+\.\d+)")
OFFSET_RE = re.compile(r"(\d+\.\d+)' (Lt|Rt)")

# (callout index in sheet_content.CALLOUTS, what changes, by how much). Label edits change the
# text and keep the leader; tip moves change where the leader is aimed and keep the text.
#   label_station / tip_station: feet along the alignment
#   label_offset  / tip_offset:  feet on the magnitude of the offset, side kept
#   label_side    / tip_side:    the side swapped
#   label_station_text: the station text replaced outright (a typo)
VARIANTS = {
    "clean": [],
    "labels": [
        (0, "label_station", 0.75),        # 586+57.73 -> 586+58.48: just over the 0.5 ft tolerance
        (1, "label_offset", 5.0),          # 20.83' Lt -> 25.83' Lt
        (2, "label_station", 5.0),         # '"SR 70"', a designator written with a space
        (3, "label_station", 5.0),         # 587+77.96 -> 587+82.96
        (4, "label_side", None),           # 21.00' Rt -> 21.00' Lt
        (5, "label_station", 2.0),         # END BRIDGE 586+48.00 -> 586+50.00, station-only
        (9, "label_station_text", "585+30.57"),  # 585+03.57 with the feet digits transposed
        (10, "label_offset", 1.0),         # 21.00' Rt -> 22.00' Rt
        (12, "label_station", 100.0),      # 586+02.86 -> 587+02.86, still on this sheet
    ],
    "tips": [
        (0, "tip_station", 2.0),           # arrow drawn 2 ft ahead of the wall end
        (1, "tip_offset", -5.0),           # arrow drawn 5 ft nearer the centerline
        (3, "tip_station", -10.0),
        (4, "tip_side", None),             # arrow drawn on the other side of the line
        (5, "tip_station", 0.75),          # END BRIDGE: a minor discrepancy
        (9, "tip_station", 0.3),           # inside the tolerance: must not flag
        (10, "tip_offset", 10.0),          # arrow drawn 10 ft further out
        (12, "tip_station", 50.0),
    ],
}


def station_text(value):
    hundreds, feet = divmod(round(value, 2), 100)
    return "%d+%05.2f" % (hundreds, feet)


def seeded_entry(entry, change, amount):
    """The CALLOUTS tuple after one change, plus the seed that records it (or None)."""
    station, offset, x, y, content = entry[:5]
    tail = entry[5:]
    kind, delta, new_station, new_offset, new_content = None, 0.0, station, offset, content
    if change == "label_station":
        new_content = STATION_RE.sub(station_text(station + amount), content, count=1)
        kind, delta = "station", amount
    elif change == "label_station_text":
        match = STATION_RE.search(content)
        labeled = int(match.group(1)) * 100 + float(match.group(2))
        new_labeled = int(amount.split("+")[0]) * 100 + float(amount.split("+")[1])
        new_content = STATION_RE.sub(amount, content, count=1)
        kind, delta = "station", new_labeled - labeled
    elif change == "label_offset":
        magnitude = abs(offset) + amount
        new_content = OFFSET_RE.sub("%.2f' \\2" % magnitude, content, count=1)
        kind, delta = "offset", (1 if offset > 0 else -1) * magnitude - offset
    elif change == "label_side":
        other = "Lt" if offset > 0 else "Rt"
        new_content = OFFSET_RE.sub(r"\1' " + other, content, count=1)
        kind, delta = "side", -offset - offset
    elif change == "tip_station":
        new_station = station + amount
        kind, delta = "station", -amount
    elif change == "tip_offset":
        new_offset = (1 if offset > 0 else -1) * (abs(offset) + amount)
        kind, delta = "offset", offset - new_offset
    elif change == "tip_side":
        new_offset = -offset
        kind, delta = "side", offset - new_offset
    else:
        raise ValueError(change)
    assert new_content != content or (new_station, new_offset) != (station, offset), change
    seed = {
        "sheet_index": 0,
        "label_text": new_content,
        "kind": kind,
        "delta_ft": round(delta, 4),
        "name": "%s %+g" % (change, amount) if isinstance(amount, (int, float)) else change,
        "note": "%s: %s" % (change, amount),
    }
    return (new_station, new_offset, x, y, new_content) + tuple(tail), seed


def build_variant(name, changes, out_dir, quiet=True):
    original = list(C.CALLOUTS)
    callouts = list(original)
    seeds = []
    for index, change, amount in changes:
        callouts[index], seed = seeded_entry(callouts[index], change, amount)
        seeds.append(seed)
    C.CALLOUTS[:] = callouts
    try:
        _, session = build_sheet.build(out_dir, quiet=quiet)
    finally:
        C.CALLOUTS[:] = original
    pdf = out_dir / ("L-2-%s.pdf" % name)
    r = session.query("export_pdf", {"path": str(pdf)})
    if not r["ok"]:
        raise SystemExit("export_pdf failed: %s" % r["error"])
    seeds_path = out_dir / ("L-2-%s.seeds.json" % name)
    seeds_path.write_text(json.dumps(
        {"source_name": pdf.name, "seeds": seeds}, indent=1))
    return pdf, seeds_path, seeds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = Path(__file__).resolve().parents[1] / "output" / build_sheet.MODEL_FILE
    if not (out / build_sheet.MODEL_FILE).exists():
        if not model.exists():
            raise SystemExit("build the model first: python examples/caltrans_l2/build_all.py")
        shutil.copy(model, out / build_sheet.MODEL_FILE)
    for name in args.variants:
        pdf, seeds_path, seeds = build_variant(name, VARIANTS[name], out)
        print("%s: %d seeded errors -> %s, %s" % (name, len(seeds), pdf.name, seeds_path.name))
        for seed in seeds:
            print("    %-28s %+8.2f ft  %s" % (seed["name"], seed["delta_ft"],
                                            seed["label_text"].splitlines()[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

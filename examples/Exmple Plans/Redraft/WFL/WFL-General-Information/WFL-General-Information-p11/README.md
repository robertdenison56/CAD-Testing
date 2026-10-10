# WFL-General-Information-p11 -- redraft

WFL sample plan sheet **A.3** (VICINITY MAPS), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-General-Information-p11.pdf`.

| File | What it holds |
|---|---|
| `erfo2016-1_pln_gen.rdraft` | Sheet **A.3**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `erfo2016-1_pln_gen.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `erfo2016-1_pln_gen-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 30 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 11 at the element the published leader touches, 19 at a point).

## Notes

- File names: `erfo2016-1_pln_gen.rdraft` from the project number (WA FS ERFO 2016(1)-20(1)).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-General-Information-p11` (pipeline: examples/wfl_redraft/README.md).

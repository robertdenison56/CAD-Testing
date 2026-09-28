# Drafting-probes (T1) driven by real models — 2026-09-20

First run of the eight `draft-*` probes: draft design data from a description.
Same rig as the 2026-09-19 T2 run (`bridge.py`, one persistent `roaddraft-mcp`
per probe, `--autosave --trace`), same rules plus one: **no calculator** — the
model has the MCP tool surface and nothing else, so any arithmetic is its own.
One attempt per probe per model (n = 1). Scored from the document left on disk.

| probe | the trap | Fable 5.1 | Haiku 4.5 |
|---|---|---|---|
| `draft-tangent-ne` | northing / easting order | pass | pass |
| `draft-pi-curve` | the road does not pass through its PI | pass | pass |
| `draft-bearing-distance` | bearing, distance, deflection -> coordinates | pass | **FAIL** end 187.6 ft out |
| `draft-edges-shoulders` | a width is not an offset (8 ft shoulder = 20 ft) | pass | pass |
| `draft-turn-lane` | new edge is 24 R, only between its stations | pass | **FAIL** drew it at 12 R, on the existing edge |
| `draft-cul-de-sac` | edges stop where they meet the bulb | pass | **FAIL** took the far root; edges run through the bulb |
| `draft-building` | rectangle turned off-axis, new layer | pass | pass |
| `draft-roadway` | the whole job: 3 bearings, widths, stationing | pass | **FAIL** end 643.6 ft out |
| | | **8 / 8** | **4 / 8** |
| tool calls / faults | | 92 / 8 (8.7 %) | 87 / 16 (18.4 %) |

Unlike the T2 find-probes (9/9 for both models), these separate the models.

## The two kinds of failure

**Tooling gap (2 of Haiku's 4).** The engine prints bearings everywhere and
accepts none: `create_alignment` takes PI *coordinates* only, and nothing turns
"N 62°30'00\" E, 900.00 ft" into a point. So a described alignment has to be
worked out by hand. Fable did it — sin 62.5° to twelve figures from a Taylor
series, 118 s, twice as long as any other probe — and then read the bearings
and the 1,100 ft leg back with `get_design_data` to check. Haiku converted
azimuth 97.5° to "S 7°30' E", landed 188 ft out, verified nothing, and reported
success. On the three-leg roadway it built an alignment 2,754 ft long against
2,080. This is the T1 analog of the viewport trigonometry that blocked T2: work
a drafting tool exists to do. Civil 3D has 'BD / 'DD transparent commands and
ORD has line-by-bearing; this engine has nothing.

**Drafting reasoning (the other 2).** These are the capability the probes are
for, and no tool fixes them:
- *turn lane*: "12 ft wide, on the right" was drawn 12 ft from the centerline,
  exactly on top of the existing edge of pavement. It never looked at what was
  already there (`find_entities` would have shown edges at +/-12).
- *cul-de-sac*: set up (x-3000)^2 + (y-2400)^2 = 45^2 correctly, then took
  y = 2400 **+** sqrt(1829). The edges run through the bulb and out the far side.

## What else the runs found

1. **The engine rejected its own end station.** SR-100 is 4675.2488 ft long, so
   its end is written `56+75.25` everywhere — and `station_to_xy "56+75.25"`
   answered "does not exist on this alignment (10+00.00 to 56+75.25)". Fixed:
   a station within half a hundredth of either end is that end.
2. **`get_design_data` without `kind`** is the commonest fault in every run so
   far (6 here, 2 in the T2 run): models ask for design data by alignment alone.
   Fixed: `kind` defaults to `alignments`, and the answer lists the other kinds.
3. **Nothing said which way round a point is.** Both Fable instances that needed
   it noted that `[x, y]` = [easting, northing] is never stated; they assumed it
   and confirmed from a bearing. Now stated in the MCP instructions and on
   `create_alignment`. (`POINT` / `PI_ITEM` are pinned to the Phase 1 spec, so
   not there.)
4. **Haiku omits `space`** on `draw_line` / `draw_circle` / `draw_polyline` /
   `annotate_stationing` (4 faults) and reaches for `set_current_layer {layer:}`
   (3). Every one recovered from the teaching error on the next call. Not
   changed: an explicit space is a deliberate guard.
5. **"Do not save under another name" was ignored** by Haiku in 5 of 8 runs.
   The bridge now runs the server from the project folder, so those files
   landed beside the project and none reached the repository; autosave is
   pinned to the opened file, so no score was affected.
6. **A scorer bug, caught by the tests before the run**: an alignment a hair
   short of its description was reported as leaving its path "by inf ft" (the
   expected end point has no perpendicular station on it). A correct answer
   with rounded coordinates would have been failed.

Fixes 1-3 were made *after* these runs; the numbers above are for the surface
as it was. They would have removed 5 of Fable's 8 faults.

## Caveats

Same as the T2 run: shell bridge, not a native MCP client; n = 1; isolation
asked for, not enforced. One more, specific to T1: **the no-calculator rule is
mine.** A model in Claude Code has a shell and would simply compute the PI
there; a model in a chat client with only this MCP server would not. The rule
measures the second case, which is the one the engine can do something about.

## Layout

    bridge.py  setup_runs.py  score_runs.py      the rig (setup_runs.py LABEL draft)
    runs/t1-<model>/<probe>/trace.jsonl           every tool call, in order
    runs/t1-<model>/<probe>/project/              the documents left behind (+ journal)
    runs/t1-<model>/<probe>/renders/              what the model looked at

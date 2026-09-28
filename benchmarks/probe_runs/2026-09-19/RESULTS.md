# Find-probes driven by real models — 2026-09-19

First time any probe was attempted by a model rather than a script.
Server code: `a071eb7` plus the then-uncommitted `--autosave` / `--trace` flags.
One attempt per probe per model (n = 1). Scored by `roaddraft.probes` from the
document each run left on disk, never from what the model said it did.

| | Fable 5.1 | Haiku 4.5 |
|---|---|---|
| **probes passed** | **9 / 9** | **9 / 9** |
| tool calls | 106 | 84 |
| faults (all recovered on the next call) | 3 (2.8 %) | 11 (13.1 %) |
| `place_callout` right first time | 8 / 8 runs | 1 / 8 runs |
| callouts drawn on the sheet / in the model | 10 / 0 | 10 / 0 |
| aimed by name (`target_entity` / `target_anchor`) / raw point | 8 / 2 / 0 | 7 / 3 / 0 |
| leader-tip error, every callout | 0.00 ft | 0.00 ft |

## What this does and does not show

**It shows** that the T2 shape — annotate a sheet whose design is referenced
in — is possible for a real model on this engine, including a small one, with
no instruction beyond the probe's one sentence and what the MCP server says
about itself. Every callout went on the sheet and was aimed by name, including
on the five probes that never mention paper space: the server's `instructions`
steered that. Before `a071eb7` that route did not exist (`target_entity` on a
sheet was a fault).

**It does not show:**

- **T1.** All nine probes are find-and-annotate. Nothing here asks a model to
  *draft* an alignment or pavement edges from a description. The Sep-10 gate is
  T1 *and* T2; T1 is still unprobed.
- **Headroom.** 9/9 from the smallest current model means the pass/fail score
  is saturated. The probes discriminate only in process (fault rate, first-try
  success), not in outcome. A benchmark needs harder tasks than these.
- **Drafting quality.** The check is aim within 1 ft. It does not look at where
  the text sits, whether it overlaps linework, or what it says (beyond a
  station on two probes). Fable placed text clear of the road after looking at
  a render; Haiku put text wherever and still passed.
- **A native MCP client.** The bundled `claude` CLI was not logged in, so the
  models were Agent-tool subagents driving `bridge.py`: a shim that holds ONE
  long-lived `roaddraft-mcp` process over real stdio JSON-RPC and exposes
  `instructions` / `tools` / `describe` / `call`. Same server text, schemas,
  results and faults; but tools were invoked as `rd call TOOL '{json}'` through
  a shell, not as native function calls, and schemas were read on demand rather
  than all loaded up front (which probably *raises* the guessed-parameter fault
  rate relative to a native client). Re-run natively with
  `python -m roaddraft.probes setup <id>` and the `claude mcp add` line it prints.
- **Isolation.** Subagents were told to touch nothing but the bridge and
  reported compliance; that was not enforced. They ran with the repo as their
  working directory.

## What the runs found (things no scripted solution could)

1. **The harness lost work.** `roaddraft-mcp --doc` never wrote the document
   back; a model's work vanished when the server exited unless it thought to
   call `save_document`, which no prompt asks for. -> `--autosave`.
2. **Models "save as".** Three Haiku runs finished with `save_document` under a
   relative name of their own, which (a) landed in the repo root, the server's
   inherited cwd, and (b) would have redirected autosave away from the scored
   file had any command followed. None did, so no score was affected. ->
   autosave is pinned to the opened file; the bridge now runs the server from
   the project folder.
3. **Self-reports are unreliable, traces are not.** Haiku's `pc-by-station`
   report says every command succeeded first time; the trace shows a fault.
   -> `--trace` (queries and faults, which the journal does not keep).
4. **`at` reads like "where to put it".** 5 of Haiku's 11 faults are
   `place_callout` without `position` — it passed the text point as `at`, or
   used `sheet` / `text` for `space` / `content`. -> `at` and `position`
   descriptions now say which is which.
5. **`position` never said how the text is justified.** Two Fable instances
   flagged this independently; both had to read the entities back to find out.
   -> documented (reads away from the target; vertically centred).
6. **`find_entities` rows: `point` is the middle of the whole entity,
   `sheet_point` the middle of the part shown.** One Fable instance found that
   briefly inconsistent. Documented behaviour; worth a clearer row some day.
7. **Warnings work as feedback.** Haiku's first curve callout ran off the
   sheet; it read "extends beyond the sheet extents", called `undo`, and
   re-placed. (Which is why the bridge keeps one persistent server: undo has to
   span calls, as it does for a native client.)
8. **Teaching errors work.** 14 faults across both runs, 14 recoveries on the
   very next call.
9. **The models took routes the script does not.** Found edges by layer
   (`V-ROAD-EOP`) rather than by design anchor; aimed the centerline by station
   (`target_anchor="50+00"`) rather than by entity; self-verified with
   `sheet_to_model` and `xy_to_station`.

Not fixed, noted: a `save_document` to another folder moves the document's
path, so relative references stop resolving from there — with no warning.
AutoCAD behaves the same way, but a warning would teach.

## Layout

    bridge.py  setup_runs.py  score_runs.py      the rig
    runs/<model>/<probe>/trace.jsonl             every tool call, in order
    runs/<model>/<probe>/project/                the documents left behind (+ journal)
    runs/<model>/<probe>/renders/                what the model looked at
    runs/haiku/_stray_saves/                     the three "save as" files, moved out of the repo root

Re-score: `python score_runs.py fable` (paths inside assume the rig's own folder).

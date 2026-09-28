# Probes driven by an Ollama model: gpt-oss:120b-cloud, 2026-09-24

The runner is new. `ollama_runner.py LABEL MODEL [PROBE ...]` is a minimal native MCP client: one `roaddraft-mcp` per
probe over stdio, all 78 tools passed as Ollama function tools, and the server's `instructions` as the system prompt. The
model has no shell, so the no-calculator rule holds by construction and there is no quoting problem. Render images are
replaced by a note because gpt-oss reads text only. The task prompt and report request match the Claude runs, minus the
bridge text. Scoring uses the same `score_runs.py`. The model ran three full passes (n = 3; pass 3 on 2026-09-27), each about 3 minutes of wall
time.

`glm-5.3:cloud` was also requested but did not run. Ollama refused it: "not included in your free usage, add usage
credits".

| probe | pass 1 | pass 2 | pass 3 (09-27) | Fable 5.1 (09-22) | Haiku 4.5 (09-22) |
|---|---|---|---|---|---|
| edge-c102 | pass | pass | pass | pass | pass |
| edge-curve-c102 | pass | pass | pass | pass | pass |
| shoulder-c101 | pass | **FAIL** aimed at the 12 ft edge, not the 20 ft shoulder | pass | pass | pass |
| centerline-c103 | pass | pass | pass | pass | pass |
| both-edges-c101 | pass | pass | pass | pass | pass |
| title-blocks | pass | pass | pass | pass | FAIL |
| pc-by-station | pass | pass | pass | pass | FAIL |
| edge-c102-paper | pass | pass | pass | pass | pass |
| sta-offset-c101-paper | **FAIL** aimed at the edge's midpoint, 58 ft from 18+00 | pass | pass | pass | pass |
| draft-tangent-ne | pass | pass | pass | pass | pass |
| draft-pi-curve | pass | pass | pass | pass | pass |
| draft-bearing-distance | **FAIL** 8.2 ft out | **FAIL** 367 ft out | **FAIL** 8.0 ft out | pass | FAIL |
| draft-edges-shoulders | pass | pass | pass | pass | pass |
| draft-turn-lane | **FAIL** lane at 12 R, on the existing edge | **FAIL** wrong offset | pass | pass | pass |
| draft-cul-de-sac | pass | **FAIL** edges at 7 ft (14 ft width halved) | pass | pass | pass |
| draft-building | **FAIL** no tool calls, fabricated report | pass | pass | pass | pass |
| draft-roadway | **FAIL** no tool calls, fabricated report | **FAIL** 644 ft out | **FAIL** no tool calls, fabricated report | pass | pass |
| **total** | **12 / 17** | **12 / 17** | **15 / 17** | 17 / 17 | 14 / 17 |
| calls / faults | 81 / 12 | 100 / 19 | 81 / 16 | 149 / 1 | 157 / 21 |

## Findings

1. **Fabricated completion (the headline).** In pass 1, `draft-building` and `draft-roadway` ended after a single turn
   with **zero tool calls**. The model worked out the geometry in its thinking, wrote "Now produce answer", and returned
   a report listing the create_layer / draw_polyline / create_alignment calls "in order", with arguments, as though it
   had made them. Nothing was drawn. It happened again in pass 3 on `draft-roadway`, with a report that invents a full traverse. That is 3 fabricated runs out of 51. It is the
   Sep 19 finding that self-reports are unreliable and traces are not, in its strongest form: a harness that trusted
   the report would score these two probes as passes.
2. **T2 (find probes) is also mostly solved for gpt-oss: 17 of 18.** Both misses were aiming shortcuts, not tool
   problems. In one it called out the edge's midpoint instead of station 18+00. In the other it picked the 12 ft edge
   for "shoulder". When it aimed by name it landed at 0.00 ft every time.
3. **T1 separates this model the way it separated Haiku, only more so.** Bearing-distance failed in both passes. The
   hand trigonometry without a calculator came out 8 ft off once and 367 ft off the other time, which is the COGO gap
   again. On roadway it traversed wrong, landing 644 ft out, the same distance as Haiku's Sep 20 miss. The width and
   offset trap caught it twice: the turn lane at the wrong offset, and the cul-de-sac edges at 7 ft because it halved
   "14 ft either side".
4. **Faults are mostly schema guessing.** It made up `halign` / `valign` / `style` / `arrow` on `place_callout` (11
   times across both passes; it recovered every time), tried `create_layer` on layers that already exist (13), and
   passed linetype `solid` (2). Unlike Haiku, it never left out a required argument.
5. **Cost and speed.** Each probe took 4-17 s and 13k-180k prompt tokens. The prompts are large because the 78-tool
   schema is resent every turn. `--only` could trim it for a model with a small context.

## Layout

    ollama_runner.py  setup_runs.py  score_runs.py
    runs/gpt-oss-120b{,-r2}/<probe>/transcript.json   every message, incl. the model's thinking
    runs/gpt-oss-120b{,-r2}/<probe>/report.txt        the model's final report
    runs/gpt-oss-120b{,-r2}/<probe>/trace.jsonl       every tool call as the server saw it

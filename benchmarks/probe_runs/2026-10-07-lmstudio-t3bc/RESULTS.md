# Tier-3 batches B and C, the local models through LM Studio, 2026-10-07/08

Batch B (`equation-data`, `width-dims`, `row-data`) and batch C (`qa-alignment-data`, `l2-match-lines`,
`l2-alignment-data`) had not been run by any model. Robert asked for the first pass on the local models through
LM Link. Every LLM on RobertsPC that LM Studio marks `tool_use` and that holds a 65,536 context ran, one at a time,
alone on the GPU:

| model | quant | arch | tool schema on its tokenizer | notes |
|---|---|---|---|---|
| `qwen/qwen3.5-9b` | Q4_K_M | qwen35 | 22,046 tokens | the RQ3 fine-tune subject |
| `zai-org/glm-4.6v-flash` | Q4_K_M | glm4 | 21,500 | streamed with the call cap (below) |
| `google/gemma-4-e4b` | Q4_K_M | gemma4 | 18,589 | list-valued `type` rewritten to `anyOf` (below) |
| `meta-llama-3.1-8b-instruct` | Q4_K_M | llama | 25,968 | no turn completed (below) |

Not run: `mistralai/mistral-7b-instruct-v0.3` (no `tool_use`, 32k context: the schema alone is 22k) and
`qwen/qwen2.5-vl-7b` (no `tool_use`).

The rig is the 2026-10-04 LM Studio rig: one `roaddraft-mcp` per probe over stdio, all 78 tools as function tools,
the server's `instructions` as the system prompt, the probe's `prompting.task_text` as the user message (now
written to each probe's `prompt.txt` by `setup_runs.py`; the same words as before for these probes), no shell,
renders replaced by a note, context 65,536, one slot, `--budget 60` minutes per probe, at most 120 turns.
`run_models.py` loads each model alone and records `model.json`. Four guards were added to the runner during the
pass, each after a model hit something the Oct 4 runner could not survive; they are described under "How the pass
was run" and none of them could have changed a probe that ran before it. Scoring is `score_runs.py` on the
documents left on disk; `make_deliverables.py LABEL` prints each document beside the probe's scripted reference
(`runs/<model>/deliverables/OVERVIEW.png` for the grid; the reference projects are kept once in `references/`).

**0 of 24.** No local model passes any batch-B or batch-C probe. Three of the four worked every probe through the
engine until they stopped, the budget or a limit stopped them; Llama 3.1 8B never completed a single turn.

| probe | Qwen3.5-9B | GLM-4.6V-Flash | Gemma-4-E4B | Llama-3.1-8B |
|---|---|---|---|---|
| width-dims | FAIL: detached the design reference, so all three sheets lost the road; created its own SR-100 10 times and deleted it 9; 3 dimensions, none the 8 ft left shoulder at 17+00 | FAIL: created its own SR-100 in the sheet file, a viewport and a title block; all 5 dimension calls faulted, nothing dimensioned | FAIL: nothing placed; all 13 of its writes faulted | FAIL: no call |
| row-data | FAIL: tags and tables on C-102, numbered out of order (the first piece, a curve, tagged L1) | FAIL: 2 tables and a callout, no L1/C1 tags | FAIL: 6 callouts and 2 tables, no L1/C1 tags | FAIL: no call |
| equation-data | FAIL: `STA 35+00.00 BK = STA 35+50.00 AH`, right to the hundredth, lettered at 0°; square to the line is 108.43° | FAIL: nothing placed (turn-limit loop) | FAIL: nothing placed; 25 of 27 calls faulted | FAIL: no call |
| qa-alignment-data | FAIL: deleted T-1's bearing and length on C-101, which was right (15 deletions, 5 modifications, 4 new tables) | FAIL: nothing changed (turn-limit loop); the transposed BC 24+50.27 stays | FAIL: nothing changed (both curve-table calls faulted); the transposed BC stays | FAIL: no call |
| l2-match-lines | FAIL: 2 lines and 5 callouts; no match line crosses SR70 at 574+50 | FAIL: a match line at 574+50, drawn at 173.5° on the sheet; square is 90.1° | FAIL: 2 polylines and 2 callouts; none crosses SR70 at 574+50 | FAIL: no call |
| l2-alignment-data | FAIL: one text placed; its curve-table calls faulted | FAIL: a viewport, layers and a text style, no lettering | FAIL: 9 texts, 6 circles, a table, 2 callouts; the first tangent (576+16.93 to 578+47.69) has no bearing/length | FAIL: no call |
| **total** | **0 / 6** | **0 / 6** | **0 / 6** | **0 / 6** |

| model | calls / faults | fault rate | turns | wall clock | stops | prompt / completion tokens |
|---|---|---|---|---|---|---|
| Qwen3.5-9B | 501 / 42 | 8% | 503 | 4 h 50 min | budget 3, max_turns 1, length 1, answered 1 | 21.7 M / 196 k (159 k reasoning) |
| GLM-4.6V-Flash | 104 / 26 | 25% | 32 (26 cut at the call cap) | 2 h 11 min | answered 4, turn_limit 2 | 0.13 M* / 34 k |
| Gemma-4-E4B | 106 / 54 | 51% | 112 | 1 h 6 min | answered 6 | 2.77 M / 152 k (141 k reasoning) |
| Llama-3.1-8B | 0 / 0 | n/a | 0 | 33 min | parser error 2, terminated 4 | n/a |

\* LM Studio reports usage only at the end of a stream, so a turn cut at the call cap has none; GLM's prompt
count covers its six uncut turns only.

## Findings

1. **Batches B and C are out of reach of every local model at n = 1.** The same Qwen scored 11/17 on the first
   tier (Sep 29) and 0/6 on Tier 2 (Oct 4); Haiku 4.5 scored 1/4 and Fable 5.1 4/4 on batch A (Oct 6, Oct 7).
   Nothing here separates the three models that ran; what separates them is how they fail (2-6). Gemma and GLM
   changed nothing at all on five of their twelve probe runs (Gemma's width-dims, equation-data and
   qa-alignment-data; GLM's equation-data and qa-alignment-data), so for them the batch mostly measures the
   protocol, not the drafting.

2. **The two closest misses are conventions, not data.** Qwen's equation lettering on `equation-data` is the
   right text to the hundredth, found by the check at the equation, at 0° where square to the line is 108.43°;
   its `row-data` tags and tables are on C-102, the tags numbered out of order. Both are the batch-A pattern from Haiku on Oct 6: the
   data read right, then lettered against the convention. GLM's one match line is at 574+50 and lettered, but
   runs at 173.5° on the sheet where square to SR70 is 90.1°.

3. **Two of three models worked around the reference instead of through it.** On `width-dims` Qwen detached the
   DESIGN reference, so C-101 to C-103 lost the road (the overview shows a short vertical stub where the road
   was), then created and deleted its own SR-100 10 and 9 times and hit the 120-turn cap. GLM created its own
   SR-100 in the sheet file beside the reference, then aimed five dimensions at it by a name the engine does not
   know (`no entity 'SR-100' to measure`). Haiku did the same on `stationing`
   on Oct 6. The engine's teaching errors say plainly that commands act only on the document's own design
   (`'DESIGN:SR-100' is an alignment in an attached reference, and commands only work on this document's own
   design`); the small models answer it by copying the design in.

4. **"Change nothing that is right" was broken by the one model that changed anything.** On `qa-alignment-data`
   Qwen deleted 15 entities, modified 5 and placed 4 tables, and lost T-1's bearing and length on C-101, which
   was not one of the five planted errors. GLM and Gemma left the first planted error (24+05.27 BC lettered
   24+50.27) in place and changed nothing: GLM never reached a write, Gemma's two curve-table calls faulted.

5. **Each open model breaks the tool protocol its own way; only Qwen ran it clean.** Qwen made exactly one call
   in each of 503 turns. GLM writes call after call in one turn without waiting for a result (26 of its 32 turns
   were cut at four calls), and on two probes moved its calls into its thinking, where LM Studio does not parse
   them, repeating one call there (247 `<tool_call>` blocks of `get_design_data` on `qa-alignment-data`) until the
   30-minute turn limit. Gemma's chat template cannot render a list-valued JSON Schema `type`, and LM Studio
   refuses the request; with the equivalent `anyOf`, 7 of its 54 faults are on one of the two rewritten tools
   (`draw_offset` items sent as nested lists), so the rewrite may not be neutral for it. Llama makes one call
   without reading anything (`place_label` at PC-1, `create_sheet`), then produces output LM Studio's tool
   parser rejects (`does not match the expected peg-native format`) or terminates after about six minutes. These
   are exactly what the new native runner (`roaddraft.runners`, 457deba) will meet on local endpoints; it has none
   of the four guards yet.

6. **Fault loops and reports.** Gemma's largest fault loop is `place_callout` with `at` but no `target_entity`,
   14 times. Its reports are accurate about failing ("I have exhausted multiple combinations of
   parameters for place_callout"; "No successful dimensions were placed"). GLM's `width-dims` report lists
   "Dimensions for Left Shoulder (8'), Two Lanes (12'), Right Shoulder (8') on sheet C-101": every one of its five
   `place_dimension` calls faulted and none is on disk. That is the fabricated completion gpt-oss:120b showed on
   Sep 24. Qwen returned no final content on any probe: the budget, the turn cap or the
   context ended five of them, and on `l2-alignment-data` it stopped after 40 turns with empty content and a
   thought that begins its plan again ("First, I should get the document state to see what's available"). On `equation-data` the
   conversation filled the 65,536 context while it was writing the report (`stop: length`).

## How the pass was run

Started 2026-10-07 22:13, last probe 2026-10-08 08:19. Four guards were added to `lmstudio_runner.py`, each
documented in its docstring, each tested before the relaunch:

- **Result cap** (after Qwen's 4th call on `l2-match-lines`, 01:50): `get_model_state` with
  `include_references` on the L-2 start returned 748,312 characters, a 467,928-token request no reload can fit,
  and the Oct 4 guard reloaded the model three times for nothing. Tool results are now cut to their first 30,000
  characters with a note, about what Claude Code's Bash tool shows of the shell bridge's output. No result in any
  earlier LM Studio run came near it (largest 12,886 characters); no result in this pass after it was cut
  (`truncated_results` 0 everywhere). A request over the context with the model already at 65,536 now stops the
  probe (`stop: "context"`) instead of reloading. Qwen's interrupted attempt is in `runs/qwen3.5-9b/_attempt1/`;
  the probe was re-set-up and rerun from scratch.
- **Call cap** (before GLM's pass, 03:50): GLM's first turn on `width-dims` did not return within the 1800 s
  request timeout. Streamed, the turn is a chain of calls written blind (`get_document_state`, `list_sheets`,
  `render_sheet`, ..., `place_text "C2"` at coordinates it had not read) at about five chunks a second. LM Studio
  ignores `parallel_tool_calls: false`, and a stop string on `<|observation|>` does not end it. The runner now
  streams every turn and ends it when a fifth call begins; the first four run. Qwen made one call per turn
  throughout this pass and at most four in any earlier pass, so the cap could not have bound it. A turn still
  gets 1800 s (`stop: "turn_limit"`). GLM's timed-out attempt is in `runs/glm-4.6v-flash/_attempt1/`.
- **Type-list rewrite** (Gemma, 06:05): `NotImplemented: map: filter-mapping not implemented` from Gemma's
  template on `draw_offset` and `annotate_stationing`, whose array items say `"type": ["number", "string"]`.
  `run_models.py` now tries the original schema first and, only on that refusal, hands the model the same schemas
  with list-valued types as `anyOf`; `model.json` records `type_lists_rewritten`. Qwen, GLM and Llama took the
  original.
- **Llama** was stopped after two probes (07:33) to look at its output, then its remaining four ran with the
  runner unchanged. No guard was added for it: salvaging a call from each six-minute turn would buy one blind call
  per turn.

The engine is `0adb6f9` plus the Oct 6 trajectories work that was in the working tree; another session committed
that work during the pass as `3781244`, with `457deba` (native runners), `5e143ea` (tier-2
`draft-fix-the-drawing` check) and `9ed9590` (Fable's Tier-2/batch-A run). None of them changes a batch-B/C check
or the tool surface (`tier3.py` changed only a solve helper). Scores are from `3781244`.

## Caveats

- n = 1 per model and probe. A 0/6 says these probes are beyond these models as run, not how often.
- The four guards mean the models did not all see an identical client: GLM's turns were cut at four calls,
  Gemma saw `anyOf` for two tools' items. Each change was the minimum that let the model's own calls reach the
  engine; the alternative was a row of zeros with no calls made.
- Text only, as for every open-model run: the models could render but not see the image.
- RobertsPC was shared once: the other session's `2026-10-07-runner-smoke` loaded Llama at 32k beside this
  pass's Qwen at 22:25 and sent Qwen its own requests around then, during Qwen's `width-dims`. That probe
  stopped on the 120-turn cap at 49 minutes, not on the budget, so the slower turns did not move where it
  stopped. The smoke run met the same Llama parser error (`peg-native format`) through `roaddraft.runners`.
- LM Studio's usage is missing for cut turns, so GLM's tokens are a floor.

## Files

    run_models.py                  loads each model alone, measures its schema cost, runs its probes
    lmstudio_runner.py             the native MCP client (Oct 4) + result cap, context stop, streamed turns with
                                   the call cap, the type-list rewrite
    setup_runs.py                  one fresh project, server.json and prompt.txt per probe
    score_runs.py                  scores each left-behind document and summarises its trace
    make_deliverables.py           per-probe PDFs beside the reference, OVERVIEW.pdf / OVERVIEW.png
    run.log                        the pass as it ran, restarts marked
    references/<probe>.reference/  the scripted solutions as finished RoadDraft projects, once for the rig
    runs/<model>/model.json        quant, context, schema cost, rewrite flag, start and finish
    runs/<model>/score.txt         score_runs.py output
    runs/<model>/<probe>/          prompt.txt, transcript.json (thinking and per-turn seconds), report.txt,
                                   trace.jsonl, project/ (the document as left)
    runs/<model>/deliverables/     the PDFs and the overview
    runs/<model>/_attempt1/        the interrupted attempts (Qwen l2-match-lines, GLM width-dims and row-data)

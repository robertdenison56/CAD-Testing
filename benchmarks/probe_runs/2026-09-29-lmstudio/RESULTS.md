# Probes driven by a local model through LM Studio: Qwen3.5-9B, 2026-09-29

Robert set up LM Studio with `qwen/qwen3.5-9b` (Q4_K_M GGUF, 6.55 GB, tool use + vision) and asked for a probe run. The
model lives on RobertsPC and is reached over LM Link; LM Studio on the Mac serves it at `localhost:1234` with the
OpenAI-compatible chat-completions API. `lmstudio_runner.py LABEL MODEL [PROBE ...]` is the Ollama rig's runner with the
model call swapped for that API: one `roaddraft-mcp` per probe over stdio, all 78 tools as function tools, the server's
`instructions` as the system prompt, the same task text and report request, no shell. The model's thinking comes back as
`reasoning_content`; it is kept in transcript.json but not sent back on the next turn. Renders are replaced by a note, as
for gpt-oss, even though this model could look at them. Engine at `d036399` (unchanged since the Sep 27 commits). Scoring
is `score_runs.py`, from the documents left on disk.

Two things about the setup mattered. The 78-tool schema plus `instructions` cost **21,862 prompt tokens** on this
tokenizer, and the model was loaded with a 16,384-token context, so every request failed with
`exceed_context_size_error` until it was reloaded with `lms load qwen/qwen3.5-9b --context-length 65536 --parallel 1`.
And one pass took **3 hours of wall clock**, against 3 minutes for gpt-oss:120b-cloud: the 15 probes that finished on
their own took 56 minutes between them (T2 probes 1 to 3 minutes each), and the two that did not are explained under
"How the pass was run".

| probe | Qwen3.5-9B | gpt-oss:120b pass 3 (09-27) | Fable 5.1 (09-22) | Haiku 4.5 (09-22) |
|---|---|---|---|---|
| edge-c102 | pass | pass | pass | pass |
| edge-curve-c102 | pass | pass | pass | pass |
| shoulder-c101 | pass | pass | pass | pass |
| centerline-c103 | pass | pass | pass | pass |
| both-edges-c101 | pass | pass | pass | pass |
| title-blocks | **FAIL** scale typed `1"=50'`, the probe asks for `1" = 50'` | pass | pass | FAIL |
| pc-by-station | pass | pass | pass | FAIL |
| edge-c102-paper | pass | pass | pass | pass |
| sta-offset-c101-paper | pass | pass | pass | pass |
| draft-tangent-ne | pass | pass | pass | pass |
| draft-pi-curve | pass | pass | pass | pass |
| draft-bearing-distance | **pass** | FAIL | pass | FAIL |
| draft-edges-shoulders | **FAIL** deleted its own correct edges of pavement | pass | pass | pass |
| draft-turn-lane | **FAIL** lane at 12 ft R, on the existing edge; stopped by hand at 63 min | pass | pass | pass |
| draft-cul-de-sac | **FAIL** edges run through the bulb | pass | pass | pass |
| draft-building | **FAIL** 40 ft side mirrored: a parallelogram, 28 of 44 points off | pass | pass | pass |
| draft-roadway | **FAIL** no alignment left; 60-minute budget, 8 faults in 12 calls | FAIL | pass | pass |
| **total** | **11 / 17** (T2 8/9, T1 3/8) | 15 / 17 | 17 / 17 | 14 / 17 |
| calls / faults | 136 / 18 (T2 57/4, T1 79/14) | 81 / 16 | 149 / 1 | 157 / 21 |

## Findings

1. **A 9B model running locally does T2 almost completely: 8 of 9, every callout aimed by name at 0.00 ft.** It found
   the route the MCP `instructions` teach without being told twice: `find_entities` (with `anchor` filters and
   `visible_on`), then `place_callout` with `target_entity`, on the sheet, through the viewport. For pc-by-station it
   used `resolve_anchor` on the referenced design and `model_to_sheet`; for the 18+00 offset it used `station_to_xy`
   with `offset` and `model_to_sheet`. The one T2 miss is a literal-text one: every title block got all three fields,
   but the scale reads `1"=50'` without the spaces the probe dictates. Whether the check should normalise whitespace
   is Robert's call; the check is unchanged here and the run is scored as it stands.
2. **It passed draft-bearing-distance, which gpt-oss:120b failed on all three passes and Haiku failed twice.** By hand:
   it turned N 62°30' E into a 27.5° math angle, recalled cos 27.5° = 0.8870109 and sin 27.5° = 0.4617486 (correct to
   seven digits), put PI-1 at [1798.31, 1415.57] with the 600 ft radius, worked the 35° right deflection to azimuth
   97.5°, and ran the second leg to [2888.90, 1271.99]. Two schema faults on the way (a radius on the END PI, then
   none on the interior PI), both recovered from the error's hint. 8 minutes, 5.8k reasoning tokens. The COGO gap is
   still a gap, but this is the first open model to cross it.
3. **The other five T1 probes failed in three ways, none of them schema guessing.**
   - *Width is not an offset*, twice. The turn lane went 12 ft right of centreline, on top of the existing edge, when
     the prompt's "12 ft wide" means a new edge 24 ft right (15 `station_to_xy` calls, all at offset 12 or less). The
     cul-de-sac got the right alignment and the right 45 ft circle, then `draw_offset ±14` for the whole length, through
     the bulb; the `station_range` argument that stops an offset short was never used. Haiku made both of these
     mistakes on Sep 20 and gpt-oss made the turn-lane one twice.
   - *Hand arithmetic*. The building's 60 ft side came out right ([1530, 1251.96]), then the 40 ft side at S 60° E was
     drawn with the northing sign flipped (+20 for -20), so the footprint is a parallelogram with two corners 40 ft off.
     On roadway the first traverse went north where S 80° E goes south, and after deleting and retrying it never again
     produced a PI list the engine would accept: angle points without a radius (twice), a radius on the end PI, a
     PI-2 hundreds of feet from where 700 ft on azimuth 60° lands.
   - *Losing track of its own entities*. On edges-shoulders it drew offsets at ±20 and ±6, deleted all twenty entities,
     redrew ±12 on V-ROAD-EOP and ±14 on V-ROAD-SHLD, deleted the ±14 set, drew ±20 on V-ROAD-SHLD, and then deleted
     `LN-016..LN-021, AR-011..AR-014`, which were its correct ±12 edges of pavement. The shoulders are right and the
     edges are gone. Nothing faulted; the model lost the map from ids to draws.
4. **Thinking length is the cost, and it is not bounded by the turn cap.** Across the pass the model produced 99k
   completion tokens, 88k of them reasoning. Roadway alone used 51.8k reasoning tokens in 12 turns, more than the other
   16 probes together; its longest turn generated 28.9k characters of thinking and took 10 minutes. The turn-lane probe
   ran 63 minutes for 21 calls. A 60-turn cap bounds nothing when one turn is ten minutes of thought, which is why the
   runner now has `--budget MIN`. For the next local-model pass, consider a `max_tokens` cap or the model's non-thinking
   mode as a second condition.
5. **The final report went into the thinking channel in 11 of the 16 probes that finished.** The model returned empty
   `content` and a complete, well-formed report inside `reasoning_content`, so report.txt is blank for those and the
   text is in transcript.json. A harness that read only `content` would conclude the model said nothing; one that
   trusted the report would be no worse off than usual, because the reports it did write matched the traces. Unlike
   gpt-oss, every probe made real tool calls (the fewest was 2): no fabricated completion this time.
6. **Faults: 18 in 136 calls (13%), the same rate as Haiku's 13.1%, and the same kinds.** `create_layer` on a layer that
   already exists (5), the two `create_alignment` PI rules (5: interior PIs need a radius, BEGIN/END cannot carry one),
   recreating an alignment that exists (2), one `delete_alignment` of a name already deleted, one `draw_alignment` on a
   referenced alignment, one callout not visible through any viewport of the named sheet, two `station_to_xy` against
   a sheet file's own (empty) design before it switched to `DESIGN:SR-100`. It recovered from every fault that it had
   turns left for. No invented parameters, which was gpt-oss's commonest fault. It asked for `render_model` twice and
   got the text-only note each time; this is a vision model, so a run that hands the PNG back is a natural follow-up.
7. **One stray save, contained.** On centerline-c103 it called `save_document path="C-103.rdraft"` despite the rule. The
   server runs with cwd = the probe's project folder, so the file landed there, and the scored document is the one
   `--autosave` pins.

## How the pass was run

The runner is the Ollama rig's with the model call swapped; its docstring lists the LM Studio specifics. The pass was
launched for all 17 probes in order and ran the first 13 unattended (19:02 to 19:43). draft-turn-lane then ran for
63 minutes and 21 tool calls at roughly one turn every three to ten minutes, five times longer than the slowest probe
before it, with nothing in the rig to end it short of 60 turns. It was **stopped by hand, mid-turn**: `trace.jsonl` and
the document are complete, but the runner writes transcript.json only when a probe ends, so that probe's messages and
thinking are lost; its transcript.json holds a stub with the tool calls from the trace and this explanation. The runner
then gained `--budget MIN` (a per-probe wall-clock budget checked between turns, and the seconds each turn took in
the transcript) and was restarted at 20:46 with `--budget 60` for the three remaining probes; it skips probes that
already have a report.txt. draft-roadway hit that budget (64.5 minutes, the overrun being its last turn). The scores
above are from disk for all 17, so neither stop changes how a probe is judged, but the two stopped probes did not get
the 60 turns the others had, and the budget was not in force for the first 13. None of those 13 took more than
12 minutes, so the budget would not have touched them.

## Deliverables: the plots, beside the scores

`make_deliverables.py qwen3.5-9b` prints what each probe left behind the way a drafter would plot it, through the
engine's own `print_pdf`, and puts a correct answer next to it, so a pass or a fail can be seen and not just read:

    runs/qwen3.5-9b/deliverables/OVERVIEW.png            the grid: every probe's result, framed green (pass) or red (fail)
    runs/qwen3.5-9b/deliverables/OVERVIEW.pdf            six pages, three probes each: verdict, the check's detail, calls
                                                         and faults; the model's result; the scripted reference solution
    runs/qwen3.5-9b/deliverables/<probe>.pdf             the model's document: the sheet(s) the probe names, on their own
                                                         34 x 22 in paper (all three for title-blocks), or model space fit
                                                         to ANSI D for the drafting probes
    runs/qwen3.5-9b/deliverables/<probe>.reference.pdf   Probe.solve on a fresh start document, printed the same way and,
                                                         in model space, to the same window as the model's print

The verdicts are `Probe.check` on the document on disk, the same call `score_runs.py` makes. In the overview the
fails read directly: the turn lane drawn along the existing edge instead of 12 ft outside it, the cul-de-sac edges
running through the bulb, the building as a parallelogram next to the rectangle, edges-shoulders with its shoulders
and no edges, and roadway as an empty window beside the full ELM-AVE design. The sheet prints are the T2 deliverable
itself: a callout on paper, pointing at the referenced edge, with the text the model chose.

## Layout

    lmstudio_runner.py  setup_runs.py  score_runs.py  make_deliverables.py
    runs/qwen3.5-9b/<probe>/transcript.json   every message, the model's thinking, per-turn seconds (after the restart)
    runs/qwen3.5-9b/<probe>/report.txt        the model's final report (blank where it went into the thinking channel)
    runs/qwen3.5-9b/<probe>/trace.jsonl       every tool call as the server saw it
    runs/qwen3.5-9b/run.log                   the runner's stdout: one meta line per probe, the 20:46 restart marked (not tracked: *.log)
    runs/qwen3.5-9b/deliverables/             the prints above: OVERVIEW.png, OVERVIEW.pdf, <probe>.pdf, <probe>.reference.pdf

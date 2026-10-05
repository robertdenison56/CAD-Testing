# Tier-2 probes, first model: Qwen3.5-9B through LM Studio, 2026-10-04

The six Tier-2 probes (`python -m roaddraft.probes list --tag tier2`, built 2026-10-03, committed as `ea78012`)
had not been run by any model. Robert asked for the first pass to go through LM Studio, so the model is the one
from the Sep 29 pass: `qwen/qwen3.5-9b` (Q4_K_M GGUF, tool use + vision) on RobertsPC over LM Link, served by
LM Studio on the Mac at `localhost:1234`. The rig is the Sep 29 rig copied unchanged except for two runner changes
described under "How the pass was run": one `roaddraft-mcp` per probe over stdio, all 78 tools as function tools,
the server's `instructions` as the system prompt, the same task text and report request, no shell, renders
replaced by a note (text-only, as for every open-model run). Context 65,536; the schema costs 21,844 prompt tokens
on this tokenizer. Engine at `8f2694d`. Scoring is `score_runs.py`, from the documents left on disk; the plots
beside them are `make_deliverables.py` (`runs/qwen3.5-9b/deliverables/`, `OVERVIEW.png` for the grid).

**0 of 6.** The same model scored 8 of 9 on the first-tier find-probes and 3 of 8 on the drafting-probes a week ago.
Each of the six fails on the thing it was built to measure, and nothing else: the far side of a sheet set, a
fifteen-item loop, text over linework, a mirrored centre, a fix made by relayering instead of redrawing, and the
last leg of a bearing-and-distance description.

| probe | Qwen3.5-9B | what the document on disk shows | calls / faults | turns | min | stop |
|---|---|---|---|---|---|---|
| sheet-set-callouts | **FAIL** | 9 of 15 edges aimed: the left edge, left shoulder and centerline on every sheet, both right-side callouts on left-side pieces on every sheet; `sheet_number` reads `C-101`, not `1 of 3` | 47 / 0 | 21 | 10 | answered |
| station-callouts | **FAIL** | 2 of 15 stations have a leader on them and both read the wrong station; 21 placed, 16 deleted, 4 left | 54 / 1 | 55 | 40 | answered |
| clean-callouts | **FAIL** | all three aimed and inside the border; `EDGE OF PAVEMENT` sits on the roadway linework at (4.98, 7.31) in | 25 / 3 | 26 | 11 | answered |
| draft-intersection-corner | **FAIL** | nothing drawn: an arc at the mirrored centre, modified, deleted; the right centre reached in thought as the budget ran out | 12 / 0 | 12 | 64 | budget |
| draft-fix-the-drawing | **FAIL** | the shoulder piece relayered (right); the 11 ft piece relayered to the shoulder layer instead of redrawn at 12 ft; the callout deleted, then two new ones added | 12 / 0 | 13 | 10 | answered |
| draft-roadway-sheets | **FAIL** | the sheet half is right; ELM-AVE ends 130 ft from where it was described, and the shoulder edges sit at 21 ft, not 16 | 33 / 4 | 34 | 23 | answered |
| **total** | **0 / 6** | | **183 / 8** | 161 | 159 | |

Tokens for the six: 5.06 M prompt, 134 k completion of which 116 k reasoning. Wall clock 2 h 39 min for the pass
that ran clean, plus about an hour on the two launches that did not (below).

## Findings

1. **The second tier separates where the first did not.** A week ago this model aimed every first-tier callout by
   name at 0.00 ft. Here it still aims well: 9 of 15 edges on the sheet set, all three on clean-callouts, and the
   two station callouts that reached a station landed at 0.00 ft. What it cannot do is the rest of the job:
   the far side of the road, the eleventh of fifteen near-identical calls, the paper around the text. The proposal
   named these gaps before any model ran; the run confirms them one for one.

2. **sheet-set-callouts: the right side of the road never got a callout, on any sheet.** Each sheet got five
   callouts with the right five texts, and the three centerlines are named `SR-100` with a leader on the
   centerline. But both `EDGE OF PAVEMENT` callouts on a sheet point at two pieces of the *left* edge (a tangent
   and an arc of the -12 ft offset), and both `EDGE OF SHOULDER` callouts at two pieces of the left shoulder; the
   +12 and +20 offsets have nothing on them. The pattern is identical on C-101, C-102 and C-103: it searched by
   layer, took the first two pieces, and never asked which side. The report claims targets at "-12' (L), +12' (R),
   -20' (L), +20' (R)" on every sheet. The title blocks carry the project, title and `1" = 50'` with the probe's
   spaces, but `sheet_number` is `C-101` with `total_sheets` 3, where the prompt says "1 of 3": the sheet's name
   where its number in the set was asked for. The check wants `1` or `1 of 3`; whether a sheet name should pass is
   Robert's call, as the `1"=50'` whitespace was on Sep 29. It would still fail on the right side.
   The engine warned twice that a new callout's text overlapped an earlier one; both warnings were ignored.

3. **station-callouts: fifteen near-identical calls, and the loop ate itself.** 21 `place_callout`, then
   `delete_entities` seven times removing 16 of them, in a place-check-delete-replace cycle that lasted 55 turns
   and 40 minutes (27 k reasoning tokens). The document ends with four callouts: `14+00` with its leader on 13+00,
   `24+00` on 19+00, `12+00` 40 ft from 11+00 and `10+00` 64 ft from it. The first attempt at this probe, cut off
   by the engine at turn 52, had done the same (16 placed, 15 deleted, one left). The one fault is instructive:
   `target_anchor: "11+00@0"`, a notation of its own invention, rejected with a hint; it then went to
   `station_to_xy` + `model_to_sheet` + `position`, which works, and drifted anyway. Its report narrows the task to
   four stations "that fall within the viewport's visible range" and calls it complete.

4. **clean-callouts: the aim is right and the paper is wrong.** `SR-100` on the centerline, `EDGE OF PAVEMENT` on
   the left edge, `EDGE OF SHOULDER` on the right shoulder, all inside the drawing area, and the text of the
   second sits across the roadway band, 0.05 in being the air the check wants. It called `render_sheet` once, got
   the text-only note this rig returns, and answered. A vision run would be the fair test of this probe for this
   model, and this rig does not give one by design; the finding here is that reasoning about the paper from
   coordinates alone did not get it clear of a 0.8 in band. Three faults on the way, all teaching errors (a
   `visible_on` on the wrong space, `draw_alignment` on a referenced design, `point_on_entity` with a viewport but
   no sheet), and a report that says "No errors or warnings were reported".

5. **draft-intersection-corner: the sign flip, with a budget.** Twelve calls in 64 minutes, because four turns ran
   10 to 16 minutes of thinking each (56 k reasoning tokens, the most of the six). It found the lines and the three
   existing returns, then drew the arc centred at [5082, 4906]: east sign right, north sign flipped, the southeast
   corner's centre. It moved the centre to [5094, 4906], deleted the arc, and was still reading entity lists when
   the budget stopped it; its last thinking has the right centre, [5082, 5094], and the right tangent points. The
   fixture is untouched. This is the family of the Sep 29 building failure (a mirrored side), now on a problem
   with no trigonometry in it.

6. **draft-fix-the-drawing: one of three fixes, and additions where restraint was asked for.** It found both
   mislayered pieces at once (`find_entities` by layer with `detail: full`, reading the anchor records), moved the
   shoulder piece back to V-ROAD-SHLD, which is the one correct fix, and moved the hand-drawn 11 ft piece to
   V-ROAD-SHLD too, reasoning that a line "with no alignment anchor" belongs off the pavement layer. The right
   edge of pavement now has a gap over the piece's run (49 of 189 check points with no V-ROAD-EOP linework within
   0.5 ft, the worst 24 ft from any) and the shoulder layer has an 11 ft line on it. The mislabelled callout it
   deleted whole, text, leader and arrowhead, which the check accepts as a fix; then it placed two new callouts in
   model space, `EDGE OF PAVEMENT` on the left edge and `RIGHT PAVEMENT EDGE` on the right, the second in wording
   the drawing does not use. "Change nothing else" was not honoured. The check does not fail the additions, since
   it judges the fixture's entities and not the model's extras; worth a second look if restraint is the point.

7. **draft-roadway-sheets: the sheet is right and the roadway is not.** Taken on its own, C-101 passes every
   sheet item: ANSI D, a viewport at exactly 1" = 100' whose paper box (2.5, 0.8, 32.5, 20.8) in lies inside the
   border, every point of the alignment it drew and both shoulder ends visible through it, title block `ELM AVE` /
   `ROADWAY PLAN` / `1" = 100'`. It took seven `modify_viewport` calls and two extra viewports to get there, with
   `get_extents` and `get_sheet_state` between them, which is the sheet-fitting loop a drafter runs. The roadway
   fails twice over. The hand arithmetic: PI-1 is 0.85 ft off (a slip in cos 100°), PI-2 carries it, and the last
   leg runs 710 ft at azimuth 79° instead of 600 ft at 85°, so the end is 130 ft from where it was described. And
   the offsets: edges of pavement at ±11 (right, for 11 ft lanes), a second pair at ±16 on V-ROAD-EOP, and the
   shoulder edges at ±21 on V-ROAD-SHLD, where 11 + 5 = 16 is the outside edge of a 5 ft shoulder; the 5 ft was
   added twice, the width-vs-offset trap in its shoulder form. The first `create_alignment` had no radii on the
   interior PIs and was refused with a hint; the second was accepted. The COGO gap decides this probe, as the
   proposal said it would; the sheet part, which was the new thing, this model can do.

8. **Report against disk, again.** Three of six final answers came back with empty `content` and the report in
   `reasoning_content` (clean-callouts, draft-roadway-sheets, and draft-intersection-corner's was never written).
   Where there is a report it diverges from the document: right-side targets that do not exist, "No errors" over
   four faults, "task complete" over 4 of 15. Nothing here is scored from a report.

9. **Turns are cheap and the cap was the wrong bound.** On Sep 29 this model's thinking turns ran 3 to 10 minutes;
   here most turns took 10 to 60 seconds, and the first attempt at sheet-set-callouts hit the Ollama rig's
   60-turn cap after 24 minutes, under half its budget, mid-revision. The cap is 120 in this rig, the 60-minute
   budget is the bound, and the four thinking-heavy turns of the corner probe show the budget still matters.

## How the pass was run

Three launches; the first two were ended by the infrastructure, not by the probes, and are kept under
`runs/qwen3.5-9b/_attempt1/` and `_attempt2/` (trace, project, transcript, report) for the record. Nothing in the
table above comes from them.

- **Attempt 1.** sheet-set-callouts ran 60 turns in 24 minutes and stopped on the turn cap, with 23 callouts
  across the three sheets and every edge covered but the right shoulder on C-101, which it had deleted in its
  revision pass. At turn 52 of station-callouts LM Studio returned `{"error":"terminated"}`, then `fetch failed`,
  and then reloaded the model on its own at the model's default settings: context 16,384, four parallel slots,
  a one-hour TTL. The 22 k-token schema no longer fit, and the remaining four probes each failed with
  `exceed_context_size_error` in under six seconds. `lms ps` showed the change; nothing in the run log said why.
- **Attempt 2.** Relaunched after reloading at 65,536. Fourteen calls in, `LM Link client transport disposed`: the
  link to RobertsPC dropped, then the server refused connections. The Mac was being rebooted. RobertsPC kept the
  model loaded at 65,536 through it; the Mac side needed `lms server start`.
- **Attempt 3** is the pass above, launched 13:44, finished 16:23.

The runner's two changes, documented in its docstring: `MAX_TURNS` 120 (finding 9), and two guards so a pass
survives LM Studio rather than losing the probes after an incident: a 400 carrying `exceed_context_size_error`,
`fetch failed`, `terminated` or `LM Link client transport disposed` reloads the model through `lms` at 65,536
and retries the same request, and a refused connection waits up to 15 minutes for the server, checks
`loaded_context_length` on `/api/v0/models`, and reloads if it is short. Neither guard fired during attempt 3.
`setup_runs.py`, `score_runs.py` and `make_deliverables.py` are the Sep 29 scripts unchanged; the six probes come
from `tasks.PROBES` with no rig change, as the proposal said they would.

## Caveats

- n = 1, one model, one quantisation, text-only. The clean-callouts result in particular is a text-only result for a
  vision model.
- Every probe hands the model the same 78 tools and the same `instructions`; nothing was tuned for the second tier.
- Two check-strictness questions for Robert, both of the Sep 29 `1"=50'` kind: `sheet_number` = `C-101` against
  `1 of 3` (finding 2), and whether draft-fix-the-drawing should fail additions (finding 6). Neither changes a
  verdict here.
- draft-intersection-corner was stopped by the 60-minute budget with the right geometry in its thinking. A longer
  budget might change that one; the fixture would still need the arc drawn and both curbs trimmed.

## What next

The six do what they were built for: a model that saturates the find-probes gets none of them, and each miss is
on the named gap. The ceiling is unmeasured. Fable 5.1 and Haiku 4.5 through the shell bridge would say whether
the set is hard or merely hard for a 9B model, and n = 3 on whichever probes turn out to be close.

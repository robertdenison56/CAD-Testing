# 2026-10-18 — gpt-oss-20b at k = 3 again, with its thinking sent back (`--send-reasoning`)

The gpt-oss-20b row of `2026-10-17-k3` (7.1%) ran without the harmony format's analysis channel: the runner kept a
tool-call turn's thinking in the transcript and sent only the call back, so from the second turn on the model drafted
without the reasoning behind its own earlier calls. `727fb7f` added `--send-reasoning` to the openai backend (the
turn's thinking goes back as the message's `reasoning`, which vLLM v0.31.0 renders as the analysis channel), and this
folder is the same row run again with it: same endpoint (`823ffmdxxfz2v2`, A40, vLLM v0.31.0, `openai` +
`openai_gptoss` parsers, the model's default sampling and reasoning effort), same budgets (120 turns, 30 minutes a
probe), same probe set, the worktree pinned at `727fb7f` (engine and tool surface as at `e7178a2`: tools
`sha256:60eeeb21`, instructions `sha256:4dff2849`). Its own folder because the board makes one row of a model per
folder; the board ranks this row and lists the Oct 17 one as superseded.

Robert: "do number 1" (Oct 18, the review's next step: commit `--send-reasoning`, rerun gpt-oss-20b at k = 3).

## Result (Oct 19, 01:08 to 01:53 UTC): 6, 5, 2 of 33, 13.1% [4.0, 24.2], still last

| | 2026-10-17-k3 (no thinking sent back) | 2026-10-18-gpt-oss-k3 (`--send-reasoning`) |
|---|---|---|
| r1, r2, r3 | 0, 3, 4 | **6, 5, 2** |
| pass rate [95% CI] | 7.1% [1.0, 14.1] | **13.1% [4.0, 24.2]**, rank 9 of the board's 9 |
| T1 / T2 / T3 | 6/51, 0/18, 1/30 | 11/51, 0/18, 2/30 |
| hard-fail | 85% (28/33) | 76% (25/33) |
| episodes with no tool call at all | 67 of 99 | **77 of 99** |
| episodes that called tools | 32 | 22 |
| of those, passed | 7 (22%) | **13 (59%)** |
| of those, ended on vLLM's harmony parser | 17 | **0** |
| invalid calls | 21.8% | 19.4% |
| mean episode | 102 s, 3.7 turns | 72 s, 2.9 turns |
| bill | $1.28 | about $1 (worker time ~50 min at $1.22/h; Runpod had not posted the Oct 19 UTC record when this was written) |

The intervals overlap, so the two rows are not separated as pass rates. What did change is inside the episodes:

- *The flag fixed what it could reach.* Sent its own thinking back, gpt-oss-20b no longer breaks harmony's tool
  header (17 parser rejections, `unexpected tokens remaining in message header` / `could not decode header`, to none)
  and passes more than half the episodes in which it works through the tools: `sta-offset-c101-paper` every time,
  `shoulder-c101`, `edge-c102-paper` and `stationing` twice, `edge-c102`, `centerline-c103`, `title-blocks`,
  `draft-building` once, `equation-data` never (once on Oct 17).
- *What it cannot reach decides the row.* 77 of 99 episodes ended on the first turn with no tool call: the model
  plans the calls in its thinking ("Let's produce calls: find_entities ... place_callout ..."), then writes them out
  as its report, with entity ids it never looked up, and stops. `--send-reasoning` only acts after a tool-call turn,
  so these episodes ran exactly as before (67 of 99 on Oct 17; the difference is sampling). 79 of the 86 failed
  episodes' reports say the task was done.
- *Not the rig.* vLLM v0.31.0 builds the canonical harmony preamble for a chat request
  (`renderers/online_renderer.py` `_make_request_with_harmony`, `parser/harmony_utils.py` `build_harmony_preamble`):
  the leading system message, the server's instructions, becomes the developer message's instructions beside the 103
  function tools, the system message carries the reasoning effort and the date. The same first-turn behaviour is the
  September finding on gpt-oss:120b through Ollama cloud (`2026-09-24-ollama`, in the history at `727fb7f`), another
  server and another rig. The only setting left that bears on it is the reasoning effort (medium by default; `high`
  through `extra_body`), which would be a different row and is Robert's call.

**Rig.** `benchmarks/runpod/runpod_campaign.py smoke gpt-oss-20b`, then `k3 gpt-oss-20b`: three processes on one
worker. The models.json entry gained `send_reasoning: true` and `campaign: "2026-10-18-gpt-oss-k3"`, and the script
reads both (`--send-reasoning` on every run command, the folder for smoke, k3, rerun and score); `PIN` moved to
`727fb7f`, whose `src/` differs from `e7178a2` only in the runner (the flag, off by default) and the board rules. Every
`run.json` records `send_reasoning: true`; the model cards now show it, with the sampling, as "request settings". The
smoke probe (`edge-c102`, 1 turn, no tool call, as on Oct 17) runs as `-r1`. No episode ended on the infrastructure;
nothing was rerun. The endpoint was parked at max workers 0 afterwards.

**Per-probe marks**, Oct 17 then Oct 18 (P pass, · fail):

| probe | 2026-10-17-k3 | 2026-10-18-gpt-oss-k3 |
|---|---|---|
| edge-c102 | · · · | · P · |
| edge-curve-c102 | · P P | · · · |
| shoulder-c101 | · P · | P P · |
| centerline-c103 | · · · | · · P |
| title-blocks | · · · | P · · |
| edge-c102-paper | · P P | P P · |
| sta-offset-c101-paper | · · P | P P P |
| draft-building | · · · | P · · |
| stationing | · · · | P P · |
| equation-data | · · P | · · · |
| the other 23 probes | never | never |

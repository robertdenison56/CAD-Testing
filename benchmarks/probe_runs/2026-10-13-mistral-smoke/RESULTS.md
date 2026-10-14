# 2026-10-13 — Mistral 7B Instruct v0.3 through LM Studio: one smoke probe, and why there is no run

Robert asked for Mistral through LM Studio after the four-model k = 3 campaign (`2026-10-12-k3`). One probe was
run first, because the Oct 7 rig had skipped this model for two reasons that still hold: LM Studio lists
`mistralai/mistral-7b-instruct-v0.3` without the `tool_use` capability, and its context is 32,768 tokens where the
103-tool schema alone is 129,727 characters (about 29,000 tokens by the Oct 7 measurement scaled, 32,000 to 37,000
at 3.5 to 4 characters a token).

**Rig.** `python -m roaddraft.runners run --backend openai --model mistralai/mistral-7b-instruct-v0.3
--lms-context 32768 --budget 15 edge-c102`, LM Studio on RobertsPC over LM Link, Q4_K_M, Gemma unloaded first.
The runner sent the tools as function tools, as it does for every model.

## Result: 0 of 1, with a report claiming the work was done

| | |
|---|---|
| stop | answered, after 1 turn, 10.8 s |
| input tokens | **1,284**: the system instructions and the task only. The tool schema never reached the model: LM Studio accepted the `tools` parameter and rendered none of it, because the model's chat template has no tool slot |
| tool calls | 0 |
| context | LM Studio JIT-loaded the model at 16,384, not the 32,768 the guard asked for; moot, since nothing but the 1,284 tokens was ever sent |
| the document | unchanged; `edge-c102` fails: no callout |
| the report | "I utilized the provided functions to find and point at the edge of pavement ... find_entities {anchor: {kind: 'offset', offset: [-12, 12]}, visible_on: 'C-102'} ... place_callout (target_entity was the ID returned from the previous command)" |

The report names the right two calls in the right order with the right arguments, copied from the server's
instructions, and made neither. This is the fabricated-completion failure the Sep 24 gpt-oss run documented,
in its purest form: a model that cannot call tools describing the calls it would have made as if it had.

**No k = 3 run.** 99 episodes of this would score 0 of 33 three times and measure nothing about drafting; the
row would say only that LM Studio strips tools from a model without a tool template. Two things would have to
change for Mistral to be benchmarked here: a build of the model whose template carries tools (v0.3 has native
function calling in its own format; LM Studio's GGUF template does not expose it), and a context that holds the
schema, which 32k does not. The second rules it out on this tool surface regardless of the first.

    python -m roaddraft.runners run --backend openai --model mistralai/mistral-7b-instruct-v0.3 --base-url http://localhost:1234/v1 \
        --lms-context 32768 --out benchmarks/probe_runs/2026-10-13-mistral-smoke --label mistral --budget 15 edge-c102
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-13-mistral-smoke/runs/mistral

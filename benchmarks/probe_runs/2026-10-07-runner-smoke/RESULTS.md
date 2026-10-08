# 2026-10-07 — the native runner's first live runs (smoke, not a benchmark)

`roaddraft.runners` was built on Oct 7 2026: one native MCP client with three
backends (`anthropic`, `claude-code`, `openai`). These two folders are the
first real models through it, one probe each, to prove the path from the
server over stdio to the scored document; they are not leaderboard rows.

| Label | Model | Backend | Probe | Result |
|---|---|---|---|---|
| qwen | Qwen3.5-9B (LM Studio, 65k context, on RobertsPC over LM Link) | openai | edge-c102 | **PASS**, 4 calls, 0 faults, 195 s; leader on DESIGN:AR-003 at 0.00 ft |
| llama8b | Llama 3.1 8B Instruct (LM Studio, 32k context) | openai | edge-c102 | no calls: LM Studio answered 400 after 335 s, "the model produced output that does not match the expected peg-native format" |

Qwen went straight to the answer: `get_document_state`, `list_sheets`,
`find_entities` on V-ROAD-EOP visible on C-102, `place_callout` with the
entity as the target. Its turns took 19, 31, 67 and 78 s. Llama's tool call
could not be parsed by LM Studio; that 400 is now retried by re-sampling
(`RESAMPLE_MARKERS` in `runners/openai_compat.py`), which this run predates.

The `claude-code` backend was driven through the desktop app's bundled CLI,
which is not signed in: it accepted every flag, started the probe's server
from the generated MCP config and reported it connected, then stopped at
"Not logged in", recorded in `run.json`. That folder is not kept. No
`anthropic` run has been made: no API key.

    python -m roaddraft.runners run --backend openai --model qwen/qwen3.5-9b --lms-context 65536 \
        --out benchmarks/probe_runs/2026-10-07-runner-smoke --label qwen --budget 9 --max-turns 30 edge-c102
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-07-runner-smoke/runs/qwen

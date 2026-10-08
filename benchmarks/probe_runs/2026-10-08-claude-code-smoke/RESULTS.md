# 2026-10-08 — the `claude-code` backend's first live run (smoke, not a benchmark)

The Oct 7 smoke run drove the `claude-code` backend through the desktop app's bundled CLI, which stopped at
"Not logged in". Robert installed a standalone Claude Code CLI (2.1.295, `~/.local/bin/claude`) and signed it in
on his claude.ai account, so this run is on the subscription, with no API key.

| Label | Model | Backend | Probe | Result |
|---|---|---|---|---|
| haiku | Claude Haiku 4.5 (`claude-haiku-4-5`) | claude-code | edge-c102 | **PASS**, 7 calls, 0 faults, 27 s; leader on DESIGN:LN-005 at 0.00 ft |

Haiku called `get_document_state`, `list_sheets`, `list_references`, `get_sheet_state`, `find_entities`,
`place_callout`, then `render_sheet` to check the result. The server connected through the generated MCP config
(`mcp_servers: {"roaddraft": "connected"}` in run.json).

The first try did not reach the model: the backend wrote the MCP config path relative to the repo, as `--out` was
given, and ran `claude` from the probe's `project/` folder, so the CLI looked for
`project/benchmarks/probe_runs/.../mcp.json`. The config path is now resolved before it is handed over
(`runners/claude_code.py`), with a regression test that runs from a relative folder.

Two costs are recorded and they differ: `cost_usd` $0.0675 is the runner's list-price estimate, `claude_cost_usd`
$0.0920 is the CLI's own. The gap is the 32,668 cache-creation tokens: the CLI writes its prompt cache with a
one-hour lifetime (2x input price) and the estimate prices cache writes at the five-minute rate (1.25x). Both are
list-price figures; the subscription is not billed per token.

    python -m roaddraft.runners run --backend claude-code --model claude-haiku-4-5 \
        --out benchmarks/probe_runs/2026-10-08-claude-code-smoke --label haiku --budget 10 --max-budget-usd 2 edge-c102
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-08-claude-code-smoke/runs/haiku

The `anthropic` backend (Messages API) is still unrun: no API key, and the research plan keeps Claude on the
`claude-code` backend until one is warranted.

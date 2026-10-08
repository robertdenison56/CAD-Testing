"""One native MCP runner for every vendor (research plan, Phase A).

A model under test touches the app only through MCP, and every model should
see the same tools, the same words and the same budgets, so the rows of the
leaderboard are comparable. The runner is that one client: it sets up a
fresh project per probe, starts ``roaddraft-mcp`` on it with autosave and a
trace, hands the server's tools and instructions to the model, runs the
tool-calling loop to the model's final report, and leaves the run folder the
scorers read -- the same layout the hand-built rigs under
``benchmarks/probe_runs`` left.

Backends are the only vendor-specific part:

- ``anthropic``: the Messages API over HTTP (an API key, billed per token).
- ``claude-code``: Claude Code in headless mode, on a subscription; the CLI
  starts the server from an MCP config and the model calls the tools natively.
- ``openai``: any OpenAI-compatible chat-completions endpoint -- LM Studio,
  Ollama, vLLM -- streamed, with the LM Studio rigs' guards: a cap on the
  calls one turn may make, a per-turn time limit, a stop when the
  conversation outgrows the loaded context, the type-list rewrite for
  templates that refuse it, and the reload guard when asked for.

Every backend that reads results through ``McpServer`` sees a tool result cut
to ``RESULT_CAP`` characters.

    python -m roaddraft.runners run --backend anthropic --model claude-haiku-4-5 \\
        --out benchmarks/probe_runs/2026-10-07-native --label haiku --tag tier2
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-07-native/runs/haiku
"""
from roaddraft.runners.core import (BACKENDS, Backend, Episode, McpServer, Options,
                                    Outcome, ToolResult, estimate_cost, run_probe,
                                    setup_probe)

__all__ = ["BACKENDS", "Backend", "Episode", "McpServer", "Options", "Outcome",
           "ToolResult", "estimate_cost", "run_probe", "setup_probe"]

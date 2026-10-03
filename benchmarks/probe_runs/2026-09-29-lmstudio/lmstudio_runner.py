"""lmstudio_runner.py [--budget MIN] LABEL MODEL [PROBE ...] -> drive probes with a model served by LM Studio.

The Ollama rig's runner (2026-09-24-ollama/ollama_runner.py) with the model
call swapped for LM Studio's OpenAI-compatible chat-completions API on
http://localhost:1234/v1. Everything else is the same by design: one
`roaddraft-mcp` per probe over stdio (the command in the probe folder's
server.json, written by setup_runs.py), its tools handed to the model as
function tools, its `instructions` as the system prompt, the same task text
and report request. The model has no shell and nothing else -- the tool
surface is the whole world, which is the T1 no-calculator rule by construction.

Differences that LM Studio forces:
- Tool results are `role: tool` messages keyed by `tool_call_id`, and tool
  arguments arrive as a JSON string.
- The model's thinking comes back as `reasoning_content`. It is kept in
  transcript.json but NOT sent back on the next turn: the 78-tool schema
  already costs 21.8k tokens per request, and a local model's context is the
  scarce resource. (Qwen's own chat template drops old reasoning too.)
- Render images are replaced by a note, as for gpt-oss, even though Qwen3.5 is
  a vision model: text-only keeps the runs comparable.

Before running: `lms server start`, and load the model with a context that
holds the tool schema plus a conversation -- `lms load MODEL -c 65536`; the
16384 default is too small for the schema alone.

`--budget MIN` is a per-probe wall-clock budget, checked between turns: a
probe past it stops with `stop: "budget"` and is scored from whatever it left
on disk. Added mid-pass on 2026-09-29 after draft-turn-lane ran 63 minutes for
21 tool calls (the 60-turn cap alone bounds nothing when a turn takes ten
minutes of thinking); the first 13 probes of that pass ran without it, and
none of them needed more than 12 minutes.

Per probe it writes transcript.json (every message, thinking included, and
the seconds each turn took) and report.txt (the model's final answer); the
server writes trace.jsonl. Score
with score_runs.py LABEL, exactly as for the Claude and Ollama runs.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from roaddraft.probes import tasks

ROOT = Path(__file__).parent
LMSTUDIO = "http://localhost:1234/v1/chat/completions"
MAX_TURNS = 60

T2_REPORT = """When finished, reply briefly with:
1. What you placed, in which space, and what it points at.
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages."""
T1_REPORT = """When finished, reply briefly with:
1. What you created and drew (names, layers, key coordinates).
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages. If you had to compute coordinates yourself, show the arithmetic."""
RULES = """Do one drafting task in a headless CAD engine called RoadDraft, using the tools you have been given. They are your ENTIRE tool surface.

Rules:
- Every change to the drawing must go through a tool call.
- The document is already open and saves itself after each command. Do not save it under another name.
- Nobody can answer questions. Work until you judge the task done, then stop and give your report.{extra}

THE TASK:
{task}

{report}"""


class Server:
    def __init__(self, folder: Path):
        cmd = json.loads((folder / "server.json").read_text())["cmd"]
        self.log = (folder / "server.log").open("a")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.log, text=True, bufsize=1,
                                     cwd=str(folder / "project"))
        self.n = 0
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "lmstudio-runner", "version": "1"}})
        self.instructions = init["result"].get("instructions", "")
        self.notify("notifications/initialized")
        self.tools = self.rpc("tools/list")["result"]["tools"]

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method, params=None):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("the MCP server closed its output")
            reply = json.loads(line)
            if reply.get("id") == self.n:
                return reply

    def call(self, name, arguments) -> str:
        reply = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in reply:
            return f"[protocol error] {reply['error'].get('message')}"
        result = reply["result"]
        parts = ["[tool error]"] if result.get("isError") else []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block["text"])
            else:
                # text-only on purpose (see the module docstring); the text
                # block beside the image already carries the file path
                parts.append(f"[{block.get('type')} content omitted: this run is text-only]")
        return "\n".join(parts)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def chat(model, messages, tools):
    body = json.dumps({"model": model, "messages": messages, "tools": tools,
                       "stream": False}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(LMSTUDIO, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1800) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            text = ex.read().decode(errors="replace")
            if ex.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            # 400 is what LM Studio returns for a context overflow: not retryable
            raise RuntimeError(f"lmstudio HTTP {ex.code}: {text[:300]}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < 3:
                time.sleep(15)
                continue
            raise


def parse_args(raw):
    if isinstance(raw, dict):
        return raw
    if not raw or not str(raw).strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparsed": raw}


def run(label, model, probe, budget=None):
    folder = ROOT / "runs" / label / probe.id
    if (folder / "report.txt").exists():
        print(f"skip {probe.id} (already ran)")
        return
    server = Server(folder)
    tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                               "parameters": t["inputSchema"]}} for t in server.tools]
    draft = "draft" in probe.tags
    extra = ("\n- You have no calculator or code execution. Any arithmetic you need, do yourself."
             if draft else "")
    task = RULES.format(extra=extra, task=probe.prompt, report=T1_REPORT if draft else T2_REPORT)
    messages = [{"role": "system", "content": server.instructions},
                {"role": "user", "content": task}]
    log = list(messages)          # what transcript.json keeps: messages + thinking
    started = time.time()
    usage = {"prompt": 0, "completion": 0, "reasoning": 0}
    final, stop, unparsed_markup = "", "max_turns", False
    try:
        for _turn in range(MAX_TURNS):
            if budget and time.time() - started > budget:
                stop = "budget"
                break
            t0 = time.time()
            reply = chat(model, messages, tools)
            u = reply.get("usage") or {}
            usage["prompt"] += u.get("prompt_tokens", 0)
            usage["completion"] += u.get("completion_tokens", 0)
            usage["reasoning"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            choice = reply["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            calls = msg.get("tool_calls") or []
            sent = {"role": "assistant", "content": content}
            if calls:
                sent["tool_calls"] = calls
            messages.append(sent)
            kept = dict(sent)
            kept["finish_reason"] = choice.get("finish_reason")
            kept["seconds"] = round(time.time() - t0, 1)
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                kept["reasoning"] = reasoning
            log.append(kept)
            if not calls:
                final = content
                stop = "length" if choice.get("finish_reason") == "length" else "answered"
                unparsed_markup = "<tool_call>" in content
                break
            for c in calls:
                fn = c["function"]
                out = server.call(fn["name"], parse_args(fn.get("arguments")))
                tool_msg = {"role": "tool", "tool_call_id": c.get("id"), "name": fn["name"],
                            "content": out}
                messages.append(tool_msg)
                log.append(tool_msg)
    except Exception as ex:
        stop = f"error: {ex}"
    finally:
        server.close()
    meta = {"model": model, "probe": probe.id, "stop": stop,
            "turns": sum(m["role"] == "assistant" for m in messages),
            "seconds": round(time.time() - started, 1), "tokens": usage}
    if unparsed_markup:
        meta["unparsed_tool_markup"] = True
    (folder / "transcript.json").write_text(json.dumps({"meta": meta, "messages": log}, indent=1))
    (folder / "report.txt").write_text(final or f"(no final answer: {stop})")
    print(json.dumps(meta), flush=True)


def main(argv):
    budget = None
    if argv and argv[0] == "--budget":
        budget = float(argv[1]) * 60
        argv = argv[2:]
    label, model, only = argv[0], argv[1], set(argv[2:])
    for probe in tasks.PROBES:
        if only and probe.id not in only:
            continue
        run(label, model, probe, budget)


if __name__ == "__main__":
    main(sys.argv[1:])

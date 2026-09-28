"""ollama_runner.py LABEL MODEL [PROBE ...] -> drive probes with an Ollama model.

A minimal native MCP client: one `roaddraft-mcp` per probe over stdio (the
command in the probe folder's server.json, written by setup_runs.py), its
tools handed to the model as Ollama function tools, its `instructions` as the
system prompt. The model has no shell and nothing else -- the tool surface is
the whole world, which is the T1 no-calculator rule by construction.

Per probe it writes transcript.json (every message) and report.txt (the
model's final answer); the server writes trace.jsonl. Score with
score_runs.py LABEL, exactly as for the Claude runs.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from roaddraft.probes import tasks

ROOT = Path(__file__).parent
OLLAMA = "http://localhost:11434/api/chat"
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
                                       "clientInfo": {"name": "ollama-runner", "version": "1"}})
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
                # the models under test are text-only; the text block beside
                # the image already carries the file path
                parts.append(f"[{block.get('type')} content omitted: this model cannot view images]")
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
            req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            text = ex.read().decode(errors="replace")
            if ex.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"ollama HTTP {ex.code}: {text[:300]}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < 3:
                time.sleep(15)
                continue
            raise


def run(label, model, probe):
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
    started, usage, final, stop = time.time(), {"prompt": 0, "eval": 0}, "", "max_turns"
    try:
        for _turn in range(MAX_TURNS):
            reply = chat(model, messages, tools)
            usage["prompt"] += reply.get("prompt_eval_count", 0)
            usage["eval"] += reply.get("eval_count", 0)
            msg = reply["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                final, stop = msg.get("content", ""), "answered"
                break
            for c in calls:
                fn = c["function"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_unparsed": args}
                out = server.call(fn["name"], args)
                messages.append({"role": "tool", "tool_name": fn["name"], "content": out})
    except Exception as ex:
        stop = f"error: {ex}"
    finally:
        server.close()
    meta = {"model": model, "probe": probe.id, "stop": stop, "turns": sum(m["role"] == "assistant" for m in messages),
            "seconds": round(time.time() - started, 1), "tokens": usage}
    (folder / "transcript.json").write_text(json.dumps({"meta": meta, "messages": messages}, indent=1))
    (folder / "report.txt").write_text(final or f"(no final answer: {stop})")
    print(json.dumps(meta))


def main(argv):
    label, model, only = argv[0], argv[1], set(argv[2:])
    for probe in tasks.PROBES:
        if only and probe.id not in only:
            continue
        run(label, model, probe)


if __name__ == "__main__":
    main(sys.argv[1:])

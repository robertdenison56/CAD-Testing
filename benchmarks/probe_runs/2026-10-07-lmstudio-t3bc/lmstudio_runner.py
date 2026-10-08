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

Two changes for the Tier-2 pass of 2026-10-04. MAX_TURNS is 120, not 60: these
probes have fifteen pieces each and the first attempt at sheet-set-callouts
hit 60 turns at 24 minutes, under half its budget, with the turns taking 25 s
each; the wall-clock budget is meant to be the bound, so the cap is raised
until it is not. And a context guard: when LM Studio's engine dies mid-pass,
LM Studio reloads the model on its own at the model's default 16k context,
which the 22k-token tool schema overflows, so every later request 400s with
exceed_context_size_error. That cost four probes in six seconds on the first
attempt. Now a 400 carrying one of RELOAD_MARKERS reloads the model through
`lms` at CONTEXT and retries the same request, and the probe goes on; and a
refused connection waits up to SERVER_WAIT for the server to return (the
second attempt lost its five remaining probes in 45 s each when LM Studio
went down ahead of a reboot), then checks the loaded context before retrying.

For the Tier-3 batch B and C pass of 2026-10-07 the task text is no longer
composed here: setup_runs.py writes `prompting.task_text(probe)` to the probe
folder's prompt.txt and the runner hands that file over as the user message,
so the words a local model saw are the words the trajectory recorder uses.
The text is the same as the 2026-10-04 runner's for every probe that is not a
draft-probe (none of batches B and C is). run_models.py loads each model in
turn and calls run() for each probe.

Two guards added mid-pass on 2026-10-08, after Qwen's fourth call on
l2-match-lines (get_model_state with include_references on the L-2 start)
returned 748,312 characters, a 467,928-token request that no reload can fit:
- A tool result longer than RESULT_CAP characters is cut to its first
  RESULT_CAP and says so. That is about the cap Claude Code's Bash tool puts
  on a command's output, which is what the shell-bridge runs saw. No result in
  any earlier LM Studio run (Sep 29, Oct 4, or the four probes of this pass
  that ran before it) came near it; the largest was 12,886 characters, so the
  cap changes nothing for them. Only the L-2 start answers that big.
- A 400 for exceeding the context reloads the model only when the loaded
  context is below CONTEXT (the Oct 4 failure). When it is already at CONTEXT,
  the conversation has outgrown it: the probe stops with `stop: "context"` and
  is scored from disk, instead of reloading three times for nothing.

And a third, before GLM-4.6V-Flash's pass the same morning: its first turn on
width-dims did not come back in the 1800 s the request was allowed, so the
probe ended with no call made. Streamed, the turn shows why: the model writes
one tool call after another without stopping for a result (get_document_state,
list_sheets, render_sheet, list_alignments, ... then place_text "C2" at
coordinates it had not read), about five chunks a second, until the context
would be full. LM Studio ignores `parallel_tool_calls: false`, and a stop
string on GLM's `<|observation|>` token does not end it. So the runner now
streams every turn and ends it when the model starts a call past CALL_CAP:
the first CALL_CAP calls run and their results go back, as for any turn.
Qwen3.5-9B made exactly one call in each of its 503 turns of this pass, and at
most four in any turn of the Sep 29 and Oct 4 passes, so the cap could not
have bound it and its results stand. A turn still gets TURN_LIMIT seconds,
the old request timeout; past it the probe stops with `stop: "turn_limit"`
and the partial turn is kept in transcript.json. A cut turn's usage is
estimated from its chunk count (LM Studio reports usage only at the end of a
stream); `cut_turns` in the meta counts them.

And a fourth, for Gemma-4-E4B: LM Studio refuses any request carrying the
tools with `NotImplemented: map: filter-mapping not implemented`, from the
model's chat template. Two schemas trip it, draw_offset and
annotate_stationing, whose array items say `"type": ["number", "string"]`.
When a model's template refuses the tools that way, run_models.py sets
REWRITE_TYPE_LISTS and the runner hands the model the same schemas with each
list-valued type written as the equivalent `anyOf` of single types; the
model's model.json says so. Models whose templates take the original (Qwen,
GLM) saw it unchanged.

Per probe it writes transcript.json (every message, thinking included, and
the seconds each turn took) and report.txt (the model's final answer); the
server writes trace.jsonl. Score
with score_runs.py LABEL, exactly as for the Claude and Ollama runs.
"""
import http.client
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from roaddraft.probes import tasks

ROOT = Path(__file__).parent
LMSTUDIO = "http://localhost:1234/v1/chat/completions"
MAX_TURNS = 120                       # see the docstring: the budget is the bound
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms")
CONTEXT = 65536                       # what the 78-tool schema plus a conversation needs
RELOAD_MARKERS = ("exceed_context_size_error", "fetch failed", "terminated",
                  "LM Link client transport disposed")
SERVER_WAIT = 15 * 60                 # how long to wait for LM Studio to come back
RESULT_CAP = 30000                    # characters of one tool result the model is shown
REWRITE_TYPE_LISTS = False            # set by run_models.py for a template that needs it
CALL_CAP = 4                          # tool calls run from one turn; a fifth ends the turn
TURN_LIMIT = 1800                     # seconds one turn may take (the old request timeout)
reloads = 0
truncated = 0


class ContextFull(Exception):
    """The request is bigger than the model's context, which is already at CONTEXT."""


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
        text = "\n".join(parts)
        if len(text) > RESULT_CAP:          # see the docstring: the L-2 start's whole-model reads
            global truncated
            truncated += 1
            text = (text[:RESULT_CAP] + f"\n[output truncated: the first {RESULT_CAP} of "
                    f"{len(text)} characters are shown]")
        return text

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def rewrite_type_lists(schema):
    """The same JSON Schema with every list-valued `type` as an `anyOf` of single types."""
    if isinstance(schema, dict):
        schema = {k: rewrite_type_lists(v) for k, v in schema.items()}
        if isinstance(schema.get("type"), list):
            schema["anyOf"] = [{"type": t} for t in schema.pop("type")]
        return schema
    if isinstance(schema, list):
        return [rewrite_type_lists(v) for v in schema]
    return schema


def tool_defs(server_tools):
    """The MCP tools as chat-completions function tools."""
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": rewrite_type_lists(t["inputSchema"]) if REWRITE_TYPE_LISTS else t["inputSchema"]}}
        for t in server_tools]


def reload_model(model):
    """Bring the model back at the context this rig needs (see the docstring)."""
    global reloads
    reloads += 1
    subprocess.run([LMS, "unload", model], capture_output=True, text=True)
    r = subprocess.run([LMS, "load", model, "--context-length", str(CONTEXT), "--parallel", "1",
                        "-y"], capture_output=True, text=True)
    print(f"reloaded {model} at context {CONTEXT}: rc={r.returncode}", flush=True)


def loaded_context(model):
    """The context the model is loaded at now, 0 if it is not loaded or the server is down."""
    try:
        with urllib.request.urlopen(LMSTUDIO.replace("/v1/chat/completions", "/api/v0/models"),
                                    timeout=10) as resp:
            models = json.loads(resp.read()).get("data", [])
    except Exception:
        return 0
    loaded = [m for m in models if m.get("id") == model and m.get("state") == "loaded"]
    return loaded[0].get("loaded_context_length", 0) if loaded else 0


def wait_for_server(model):
    """LM Studio's server is down (connection refused): wait for it, up to
    SERVER_WAIT, then make sure the model is loaded at CONTEXT. A restart of
    LM Studio on the Mac then costs the pass minutes, not the probe."""
    t0 = time.time()
    while time.time() - t0 < SERVER_WAIT:
        try:
            with urllib.request.urlopen(LMSTUDIO.replace("/v1/chat/completions", "/api/v0/models"),
                                        timeout=10) as resp:
                models = json.loads(resp.read()).get("data", [])
            loaded = [m for m in models if m.get("id") == model and m.get("state") == "loaded"]
            if not loaded or loaded[0].get("loaded_context_length", 0) < CONTEXT:
                reload_model(model)
            return
        except Exception:
            time.sleep(30)
    print(f"LM Studio did not come back within {SERVER_WAIT} s", flush=True)


def read_stream(resp, t0):
    """Assemble a streamed turn into the shape of a non-streamed reply, ending
    it at the start of a call past CALL_CAP or after TURN_LIMIT seconds (see
    the docstring)."""
    content, reasoning, calls, usage, finish, chunks = [], [], {}, {}, None, 0
    for raw in resp:
        line = raw.decode(errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        d = json.loads(data)
        if d.get("error"):
            raise RuntimeError(f"lmstudio stream error: {str(d['error'])[:300]}")
        if d.get("usage"):
            usage = d["usage"]
        for ch in d.get("choices") or []:
            delta = ch.get("delta") or {}
            chunks += 1
            content.append(delta.get("content") or "")
            reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            for tc in delta.get("tool_calls") or []:
                i = tc.get("index", len(calls))
                if i not in calls and len(calls) >= CALL_CAP:
                    finish = "call_cap"
                    break
                slot = calls.setdefault(i, {"id": None, "type": "function",
                                            "function": {"name": "", "arguments": ""}})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
            if finish == "call_cap":
                break
            finish = ch.get("finish_reason") or finish
        if finish == "call_cap":
            break
        if time.time() - t0 > TURN_LIMIT:
            finish = "turn_limit"
            break
    msg = {"role": "assistant", "content": "".join(content)}
    if "".join(reasoning):
        msg["reasoning_content"] = "".join(reasoning)
    if calls:
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
        for n, c in enumerate(msg["tool_calls"]):
            c["id"] = c["id"] or f"call_{int(t0)}_{n}"
    if not usage:
        usage = {"completion_tokens": chunks, "estimated": True}
    return {"choices": [{"message": msg, "finish_reason": finish}], "usage": usage}


def chat(model, messages, tools):
    body = json.dumps({"model": model, "messages": messages, "tools": tools, "stream": True,
                       "stream_options": {"include_usage": True}}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(LMSTUDIO, body, {"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=TURN_LIMIT) as resp:
                return read_stream(resp, t0)
        except urllib.error.HTTPError as ex:
            text = ex.read().decode(errors="replace")
            if (ex.code == 400 and "exceed" in text and "context" in text
                    and loaded_context(model) >= CONTEXT):
                raise ContextFull(text[:300])     # a reload cannot fit it (see the docstring)
            if ex.code == 400 and any(m in text for m in RELOAD_MARKERS) and attempt < 3:
                print(f"lmstudio 400, reloading the model: {text[:140]}", flush=True)
                reload_model(model)
                time.sleep(5)
                continue
            if ex.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            # 400 is what LM Studio returns for a context overflow: not retryable
            raise RuntimeError(f"lmstudio HTTP {ex.code}: {text[:300]}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError,
                http.client.HTTPException):
            if attempt < 3:
                wait_for_server(model)
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
    tools = tool_defs(server.tools)
    task = (folder / "prompt.txt").read_text()     # prompting.task_text, from setup_runs.py
    messages = [{"role": "system", "content": server.instructions},
                {"role": "user", "content": task}]
    log = list(messages)          # what transcript.json keeps: messages + thinking
    started = time.time()
    reloads_before, truncated_before, cut_turns = reloads, truncated, 0
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
            if choice.get("finish_reason") == "turn_limit":
                stop = "turn_limit"
                break
            cut_turns += choice.get("finish_reason") == "call_cap"
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
    except ContextFull as ex:
        stop = "context"
        print(f"context full: {ex}", flush=True)
    except Exception as ex:
        stop = f"error: {ex}"
    finally:
        server.close()
    meta = {"model": model, "probe": probe.id, "stop": stop,
            "turns": sum(m["role"] == "assistant" for m in messages),
            "seconds": round(time.time() - started, 1), "tokens": usage,
            "reloads": reloads - reloads_before, "truncated_results": truncated - truncated_before,
            "cut_turns": cut_turns}
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

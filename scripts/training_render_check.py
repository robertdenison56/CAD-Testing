"""The T1 smoke's render check, run without a GPU (training plan section 7:
"training text differs from what the server sends").

For sample conversations from ``results/training``, it renders each one the
way the trainer will (``transformers``' ``apply_chat_template`` with the 9B's
own tokenizer and template, then ``training_render.plan_segments`` and its
labels) and each request the harness would send before each assistant turn
the way the serving engine does (LM Studio's llama.cpp ``llama-server``,
``/apply-template`` and ``/tokenize``, on the stand-in GGUF of
``training_serving_stub.py``), and compares:

1. *trainer vs token script*: transformers' render of the whole conversation
   equals ``scripts/training_tokens.py``'s jinja2 render (the one calibrated
   against LM Studio's prompt counts);
2. *template engines*: for every request, the server's prompt equals
   transformers' render of the same messages with the generation prompt;
3. *context*: the server's prompt is a prefix of the training sequence that
   trains the turn (string), and its token ids are a prefix of that
   sequence's token ids;
4. *target*: the trained tokens of the turn are the tokens of the turn's
   completion tokenized alone (what the model is sampled to write), and they
   decode to exactly the completion;
5. *round trip*: the completion read back the way the server's Qwen3-Coder
   parser reads it gives the recorded calls and text.

Each at ``--thinking off`` (generation prompt ``<think>\\n\\n</think>\\n\\n``)
and ``on`` (``<think>\\n``, LM Studio's default for the 9B, the board rows).

    PYTHON -I scripts/training_render_check.py RESULTS/training --out DIR

PYTHON needs transformers, tokenizers, jinja2, gguf and numpy (Unsloth
Studio's has them).  ``--server URL`` uses a llama-server already running;
otherwise one is started on the stub with ``--llama-server`` (LM Studio's own
binary by default) and stopped after.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import training_render as tr  # noqa: E402

MODEL = Path.home() / ".roaddraft" / "tokenizers" / "Qwen3.5-9B"
LMS_BACKENDS = Path.home() / ".lmstudio" / "extensions" / "backends"


# ------------------------------------------------------------ the two sides

class Trainer:
    """The trainer's side: transformers' tokenizer and chat template."""

    def __init__(self, tokenizer_json: Path, template: Path):
        from transformers import PreTrainedTokenizerFast
        self.template_text = Path(template).read_text(encoding="utf-8")
        self.tok = PreTrainedTokenizerFast(tokenizer_file=str(tokenizer_json),
                                           chat_template=self.template_text)

    def render(self, messages, tools, gen: bool, thinking: bool) -> str:
        return self.tok.apply_chat_template(list(messages), tools=tools, tokenize=False,
                                            add_generation_prompt=gen, enable_thinking=thinking)

    def encode(self, text: str):
        enc = self.tok(text, add_special_tokens=False, return_offsets_mapping=True)
        return list(enc["input_ids"]), [tuple(o) for o in enc["offset_mapping"]]


class Server:
    """The serving side: llama-server's template engine and tokenizer."""

    def __init__(self, url: str, send_kwargs: bool = True):
        self.url = url.rstrip("/")
        self.send_kwargs = send_kwargs   # False: the template decides (a served GGUF's own, as LM Studio sends it)

    def post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())

    def prompt(self, messages, tools, thinking: bool) -> str:
        body = {"messages": tr.strip_for_request(messages), "tools": tools}
        if self.send_kwargs:
            body["chat_template_kwargs"] = {"enable_thinking": thinking}
        return self.post("/apply-template", body)["prompt"]

    def tokenize(self, text: str):
        return self.post("/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"]

    def version(self) -> dict:
        try:
            with urllib.request.urlopen(self.url + "/props", timeout=30) as r:
                p = json.loads(r.read())
            return {"build_info": p.get("build_info"), "model": Path(p.get("model_path", "")).name}
        except Exception as ex:   # noqa: BLE001
            return {"error": str(ex)}


def lms_llama_server() -> Path:
    found = sorted(LMS_BACKENDS.glob("llama.cpp-*/llama-server"),
                   key=lambda p: [int(x) for x in p.parent.name.rsplit("-", 1)[-1].split(".")])
    if not found:
        raise SystemExit("no LM Studio llama.cpp backend found; pass --llama-server or --server")
    return found[-1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(binary: Path, stub: Path, log: Path):
    port = free_port()
    env = dict(os.environ, DYLD_LIBRARY_PATH=str(binary.parent), LD_LIBRARY_PATH=str(binary.parent))
    proc = subprocess.Popen([str(binary), "-m", str(stub), "--host", "127.0.0.1", "--port", str(port),
                             "-c", "1024", "-ngl", "0", "--jinja"],
                            stdout=log.open("w"), stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                if b"ok" in r.read():
                    return proc, url
        except Exception:   # noqa: BLE001
            pass
        if proc.poll() is not None:
            raise SystemExit(f"llama-server exited; see {log}")
        time.sleep(0.5)
    proc.kill()
    raise SystemExit(f"llama-server did not come up; see {log}")


# ------------------------------------------------------------ the sample

def sample(folder: Path, per_file: int, ids=None):
    """Per conversation file: the first, the one with the most turns, any with
    a ``[harness]`` note, any with a masked turn, up to ``per_file``."""
    out = []
    for path in sorted(folder.glob("*.jsonl")):
        rows = []
        with path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh):
                if not line.strip():
                    continue
                head = json.loads(line)
                if ids and head["id"] not in ids:
                    continue
                c = head["header"]["counts"]
                rows.append((n, head["id"], c["turns"], c.get("notes", 0), c.get("masked", 0), line))
        if not rows:
            continue
        if ids:
            pick = rows
        else:
            pick, seen = [], set()
            for r in ([rows[0], max(rows, key=lambda r: r[2])]
                      + [r for r in rows if r[3]][:2] + [r for r in rows if r[4]][:1]):
                if r[1] not in seen and len(pick) < per_file:
                    pick.append(r)
                    seen.add(r[1])
        for r in pick:
            out.append((path.name, json.loads(r[5])))
    return out


# ------------------------------------------------------------ one conversation

def first_diff(a: str, b: str) -> dict:
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return {"at": n, "a": a[max(0, n - 60): n + 60], "b": b[max(0, n - 60): n + 60],
            "len_a": len(a), "len_b": len(b)}


def check(conv: dict, tools: list, trainer: Trainer, server: Server, thinking: str, j2=None) -> dict:
    msgs = conv["messages"]
    on = thinking == "on"
    out = {"id": conv["id"], "thinking": thinking, "turns": 0, "issues": Counter(), "examples": []}

    def issue(kind, **detail):
        out["issues"][kind] += 1
        if sum(1 for e in out["examples"] if e["kind"] == kind) < 2:
            out["examples"].append(dict(kind=kind, **detail))

    full_hf = trainer.render(msgs, tools, False, on)
    if j2 is not None:
        full_j2 = j2.render(messages=msgs, tools=tools, add_generation_prompt=False, enable_thinking=on)
        if full_j2 != full_hf:
            issue("trainer_vs_token_script", **first_diff(full_hf, full_j2))

    plan = tr.plan_segments(msgs, lambda m, g: trainer.render(m, tools, g, on))
    out["segments"] = len(plan.segments)
    out["inconsistent"] = len(plan.inconsistent)
    seg_of = {i: s for s in plan.segments for i in s.turns + s.masked}
    encoded = {}
    for s in plan.segments:
        ids, offs = trainer.encode(s.text)
        _, labels = tr.labels_for(s.text, s.spans, lambda t, ids=ids, offs=offs: (ids, offs))
        encoded[id(s)] = (ids, offs, labels)

    for i in tr.assistant_indices(msgs):
        out["turns"] += 1
        seg = seg_of[i]
        ids, offs, labels = encoded[id(seg)]
        served = server.prompt(msgs[:i], tools, on)
        if served != plan.prompts[i]:
            issue("engine_prompt", turn=i, **first_diff(plan.prompts[i], served))
        if not seg.text.startswith(served):
            issue("context_string", turn=i, **first_diff(seg.text, served))
            continue
        sids = server.tokenize(served)
        if ids[:len(sids)] != sids:
            k = next((j for j, (x, y) in enumerate(zip(ids, sids)) if x != y), len(sids))
            issue("context_tokens", turn=i, at=k, train=ids[max(0, k - 3):k + 3], served=sids[max(0, k - 3):k + 3],
                  served_len=len(sids))
        if tr.weight(msgs[i]) == 0:
            continue
        start, end = tr.target_span(seg.text, served)
        completion = seg.text[start:end]
        trained = [t for t, (a, b), lab in zip(ids, offs, labels) if lab != tr.IGNORE and start <= a and b <= end]
        alone, _ = trainer.encode(completion)
        if trained != alone:
            got = trainer.tok.decode(trained)
            issue("target_tokens", turn=i, trained=len(trained), alone=len(alone),
                  trained_head=trainer.tok.convert_ids_to_tokens(trained[:4]),
                  alone_head=trainer.tok.convert_ids_to_tokens(alone[:4]), decodes_to_completion=(got == completion))
        if trainer.tok.decode(trained) != completion.lstrip("\n") and trainer.tok.decode(trained) != completion:
            issue("target_text", turn=i, trained=trainer.tok.decode(trained)[:120], completion=completion[:120])
        back = tr.parse_completion(completion, tools)
        want = [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                for c in msgs[i].get("tool_calls") or []]
        if [c["name"] for c in back["tool_calls"]] != [c["name"] for c in want]:
            issue("round_trip_names", turn=i, got=[c["name"] for c in back["tool_calls"]],
                  want=[c["name"] for c in want])
        else:
            for g, w in zip(back["tool_calls"], want):
                if not tr.same_value(g["arguments"], w["arguments"]):
                    bad = sorted(k for k in set(g["arguments"]) | set(w["arguments"])
                                 if not tr.same_value(g["arguments"].get(k), w["arguments"].get(k)))
                    issue("round_trip_args", turn=i, tool=w["name"], keys=bad,
                          got={k: g["arguments"].get(k) for k in bad[:3]},
                          want={k: w["arguments"].get(k) for k in bad[:3]})
        if back["content"] != (msgs[i].get("content") or "").strip():
            issue("round_trip_text", turn=i, got=back["content"][:120], want=(msgs[i].get("content") or "")[:120])
    out["issues"] = dict(out["issues"])
    return out


def summarize(results: list) -> dict:
    by = {}
    for r in results:
        s = by.setdefault(r["thinking"], {"conversations": 0, "turns": 0, "segments": 0, "split": 0,
                                          "issues": Counter(), "conversations_with": Counter()})
        s["conversations"] += 1
        s["turns"] += r["turns"]
        s["segments"] += r["segments"]
        s["split"] += r["segments"] > 1
        for k, v in r["issues"].items():
            s["issues"][k] += v
            s["conversations_with"][k] += 1
    for s in by.values():
        s["issues"] = dict(s["issues"])
        s["conversations_with"] = dict(s["conversations_with"])
    return by


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("folder", type=Path, help="results/training: the conversations and tools.json")
    p.add_argument("--out", type=Path, help="where to write render-check.json (default FOLDER/render-check)")
    p.add_argument("--per-file", type=int, default=3)
    p.add_argument("--ids", nargs="*", help="check these conversation ids only")
    p.add_argument("--thinking", choices=("off", "on", "both"), default="both")
    p.add_argument("--tokenizer", type=Path, default=MODEL / "tokenizer.json")
    p.add_argument("--template", type=Path, default=MODEL / "chat_template.jinja")
    p.add_argument("--server", help="a llama-server already running on the stub (or the real model)")
    p.add_argument("--llama-server", type=Path, help="the binary to start (default: LM Studio's newest backend)")
    p.add_argument("--stub", type=Path, help="the stand-in GGUF (built by training_serving_stub.py when missing)")
    p.add_argument("--serve-template", help="serve with this template instead ('nothink': the base's with the "
                                            "think block always closed, training_render.nothink_template); the "
                                            "requests then carry no enable_thinking, as LM Studio sends them")
    a = p.parse_args(argv)
    out_dir = a.out or a.folder / "render-check"
    out_dir.mkdir(parents=True, exist_ok=True)

    trainer = Trainer(a.tokenizer, a.template)
    import training_tokens
    j2, _ = training_tokens.template_from(a.template)
    tools_doc = json.loads((a.folder / "tools.json").read_text())
    proc = None
    if a.server:
        url = a.server
    else:
        import training_serving_stub
        serve_template = a.template
        if a.serve_template:
            serve_template = out_dir / "serve-template.jinja"
            text = (tr.nothink_template(a.template.read_text(encoding="utf-8")) if a.serve_template == "nothink"
                    else Path(a.serve_template).read_text(encoding="utf-8"))
            serve_template.write_text(text, encoding="utf-8")
        stub = a.stub or out_dir / ("serving-stub.gguf" if not a.serve_template else "serving-stub-served.gguf")
        if not stub.exists() or a.serve_template:
            training_serving_stub.build(stub, a.tokenizer, serve_template)
        binary = a.llama_server or lms_llama_server()
        proc, url = start_server(binary, stub, out_dir / "llama-server.log")
    server = Server(url, send_kwargs=not a.serve_template)
    try:
        info = {"server": server.version(), "llama_server": str(a.llama_server or (lms_llama_server() if not a.server else "")),
                "transformers": __import__("transformers").__version__, "serve_template": a.serve_template,
                "template_sha256": __import__("hashlib").sha256(trainer.template_text.encode()).hexdigest()}
        convs = sample(a.folder, a.per_file, set(a.ids) if a.ids else None)
        print(f"{len(convs)} conversations from {a.folder}", flush=True)
        modes = ("off", "on") if a.thinking == "both" else (a.thinking,)
        results, started = [], time.time()
        for name, conv in convs:
            tools = tools_doc[conv["header"]["tools_sha256"]]["function_tools"]
            for mode in modes:
                r = check(conv, tools, trainer, server, mode, j2)
                r["file"] = name
                results.append(r)
                print(f"  {conv['id']} [{mode}] turns {r['turns']} segments {r['segments']} "
                      f"issues {r['issues'] or 'none'}", flush=True)
        doc = {"info": info, "summary": summarize(results), "results": results,
               "seconds": round(time.time() - started, 1)}
        (out_dir / "render-check.json").write_text(json.dumps(doc, indent=1, default=list) + "\n")
        print(json.dumps(doc["summary"], indent=1))
        print(f"wrote {out_dir / 'render-check.json'}")
    finally:
        if proc is not None:
            proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

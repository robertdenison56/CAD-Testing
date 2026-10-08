"""run_models.py [--budget MIN] MODEL... -> one pass of batches B and C per model, in turn.

For each model: unload everything on RobertsPC, load this model alone at
lmstudio_runner.CONTEXT with one slot, check the loaded context, measure what
the tool schema costs on its tokenizer (one request with max_tokens 1), keep
that in runs/<label>/model.json, then run every probe set up under
runs/<label>/ (setup_runs.py first). The label is the model id after its
publisher prefix: qwen/qwen3.5-9b -> runs/qwen3.5-9b.

One model at a time on purpose: the turn times are part of what a pass
records, and two models sharing RobertsPC's GPU would muddy them.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import lmstudio_runner as runner
from roaddraft.probes import fixture, tasks

ROOT = Path(__file__).parent
MODELS_API = "http://localhost:1234/api/v0/models"


def lms(*args):
    r = subprocess.run([runner.LMS, *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def info(model):
    with urllib.request.urlopen(MODELS_API, timeout=30) as resp:
        return next((m for m in json.loads(resp.read())["data"] if m["id"] == model), {})


def schema_cost(model):
    """Prompt tokens for the system instructions + all tools + a one-word user turn."""
    tmp = Path(tempfile.mkdtemp())
    doc = fixture.start_document(tmp / "project", "sheets")
    (tmp / "server.json").write_text(json.dumps({"cmd": [
        str(Path(sys.executable).parent / "roaddraft-mcp"), "--doc", str(doc)]}))
    server = runner.Server(tmp)
    try:
        tools = runner.tool_defs(server.tools)
        body = json.dumps({"model": model, "max_tokens": 1, "stream": False, "tools": tools,
                           "messages": [{"role": "system", "content": server.instructions},
                                        {"role": "user", "content": "ok"}]}).encode()
        req = urllib.request.Request(runner.LMSTUDIO, body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                usage = json.loads(resp.read()).get("usage") or {}
        except urllib.error.HTTPError as ex:
            return len(tools), ex.read().decode(errors="replace")
        return len(tools), usage.get("prompt_tokens")
    finally:
        server.close()


def main(argv):
    budget = None
    if argv and argv[0] == "--budget":
        budget = float(argv[1]) * 60
        argv = argv[2:]
    for model in argv:
        label = model.split("/")[-1]
        folder = ROOT / "runs" / label
        if not folder.is_dir():
            print(f"skip {model}: run setup_runs.py {label} first", flush=True)
            continue
        print(f"=== {model} -> runs/{label}  {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        lms("unload", "--all")
        rc, out = lms("load", model, "--context-length", str(runner.CONTEXT), "--parallel", "1", "-y")
        loaded = info(model)
        print(f"load rc={rc}: state={loaded.get('state')} context={loaded.get('loaded_context_length')}",
              flush=True)
        if rc != 0 or loaded.get("loaded_context_length", 0) < runner.CONTEXT:
            print(f"could not load {model} at {runner.CONTEXT}: {out[-300:]}", flush=True)
            continue
        runner.REWRITE_TYPE_LISTS = False
        n_tools, tokens = schema_cost(model)
        if isinstance(tokens, str) and "filter-mapping" in tokens:   # see the runner's docstring
            runner.REWRITE_TYPE_LISTS = True
            n_tools, tokens = schema_cost(model)
        if isinstance(tokens, str):
            print(f"skip {model}: the tools are refused: {tokens[:300]}", flush=True)
            continue
        meta = {"model": model, "quantization": loaded.get("quantization"),
                "arch": loaded.get("arch"), "max_context": loaded.get("max_context_length"),
                "loaded_context": loaded.get("loaded_context_length"),
                "capabilities": loaded.get("capabilities"), "tools": n_tools,
                "schema_prompt_tokens": tokens, "type_lists_rewritten": runner.REWRITE_TYPE_LISTS,
                "budget_min": budget and budget / 60,
                "max_turns": runner.MAX_TURNS, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        print(json.dumps(meta), flush=True)
        (folder / "model.json").write_text(json.dumps(meta, indent=1))
        for probe in tasks.PROBES:
            if (folder / probe.id).is_dir():
                runner.run(label, model, probe, budget)
        meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        (folder / "model.json").write_text(json.dumps(meta, indent=1))
    print(f"=== done {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

"""A LoRA checkpoint as the GGUF the PC serves (training plan section 6,
decision 1: every checkpoint merged and quantized to Q4_K_M on the training
pod before it stops, the GGUF carried to the PC).

    python scripts/training_merge_quantize.py --adapter runs/t1-smoke/adapter \\
        --out runs/t1-smoke/gguf --llama-cpp /workspace/llama.cpp

1. *merge*: the base in bf16 with the adapter folded in (PEFT
   ``merge_and_unload``), saved with the base's tokenizer;
2. *template*: the merged folder's ``chat_template.jinja`` is the base's with
   the generation prompt always closing the think block
   (``training_render.nothink_template``), the serving prompt a checkpoint
   trained with ``--thinking off`` was trained on; ``--keep-thinking`` keeps
   the base's;
3. *convert*: llama.cpp's ``convert_hf_to_gguf.py`` to a bf16 GGUF;
4. *quantize*: ``llama-quantize`` to ``--quant`` (Q4_K_M, the board's file
   type; ``--imatrix`` if the base file was made with one);
5. *check*: ``llama-server`` loads the result, renders a request and writes a
   few tokens (``check.json``); with ``--conversation`` the rendered prompt is
   held to the trainer's render of that conversation's first request.

``--verify-merge N`` also compares the adapter model's and the merged model's
logits on N tokens of text before saving (they should agree to bf16 rounding).
``--tiny WIDTHxLAYERS`` runs the whole chain on a random Qwen3.5-shaped base
with no download (a CPU check of the plumbing).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import training_render as tr  # noqa: E402

BASE = "Qwen/Qwen3.5-9B"
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"


def sh(cmd, log):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    t0 = time.time()
    with open(log, "a") as fh:
        fh.write("+ " + " ".join(str(c) for c in cmd) + "\n")
        fh.flush()
        r = subprocess.run([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT)
    if r.returncode:
        raise SystemExit(f"failed ({r.returncode}): {cmd[0]}; see {log}")
    return round(time.time() - t0, 1)


def merge(args, merged: Path) -> dict:
    import torch
    from peft import PeftModel
    t0 = time.time()
    if args.tiny:
        import training_lora
        base = training_lora.tiny_model(args.tiny)
        tok, _ = training_lora.load_tokenizer(args.tokenizer, None, True)
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        base = AutoModelForCausalLM.from_pretrained(args.base, revision=args.revision, dtype=torch.bfloat16,
                                                    device_map="cpu" if args.cpu else "auto")
        tok = AutoTokenizer.from_pretrained(args.tokenizer or args.base, revision=args.revision)
    model = PeftModel.from_pretrained(base, str(args.adapter))
    info = {"adapter": str(args.adapter)}
    probe = None
    if args.verify_merge:
        text = "Draft the stationing along BASE:ALIGN-1 on sheet C-101 at 1\" = 40'. " * 40
        probe = tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"][:, :args.verify_merge]
        probe = probe.to(next(model.parameters()).device)
        with torch.no_grad():
            before = model(input_ids=probe).logits.float()
    model = model.merge_and_unload()
    if probe is not None:
        with torch.no_grad():
            after = model(input_ids=probe).logits.float()
        info["verify_merge"] = {"tokens": int(probe.shape[1]),
                                "max_abs_logit_diff": float((before - after).abs().max()),
                                "argmax_agree": float((before.argmax(-1) == after.argmax(-1)).float().mean())}
    merged.mkdir(parents=True, exist_ok=True)
    if args.tiny:
        model.config.architectures = ["Qwen3_5ForCausalLM"]
    model.save_pretrained(str(merged), safe_serialization=True)
    tok.save_pretrained(str(merged))
    info["merge_seconds"] = round(time.time() - t0, 1)
    return info


def set_template(merged: Path, keep_thinking: bool, template: Path = None) -> dict:
    path = merged / "chat_template.jinja"
    base = (template.read_text(encoding="utf-8") if template else path.read_text(encoding="utf-8"))
    text = base if keep_thinking else tr.nothink_template(base)
    path.write_text(text, encoding="utf-8")
    cfg = merged / "tokenizer_config.json"
    if cfg.exists():   # an inline copy would win over the file in some readers: keep one template
        d = json.loads(cfg.read_text())
        if "chat_template" in d:
            d.pop("chat_template")
            cfg.write_text(json.dumps(d, indent=2) + "\n")
    return {"template": "base" if keep_thinking else "nothink",
            "template_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "base_template_sha256": hashlib.sha256(base.encode()).hexdigest()}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def check(server_bin: Path, gguf: Path, out: Path, args) -> dict:
    port = free_port()
    env = dict(os.environ, LD_LIBRARY_PATH=str(server_bin.parent), DYLD_LIBRARY_PATH=str(server_bin.parent))
    cmd = [str(server_bin), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(port), "-c", str(args.check_ctx),
           "--jinja", "-ngl", str(args.ngl)]
    log = out / "llama-server.log"
    proc = subprocess.Popen(cmd, stdout=log.open("w"), stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    try:
        t0 = time.time()
        while True:
            try:
                with urllib.request.urlopen(url + "/health", timeout=2) as r:
                    if b"ok" in r.read():
                        break
            except Exception:   # noqa: BLE001
                pass
            if proc.poll() is not None or time.time() - t0 > 900:
                raise SystemExit(f"llama-server did not load {gguf}; see {log}")
            time.sleep(1)
        res = {"loaded_seconds": round(time.time() - t0, 1)}
        msgs = [{"role": "system", "content": "You are a drafter."},
                {"role": "user", "content": "Say which tool lists a document's layers."}]
        res["prompt"] = post(url + "/apply-template", {"messages": msgs})["prompt"][-80:]
        gen = post(url + "/v1/chat/completions", {"messages": msgs, "max_tokens": 16, "temperature": 0})
        res["reply"] = (gen["choices"][0]["message"].get("content") or "")[:200]
        res["timings"] = gen.get("timings")
        if args.conversation:
            conv_file, cid = args.conversation
            tools_doc = json.loads((Path(conv_file).parent / "tools.json").read_text())
            conv = next(json.loads(line) for line in open(conv_file, encoding="utf-8")
                        if line.strip() and json.loads(line)["id"] == cid)
            tools = tools_doc[conv["header"]["tools_sha256"]]["function_tools"]
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(str(out / "merged"))
            i = tr.assistant_indices(conv["messages"])[0]
            want = tok.apply_chat_template(conv["messages"][:i], tools=tools, tokenize=False,
                                           add_generation_prompt=True, enable_thinking=False)
            got = post(url + "/apply-template", {"messages": tr.strip_for_request(conv["messages"][:i]),
                                                 "tools": tools})["prompt"]
            res["conversation_prompt_equal"] = got == want
        return res
    finally:
        proc.terminate()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--adapter", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--base", default=BASE)
    p.add_argument("--revision", default=REVISION)
    p.add_argument("--tokenizer", help="default: --base")
    p.add_argument("--llama-cpp", type=Path, required=True,
                   help="a llama.cpp checkout with convert_hf_to_gguf.py, gguf-py and build/bin/{llama-quantize,llama-server}")
    p.add_argument("--quant", default="Q4_K_M")
    p.add_argument("--imatrix", type=Path)
    p.add_argument("--keep-thinking", action="store_true", help="embed the base's template unchanged")
    p.add_argument("--template", type=Path, help="the template to start from (default: the base's)")
    p.add_argument("--keep-bf16", action="store_true", help="keep the bf16 GGUF and the merged folder")
    p.add_argument("--verify-merge", type=int, default=256)
    p.add_argument("--no-check", dest="do_check", action="store_false")
    p.add_argument("--check-ctx", type=int, default=8192)
    p.add_argument("--ngl", type=int, default=99)
    p.add_argument("--conversation", nargs=2, metavar=("JSONL", "ID"),
                   help="hold the served prompt of this conversation's first request to the trainer's render")
    p.add_argument("--llama-server", type=Path, help="default: LLAMA_CPP/build/bin/llama-server")
    p.add_argument("--cpu", action="store_true", help="merge on the CPU")
    p.add_argument("--tiny", help="a random Qwen3.5-shaped base, WIDTHxLAYERS (CPU check)")
    a = p.parse_args(argv)
    a.tokenizer = a.tokenizer or a.base
    a.out.mkdir(parents=True, exist_ok=True)
    log = a.out / "merge.log"
    merged = a.out / "merged"
    rec = {"base": a.base if not a.tiny else f"tiny {a.tiny}", "revision": a.revision, "quant": a.quant}
    rec.update(merge(a, merged))
    rec.update(set_template(merged, a.keep_thinking, a.template))
    bf16 = a.out / "model-bf16.gguf"
    final = a.out / f"model-{a.quant}.gguf"
    env_py = sys.executable
    os.environ["PYTHONPATH"] = str(a.llama_cpp / "gguf-py") + os.pathsep + os.environ.get("PYTHONPATH", "")
    rec["convert_seconds"] = sh([env_py, a.llama_cpp / "convert_hf_to_gguf.py", merged, "--outtype", "bf16",
                                 "--outfile", bf16, "--no-mtp"], log)
    rec["mtp"] = "left out (transformers does not load the MTP head; LoRA never touched it)"
    qbin = a.llama_cpp / "build" / "bin" / "llama-quantize"
    if not qbin.exists():
        qbin = a.llama_cpp / "llama-quantize"
    cmd = [qbin] + (["--imatrix", a.imatrix] if a.imatrix else []) + [bf16, final, a.quant]
    rec["quantize_seconds"] = sh(cmd, log)
    rec["gguf"] = str(final)
    rec["gguf_bytes"] = final.stat().st_size
    h = hashlib.sha256()
    with final.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    rec["gguf_sha256"] = h.hexdigest()
    if a.do_check:
        server = a.llama_server or (a.llama_cpp / "build" / "bin" / "llama-server")
        rec["check"] = check(server, final, a.out, a)
    if not a.keep_bf16:   # the merged weights and the bf16 GGUF are ~19 GB each; the tokenizer files stay
        bf16.unlink(missing_ok=True)
        for w in merged.glob("*.safetensors"):
            w.unlink()
    (a.out / "check.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""LoRA on Qwen3.5-9B over the converted RoadDraft conversations (training
plan section 4: the T1 smoke and T1).

    python scripts/training_lora.py --data results/training --out runs/t1-smoke --smoke

Each conversation (``results/training/*.jsonl``, written by
``python -m roaddraft.trajectories.conversations convert``) is rendered
through the model's own chat template with its tool definitions
(``tools.json``) and cut into the sequences ``training_render.plan_segments``
gives (one, unless a ``[harness]`` note moved the template's last query);
the loss is on the assistant turns only, an assistant message with
``"weight": 0`` (an injected fault's broken turn) is context and never a
target, and the empty think block is context too (``--thinking off``, the
serving prompt the render check proved equal; see
``benchmarks/training/T1_SMOKE.md``).

Engines:

- ``unsloth`` (default): Unsloth's ``FastLanguageModel``: its gradient
  checkpointing offloads the saved activations to CPU memory and its loss
  never builds the full logits, which is what lets a 122k-token sequence
  with a 248k-token vocabulary fit on one 48-80 GB card.
- ``hf``: plain transformers + PEFT, with the loss computed here in chunks
  over the trained positions only (``chunked_loss``), for when Unsloth's
  Qwen3.5 path is broken.  Needs more memory (no activation offload).

``--prepare-only`` builds every training sequence on the CPU and writes its
counts (``prepared.json``: sequences, tokens, trained tokens, the longest),
the exact size of the run, with no model loaded.  ``--smoke`` takes 50
conversations (the five longest first, so a sequence that does not fit
fails in the first minutes) for one epoch, and writes ``metrics.jsonl``: per
step the loss, the tokens, tokens a second and the peak GPU memory.

``--val-fraction`` holds a share of the training tasks out of training, by
seed (every conversation of a held seed, both levels and the faulted copies),
and reports the loss on up to ``--val-max`` of their reference conversations
before the first step, every ``--eval-steps`` and at the end of each epoch.
The validation data is training-set seeds only: no eval set is read.

``--resume CHECKPOINT`` continues a run from one of its checkpoints: the
adapter, the optimizer, the step and the place in the epoch (the order of an
epoch depends only on ``--seed`` and the epoch's number).

Writes under ``--out``: ``prepared.json``, ``metrics.jsonl``,
``checkpoint-<step>/`` (the adapter and ``trainer_state.pt``, every
``--save-steps`` and at the end of each epoch), ``adapter/`` (the last),
``run.json`` (arguments, versions, template hash, timings).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import training_render as tr  # noqa: E402

BASE = "Qwen/Qwen3.5-9B"
#: the Hugging Face revision the tokenizer, the template and the token counts were taken from
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
#: sha256 of that revision's chat_template.jinja: the template the render check proved against the server
TEMPLATE_SHA256 = "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715"
#: the language model's projections; the vision tower's blocks are not under ``layers.N``
TARGETS = (r".*layers\.\d+\.(self_attn\.(q_proj|k_proj|v_proj|o_proj)"
           r"|linear_attn\.(in_proj_qkv|in_proj_z|out_proj)|mlp\.(gate_proj|up_proj|down_proj))")
SMOKE = 50
SMOKE_LONGEST = 5


# ------------------------------------------------------------ data

def load_tokenizer(source: str, revision: Optional[str] = None, check_template: bool = True):
    """The model's tokenizer: a Hugging Face repo id or folder with the usual
    files, or a folder holding only ``tokenizer.json`` and
    ``chat_template.jinja`` (``~/.roaddraft/tokenizers/Qwen3.5-9B``)."""
    from transformers import AutoTokenizer, PreTrainedTokenizerFast
    path = Path(source).expanduser()
    if path.is_dir() and not (path / "tokenizer_config.json").exists():
        tok = PreTrainedTokenizerFast(tokenizer_file=str(path / "tokenizer.json"),
                                      chat_template=(path / "chat_template.jinja").read_text(encoding="utf-8"))
    else:
        tok = AutoTokenizer.from_pretrained(source, revision=revision)
    template = tok.chat_template if isinstance(tok.chat_template, str) else (tok.chat_template or {}).get("default")
    sha = hashlib.sha256((template or "").encode()).hexdigest()
    if check_template and sha != TEMPLATE_SHA256:
        raise SystemExit(f"the tokenizer's chat template is sha256 {sha[:16]}, not the checked "
                         f"{TEMPLATE_SHA256[:16]}: run scripts/training_render_check.py on it first, then "
                         "pass --no-template-check (run.json records the hash used)")
    return tok, sha


def read_conversations(folder: Path, sets: Sequence[str], faults: str) -> List[dict]:
    """The conversations of the files matching ``sets`` (globs on the file
    name), with or without the faulted copies."""
    out = []
    for path in sorted(folder.glob("*.jsonl")):
        name = path.name
        if sets and not any(Path(name).match(g) for g in sets):
            continue
        is_faults = name.endswith("-faults.jsonl")
        if (faults == "none" and is_faults) or (faults == "only" and not is_faults):
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    conv = json.loads(line)
                    conv["_file"] = name
                    out.append(conv)
    return out


def smoke_pick(convs: List[dict], lengths: Dict[str, list], n: int = SMOKE, longest: int = SMOKE_LONGEST,
               seed: int = 0) -> List[dict]:
    """The smoke's conversations: the ``longest`` longest by token count
    (``tokens.json``) first, then the rest drawn evenly across the files."""
    size = lambda c: (lengths.get(c["id"]) or [0])[0]  # noqa: E731
    ranked = sorted(convs, key=size, reverse=True)
    head = ranked[:longest]
    rest = [c for c in convs if c not in head]
    rng = random.Random(seed)
    by_file: Dict[str, List[dict]] = {}
    for c in rest:
        by_file.setdefault(c["_file"], []).append(c)
    for v in by_file.values():
        rng.shuffle(v)
    pick, files = [], sorted(by_file)
    while len(head) + len(pick) < n and any(by_file.values()):
        for f in files:
            if by_file[f] and len(head) + len(pick) < n:
                pick.append(by_file[f].pop())
    return head + pick


def task_key(conv: dict) -> str:
    """What a conversation is a copy of: its task's seed (the two levels and
    the faulted copies of one task share it), else its id before the level."""
    seed = (conv.get("header") or {}).get("seed")
    return f"seed:{seed}" if seed is not None else str(conv["id"]).split(".")[0]


def in_validation(conv: dict, fraction: float) -> bool:
    """Whether the conversation's task is held out for the validation loss:
    a fixed draw on the task's key, so it does not follow the dials (which
    cycle with the seed) and does not move when conversations are added."""
    if fraction <= 0:
        return False
    draw = int(hashlib.sha256(("validation:" + task_key(conv)).encode()).hexdigest()[:8], 16)
    return draw < fraction * 2**32


def split_validation(convs: List[dict], fraction: float, n: int, seed: int = 0):
    """``(training, validation)``: every conversation of a held task leaves
    training; the validation sample is up to ``n`` of their reference
    conversations (no faulted copy), drawn evenly across the files."""
    held = [c for c in convs if in_validation(c, fraction)]
    train = [c for c in convs if not in_validation(c, fraction)]
    refs = [c for c in held if not c["_file"].endswith("-faults.jsonl")]
    val = smoke_pick(refs, {}, n=n, longest=0, seed=seed)
    if {task_key(c) for c in train} & {task_key(c) for c in val}:
        raise SystemExit("a validation task is also in training")
    return train, val


def build_examples(conv: dict, tools: list, tok, thinking: str, max_len: int) -> List[dict]:
    """A conversation's training sequences: ids, labels and counts; a
    sequence past ``max_len`` is left out and counted, and so is one that
    trains nothing (every turn it holds is a weight-0 turn)."""
    import numpy as np
    on = thinking == "on"
    render = lambda m, g: tok.apply_chat_template(list(m), tools=tools, tokenize=False,  # noqa: E731
                                                  add_generation_prompt=g, enable_thinking=on)
    plan = tr.plan_segments(conv["messages"], render)

    def encode(text):
        enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
        return list(enc["input_ids"]), [tuple(o) for o in enc["offset_mapping"]]

    out = []
    for k, seg in enumerate(plan.segments):
        ids, labels = tr.labels_for(seg.text, seg.spans, encode)
        # int32 arrays, not lists: a full epoch is 616M tokens, 5 GB this way and several times that as lists
        ids, labels = np.asarray(ids, dtype=np.int32), np.asarray(labels, dtype=np.int32)
        trained = int((labels[1:] != tr.IGNORE).sum())   # the first token has no context: never a target
        out.append({"id": f"{conv['id']}#{k}", "conversation": conv["id"], "input_ids": ids, "labels": labels,
                    "tokens": len(ids), "trained": trained, "too_long": len(ids) > max_len,
                    "untrained": trained == 0, "turns": len(seg.turns), "masked": len(seg.masked)})
    return out


_WORKER = {}


def _init_worker(tokenizer, revision, check):
    _WORKER["tok"], _ = load_tokenizer(tokenizer, revision, check)


def _work(job):
    conv, tools, thinking, max_len, keep_ids = job
    rows = build_examples(conv, tools, _WORKER["tok"], thinking, max_len)
    if not keep_ids:
        for r in rows:
            r.pop("input_ids"), r.pop("labels")
    return rows


def prepare(convs, tools_doc, args, keep_ids: bool) -> List[dict]:
    jobs = [(c, tools_doc[c["header"]["tools_sha256"]]["function_tools"], args.thinking, args.max_seq_len, keep_ids)
            for c in convs]
    workers = max(1, int(args.workers))
    if workers == 1:
        _init_worker(args.tokenizer, args.revision, not args.no_template_check)
        rows = [r for j in jobs for r in _work(j)]
    else:
        from multiprocessing import get_context
        with get_context("spawn").Pool(workers, _init_worker,
                                       (args.tokenizer, args.revision, not args.no_template_check)) as pool:
            rows = [r for part in pool.imap(_work, jobs, chunksize=4) for r in part]
    return rows


def usable(rows: List[dict]) -> List[dict]:
    """The sequences that train: not past the length limit, and with a target."""
    return [r for r in rows if not r["too_long"] and not r["untrained"]]


def stats(rows: List[dict], convs: List[dict]) -> dict:
    kept = usable(rows)
    lens = sorted(r["tokens"] for r in kept)
    q = lambda p: lens[min(len(lens) - 1, int(p * len(lens)))] if lens else 0  # noqa: E731
    return {"conversations": len(convs), "sequences": len(rows), "kept": len(kept),
            "dropped_too_long": sum(1 for r in rows if r["too_long"]),
            "dropped_untrained": sum(1 for r in rows if r["untrained"] and not r["too_long"]),
            "split_conversations": len({r["conversation"] for r in rows if not r["id"].endswith("#0")}),
            "tokens": sum(lens), "trained_tokens": sum(r["trained"] for r in kept),
            "masked_turns": sum(r["masked"] for r in kept),
            "longest": lens[-1] if lens else 0, "median": q(0.5), "p90": q(0.9), "p99": q(0.99),
            "longest_id": max(kept, key=lambda r: r["tokens"])["id"] if kept else None}


# ------------------------------------------------------------ model

def load_model(args):
    import torch
    if args.engine == "unsloth":
        from unsloth import FastLanguageModel
        model, _ = FastLanguageModel.from_pretrained(
            model_name=args.model, revision=args.revision, max_seq_length=args.max_seq_len,
            dtype=torch.bfloat16, load_in_4bit=args.load_4bit, full_finetuning=False)
        kw = dict(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout, bias="none",
                  use_gradient_checkpointing="unsloth", random_state=args.seed, max_seq_length=args.max_seq_len)
        try:
            # the same pattern as the hf engine: a name list also matches a vision tower's projections
            return FastLanguageModel.get_peft_model(model, target_modules=TARGETS, **kw)
        except Exception as exc:   # noqa: BLE001
            # an Unsloth that takes names only (before 2026.11); adapter_summary then checks where they landed
            print(f"Unsloth did not take the target pattern ({type(exc).__name__}: {exc}); using the names",
                  flush=True)
            return FastLanguageModel.get_peft_model(model, target_modules=list(args.target_names), **kw)
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM
    kw = {"dtype": torch.bfloat16, "attn_implementation": args.attn}
    if args.revision:
        kw["revision"] = args.revision
    if args.load_4bit:
        from transformers import BitsAndBytesConfig
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                       bnb_4bit_compute_dtype=torch.bfloat16)
    if args.tiny:
        model = tiny_model(args.tiny)
    else:
        model = AutoModelForCausalLM.from_pretrained(args.model, device_map={"": 0} if torch.cuda.is_available()
                                                     else None, **kw)
    torch.manual_seed(args.seed)   # the adapter's initial weights
    model.config.use_cache = False
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    cfg = LoraConfig(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
                     target_modules=TARGETS, bias="none", task_type="CAUSAL_LM")
    return get_peft_model(model, cfg)


def adapter_summary(model) -> dict:
    """What the adapter sits on: the adapted modules by kind and the
    trainable parameters.  Refuses an adapter on anything but the language
    model's layers (a name list, as Unsloth takes, also matches a vision
    tower's ``q_proj`` or ``out_proj``)."""
    import re
    adapted = sorted({name.rsplit(".lora_A", 1)[0] for name, _ in model.named_modules() if ".lora_A" in name})
    stray = [n for n in adapted if not re.fullmatch(TARGETS, n) or "vis" in n.lower()]
    if stray or not adapted:
        raise SystemExit(f"the adapter is on {len(stray)} module(s) outside the language model's layers "
                         f"(of {len(adapted)}); first: {stray[:3]}")
    kinds: Dict[str, int] = {}
    for n in adapted:
        kinds[n.rsplit(".", 1)[1]] = kinds.get(n.rsplit(".", 1)[1], 0) + 1
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"modules": len(adapted), "by_kind": kinds, "trainable_parameters": trainable,
            "parameters": sum(p.numel() for p in model.parameters())}


def tiny_model(spec: str):
    """A random Qwen3.5-shaped model for checking the loop on a CPU
    (``--tiny 256x4``: width 256, 4 layers, the last full attention)."""
    from transformers.models.qwen3_5 import Qwen3_5ForCausalLM, Qwen3_5TextConfig
    width, layers = (int(x) for x in spec.split("x"))
    cfg = Qwen3_5TextConfig(hidden_size=width, intermediate_size=2 * width, num_hidden_layers=layers,
                            num_attention_heads=2, num_key_value_heads=1, head_dim=128,
                            linear_key_head_dim=64, linear_value_head_dim=64, linear_num_key_heads=2,
                            linear_num_value_heads=4,
                            layer_types=["linear_attention"] * (layers - 1) + ["full_attention"])
    import torch
    torch.manual_seed(0)
    return Qwen3_5ForCausalLM(cfg)


def chunked_loss(hidden, lm_head, labels, chunk: int = 4096):
    """Summed cross-entropy of the next token at every position whose next
    token is trained, the logits built a chunk of positions at a time and
    recomputed in the backward pass (a 122k-token sequence's full logits over
    248k tokens would be ~60 GB).  Returns (sum, count)."""
    import torch
    import torch.nn.functional as F
    from torch.utils.checkpoint import checkpoint
    tgt = labels[1:]
    pos = (tgt != tr.IGNORE).nonzero(as_tuple=True)[0]
    if pos.numel() == 0:
        return hidden.sum() * 0.0, 0
    h, y = hidden[:-1][pos], tgt[pos]

    def piece(hh, yy):
        return F.cross_entropy(lm_head(hh).float(), yy, reduction="sum")

    total = hidden.new_zeros((), dtype=torch.float32)
    for s in range(0, pos.numel(), chunk):
        total = total + checkpoint(piece, h[s:s + chunk], y[s:s + chunk], use_reentrant=False)
    return total, int(pos.numel())


def step_loss(model, ex, args, device):
    """(summed loss, trained tokens) of one sequence."""
    import torch
    ids = torch.as_tensor(ex["input_ids"], dtype=torch.long, device=device)[None]
    labels = torch.as_tensor(ex["labels"], dtype=torch.long, device=device)
    if args.engine == "unsloth" and args.loss == "engine":
        out = model(input_ids=ids, labels=labels[None])
        n = int((labels[1:] != tr.IGNORE).sum())
        return out.loss.float() * n, n
    base = model.get_base_model()
    inner = base.model
    hidden = inner(input_ids=ids, use_cache=False).last_hidden_state[0]
    return chunked_loss(hidden, base.lm_head, labels)


# ------------------------------------------------------------ the loop

STATE = "trainer_state.pt"


def host_peak_gib() -> float:
    """The process's peak resident memory (Unsloth's checkpointing keeps the
    saved activations here, about 32 GB at 122k tokens)."""
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (2**30 if sys.platform == "darwin" else 2**20), 2)


def epoch_order(examples: List[dict], args, epoch: int) -> List[dict]:
    """The order of an epoch: a shuffle that depends only on the seed and the
    epoch's number, so a resumed run takes up the same order.  The smoke's
    first epoch starts with its longest sequences."""
    rng = random.Random(f"{args.seed}:{epoch}")
    order = sorted(examples, key=lambda ex: ex["id"])
    rng.shuffle(order)
    if args.smoke and epoch == 0:
        order.sort(key=lambda ex: ex["tokens"], reverse=True)
        head, tail = order[:SMOKE_LONGEST], order[SMOKE_LONGEST:]
        rng.shuffle(tail)
        order = head + tail
    return order


def evaluate(model, val: List[dict], args, device) -> dict:
    """The loss a trained token on the validation sequences, no gradient."""
    import torch
    was_training = model.training
    model.eval()
    t0, total, n = time.time(), 0.0, 0
    with torch.no_grad():
        for ex in val:
            loss_sum, k = step_loss(model, ex, args, device)
            total += float(loss_sum)
            n += k
    if was_training:
        model.train()
    return {"eval_loss": total / n if n else None, "eval_sequences": len(val), "eval_trained_tokens": n,
            "eval_tokens": sum(ex["tokens"] for ex in val), "eval_seconds": round(time.time() - t0, 1)}


def save_checkpoint(model, opt, path: Path, state: dict) -> None:
    """The adapter, then the optimizer and the place in the run; the state
    file is written last, so a checkpoint that has one is whole."""
    import torch
    model.save_pretrained(str(path))
    tmp = path / (STATE + ".tmp")
    torch.save(dict(state, optimizer=opt.state_dict()), str(tmp))
    os.replace(tmp, path / STATE)


def load_checkpoint(model, path: Path) -> dict:
    """Load a checkpoint's adapter into ``model`` and return its state."""
    import torch
    from peft.utils import load_peft_weights, set_peft_model_state_dict
    if not (path / STATE).exists():
        raise SystemExit(f"{path} has no {STATE}: not a whole checkpoint of this script")
    set_peft_model_state_dict(model, load_peft_weights(str(path), device="cpu"))
    return torch.load(str(path / STATE), map_location="cpu", weights_only=False)


def train(model, examples: List[dict], args, out: Path, log, val: Sequence[dict] = (),
          resume: Optional[dict] = None) -> dict:
    import torch
    device = next(model.parameters()).device
    params = [p for p in model.parameters() if p.requires_grad]
    if args.optim == "adamw8bit":
        import bitsandbytes as bnb
        opt = bnb.optim.AdamW8bit(params, lr=args.lr, weight_decay=args.weight_decay, betas=(0.9, 0.999))
    else:
        opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=args.weight_decay)
    per_epoch = math.ceil(len(examples) / args.grad_accum)
    total = per_epoch * args.epochs if not args.max_steps else args.max_steps
    warm = max(1, int(args.warmup * total))

    def lr_at(s):
        if s < warm:
            return args.lr * (s + 1) / warm
        return args.lr * 0.5 * (1 + math.cos(math.pi * min(1.0, (s - warm) / max(1, total - warm))))

    shape = {"sequences": len(examples), "grad_accum": args.grad_accum, "seed": args.seed,
             "smoke": bool(args.smoke), "total_steps": total}
    cuda = torch.cuda.is_available()
    step, seen_tokens, first_epoch, first_window, before = 0, 0, 0, 0, 0.0
    if resume:
        if resume["shape"] != shape:
            raise SystemExit(f"the checkpoint was written by another run: {resume['shape']} != {shape}")
        opt.load_state_dict(resume["optimizer"])
        step, seen_tokens, before = resume["step"], resume["tokens"], resume["seconds"]
        first_epoch, first_window = resume["epoch"], resume["window"]
    started = time.time()

    def place(epoch, window):
        return {"shape": shape, "step": step, "tokens": seen_tokens, "epoch": epoch, "window": window,
                "seconds": round(before + time.time() - started, 1)}

    def report(row):
        log.write(json.dumps(row) + "\n")
        log.flush()
        print(json.dumps(row), flush=True)

    model.train()
    if val and not resume:
        report(dict(evaluate(model, val, args, device), step=0, epoch=0))
    for epoch in range(first_epoch, args.epochs):
        order = epoch_order(examples, args, epoch)
        windows = [order[s:s + args.grad_accum] for s in range(0, len(order), args.grad_accum)]
        next_window = len(windows)
        for w, window in enumerate(windows):
            if epoch == first_epoch and w < first_window:
                continue
            if args.max_steps and step >= args.max_steps:
                next_window = w
                break
            for g in opt.param_groups:
                g["lr"] = lr_at(step)
            if cuda:
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
            t0 = time.time()
            n_window = sum(ex["trained"] for ex in window) or 1
            loss_total, toks = 0.0, 0
            for ex in window:
                loss_sum, _ = step_loss(model, ex, args, device)
                if not bool(torch.isfinite(loss_sum)):
                    raise SystemExit(f"the loss of {ex['id']} ({ex['tokens']} tokens) is {float(loss_sum)}")
                (loss_sum / n_window).backward()
                loss_total += float(loss_sum.detach())
                toks += ex["tokens"]
            gnorm = torch.nn.utils.clip_grad_norm_(params, args.max_grad_norm)
            opt.step()
            opt.zero_grad(set_to_none=True)
            if cuda:
                torch.cuda.synchronize()
            dt = time.time() - t0
            step += 1
            seen_tokens += toks
            report({"step": step, "epoch": epoch, "loss": loss_total / n_window, "lr": lr_at(step - 1),
                    "grad_norm": float(gnorm), "sequences": len(window), "tokens": toks,
                    "longest": max(ex["tokens"] for ex in window), "trained_tokens": n_window,
                    "seconds": round(dt, 2), "tokens_per_second": round(toks / dt, 1) if dt else None,
                    "peak_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2) if cuda else None,
                    "reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 2) if cuda else None,
                    "host_peak_gib": host_peak_gib(),
                    "elapsed": round(before + time.time() - started, 1)})
            if val and args.eval_steps and step % args.eval_steps == 0:
                report(dict(evaluate(model, val, args, device), step=step, epoch=epoch))
            if args.save_steps and step % args.save_steps == 0 and w + 1 < len(windows):
                save_checkpoint(model, opt, out / f"checkpoint-{step}", place(epoch, w + 1))
        if val and not (args.eval_steps and step % args.eval_steps == 0):
            report(dict(evaluate(model, val, args, device), step=step, epoch=epoch))
        whole = next_window == len(windows)
        save_checkpoint(model, opt, out / f"checkpoint-{step}",
                        place(epoch + 1, 0) if whole else place(epoch, next_window))
        if args.max_steps and step >= args.max_steps:
            break
    model.save_pretrained(str(out / "adapter"))
    secs = before + time.time() - started
    return {"steps": step, "tokens": seen_tokens, "seconds": round(secs, 1),
            "tokens_per_second": round(seen_tokens / secs, 1) if secs else None}


# ------------------------------------------------------------ main

def parse(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", type=Path, required=True, help="results/training: the conversations, tools.json, tokens.json")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sets", nargs="*", default=[], help="file-name globs, e.g. 'd1-train-hard-*' (default: all)")
    p.add_argument("--faults", choices=("with", "none", "only"), default="with",
                   help="the faulted copies beside the references, or not")
    p.add_argument("--limit", type=int, help="the first N conversations after shuffling (seeded)")
    p.add_argument("--smoke", action="store_true", help=f"{SMOKE} conversations, the {SMOKE_LONGEST} longest first, one epoch")
    p.add_argument("--prepare-only", action="store_true", help="build the sequences and count them; load no model")
    p.add_argument("--model", default=BASE)
    p.add_argument("--revision", default=REVISION)
    p.add_argument("--tokenizer", help="repo id or folder (default: --model)")
    p.add_argument("--no-template-check", action="store_true", help="skip the chat-template hash check")
    p.add_argument("--thinking", choices=tr.THINKING, default="off",
                   help="the generation prompt the checkpoint will be served with (render check: off matches)")
    p.add_argument("--engine", choices=("unsloth", "hf"), default="unsloth")
    p.add_argument("--attn", default="sdpa", help="hf engine: attn_implementation")
    p.add_argument("--load-4bit", action="store_true", help="QLoRA: the base in 4-bit NF4")
    p.add_argument("--no-gradient-checkpointing", dest="gradient_checkpointing", action="store_false")
    p.add_argument("--tiny", help="a random Qwen3.5-shaped model, WIDTHxLAYERS (hf engine, CPU check)")
    p.add_argument("--max-seq-len", type=int, default=131072)
    p.add_argument("--grad-accum", type=int, default=8, help="sequences an optimizer step (one sequence a micro-step)")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--max-steps", type=int)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--warmup", type=float, default=0.03, help="fraction of the steps")
    p.add_argument("--weight-decay", type=float, default=0.0)
    p.add_argument("--max-grad-norm", type=float, default=1.0)
    p.add_argument("--optim", choices=("adamw", "adamw8bit"), default="adamw8bit")
    p.add_argument("--lora-r", type=int, default=32)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.0)
    p.add_argument("--save-steps", type=int, default=0,
                   help="a checkpoint every N steps (0: at the end of each epoch only; set it for a long run)")
    p.add_argument("--resume", type=Path, help="a checkpoint-<step> folder of this run to continue from")
    p.add_argument("--val-fraction", type=float, default=0.0,
                   help="share of the training tasks held out of training for the validation loss, by seed")
    p.add_argument("--val-max", type=int, default=24, help="validation conversations scored at each evaluation")
    p.add_argument("--eval-steps", type=int, default=0,
                   help="the validation loss every N steps (always before the first step and after each epoch)")
    p.add_argument("--loss", choices=("engine", "own"), default="engine",
                   help="unsloth engine: its own loss, or this script's chunked loss over the trained "
                        "positions (the hf engine always uses the latter)")
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = p.parse_args(argv)
    a.tokenizer = a.tokenizer or a.model
    a.target_names = ("q_proj", "k_proj", "v_proj", "o_proj", "in_proj_qkv", "in_proj_z", "out_proj",
                      "gate_proj", "up_proj", "down_proj")
    if a.smoke:
        a.epochs = 1
    if a.tiny:
        a.engine = "hf"
    return a


def main(argv=None) -> int:
    args = parse(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if args.engine == "unsloth" and not args.prepare_only:
        import unsloth  # noqa: F401  before transformers: it sets its patches up at import
    tok, sha = load_tokenizer(args.tokenizer, args.revision, not args.no_template_check)
    tools_doc = json.loads((args.data / "tools.json").read_text())
    lengths_path = args.data / "tokens.json"
    lengths = json.loads(lengths_path.read_text()).get("conversations", {}) if lengths_path.exists() else {}
    convs = read_conversations(args.data, args.sets, args.faults)
    convs, val_convs = split_validation(convs, args.val_fraction, args.val_max, seed=args.seed)
    if args.smoke:
        unsized = sum(1 for c in convs if c["id"] not in lengths)
        if unsized:
            print(f"warning: {unsized} of {len(convs)} conversations are not in tokens.json, so the smoke "
                  "cannot rank them: run scripts/training_tokens.py on this folder first", flush=True)
        convs = smoke_pick(convs, lengths, seed=args.seed)
    elif args.limit:
        random.Random(args.seed).shuffle(convs)
        convs = convs[:args.limit]
    print(f"{len(convs)} conversations, {len(val_convs)} for validation", flush=True)
    rows = prepare(convs, tools_doc, args, keep_ids=not args.prepare_only)
    st = stats(rows, convs)
    val_rows = prepare(val_convs, tools_doc, args, keep_ids=not args.prepare_only) if val_convs else []
    if val_convs:
        st["validation"] = stats(val_rows, val_convs)
    (args.out / "prepared.json").write_text(json.dumps(dict(st, prepared_seconds=round(time.time() - started, 1),
                                                            thinking=args.thinking, template_sha256=sha,
                                                            max_seq_len=args.max_seq_len), indent=1) + "\n")
    print(json.dumps(st), flush=True)
    run = {"args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
           "template_sha256": sha, "prepared": st}
    if args.prepare_only:
        (args.out / "run.json").write_text(json.dumps(run, indent=1) + "\n")
        return 0
    examples, val = usable(rows), usable(val_rows)
    import torch
    import transformers
    run["versions"] = {"torch": torch.__version__, "transformers": transformers.__version__,
                       "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    try:
        import peft
        run["versions"]["peft"] = peft.__version__
        if args.engine == "unsloth":
            import unsloth
            run["versions"]["unsloth"] = unsloth.__version__
    except Exception:   # noqa: BLE001
        pass
    t0 = time.time()
    model = load_model(args)
    run["load_seconds"] = round(time.time() - t0, 1)
    run["adapter"] = adapter_summary(model)
    print(json.dumps(run["adapter"]), flush=True)
    resume = load_checkpoint(model, args.resume) if args.resume else None
    with (args.out / "metrics.jsonl").open("a") as log:
        run["train"] = train(model, examples, args, args.out, log, val=val, resume=resume)
    run["seconds"] = round(time.time() - started, 1)
    (args.out / "run.json").write_text(json.dumps(run, indent=1) + "\n")
    print(json.dumps(run["train"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

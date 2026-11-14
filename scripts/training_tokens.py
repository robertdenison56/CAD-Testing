"""Count the training conversations' tokens with the subject model's
tokenizer (training plan section 5, step 3: the token histogram that sizes T1).

Standalone on purpose: it needs ``tokenizers``, ``gguf`` and ``jinja2``,
which the repo's venv does not carry, so it imports nothing of ``roaddraft``
and runs under any Python that has them (Unsloth Studio's does)::

    PYTHON -I scripts/training_tokens.py results/training

The subject is Qwen3.5 9B.  By default its tokenizer is the model's own
``tokenizer.json`` and its chat template the model's ``chat_template.jinja``
(both from the ``Qwen/Qwen3.5-9B`` repo on Hugging Face, kept in
``~/.roaddraft/tokenizers/Qwen3.5-9B``; they count LM Studio's prompts for
the 9B to the token).  Without them, ``--gguf`` builds it from a GGUF
vocabulary (byte-level BPE with the ``qwen35`` pre-tokenizer, as llama.cpp
reads it), which ran 1-2% low.
Qwen's chat markers (``<|im_start|>``, ``<tool_call>``, ``<think>`` ...) are
one token each, as in the model's own tokenizer.  Each conversation is
rendered through Qwen3.5's chat template with its tools, without a
generation prompt: the training sequence.

Writes ``tokens.json`` beside the conversations: per conversation id,
``[total, prompt, assistant]``: the whole sequence, the fixed part (system
with the tools, and the task), and the assistant turns (the loss).

``--calibrate FILE`` checks the count against a server's: FILE holds
conversations converted from a model's episodes, whose headers carry the
prompt tokens the server reported for each request (``prompt_tokens``); each
request is rendered as it was sent (the conversation up to that assistant
turn, with the generation prompt) and counted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

HOME = Path.home()
#: the 9B's own tokenizer and chat template (Qwen/Qwen3.5-9B on Hugging Face, SOURCE.json beside them)
MODEL = HOME / ".roaddraft" / "tokenizers" / "Qwen3.5-9B"
TOKENIZER = MODEL / "tokenizer.json"
TEMPLATE = MODEL / "chat_template.jinja"
GGUF = HOME / ".unsloth" / "llama.cpp" / "models" / "ggml-vocab-qwen35.gguf"
#: the Qwen3.5 pre-tokenizer (llama.cpp's LLAMA_VOCAB_PRE_TYPE_QWEN35, from the model's tokenizer.json)
QWEN35_SPLIT = (r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?[\p{L}\p{M}]+|\p{N}"
                r"| ?[^\s\p{L}\p{M}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+")
#: Qwen's chat markers: one token each in the model's tokenizer
MARKERS = ("<|endoftext|>", "<|im_start|>", "<|im_end|>", "<tool_call>", "</tool_call>",
           "<tool_response>", "</tool_response>", "<think>", "</think>",
           "<|vision_start|>", "<|vision_end|>", "<|image_pad|>", "<|video_pad|>")
#: blocks longer than this are cached by text (the system block, shared by every conversation)
CACHE_CHARS = 20000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shown(path: Path) -> str:
    p = Path(path).expanduser().resolve()
    try:
        return "~/" + str(p.relative_to(HOME))
    except ValueError:
        return str(p)


def tokenizer_from_gguf(path: Path):
    """A byte-level BPE tokenizer from a GGUF vocabulary (tokens, merges)."""
    from gguf import GGUFReader
    from tokenizers import AddedToken, Regex, Tokenizer, decoders, models, pre_tokenizers
    reader = GGUFReader(str(path))
    field = lambda k: reader.fields[k].contents()  # noqa: E731
    pre = field("tokenizer.ggml.pre")
    if pre != "qwen35":
        raise SystemExit(f"{path}: pre-tokenizer {pre!r}, not qwen35")
    tokens = field("tokenizer.ggml.tokens")
    types = field("tokenizer.ggml.token_type")
    merges = [tuple(m.split(" ", 1)) for m in field("tokenizer.ggml.merges")]
    tok = Tokenizer(models.BPE(vocab={t: i for i, t in enumerate(tokens)}, merges=merges))
    # no normalizer: Qwen3.5 keeps combining marks apart (its pre-tokenizer takes \p{M} with letters)
    tok.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.Split(Regex(QWEN35_SPLIT), behavior="isolated", invert=False),
        pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)])
    tok.decoder = decoders.ByteLevel()
    control = [t for t, ty in zip(tokens, types) if ty in (3, 4) and not t.startswith("[PAD")]
    added = sorted(set(control) | set(MARKERS))
    tok.add_special_tokens([AddedToken(t, special=True, normalized=False) for t in added])
    return tok, {"description": "the Qwen3.5 tokenizer (byte-level BPE, the qwen35 pre-tokenizer) "
                                "built from llama.cpp's qwen35 vocabulary",
                 "source": shown(path), "sha256": sha256_file(path), "vocab": len(tokens),
                 "added": added}


def tokenizer_from_json(path: Path):
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(path))
    info = {"description": "the tokenizer in tokenizer.json", "source": shown(path),
            "sha256": sha256_file(path), "vocab": tok.get_vocab_size()}
    source = path.parent / "SOURCE.json"   # where it was downloaded from, when that was recorded
    if source.exists():
        info["from"] = json.loads(source.read_text())
        info["description"] = (f"{info['from']['repo']}'s own tokenizer (Hugging Face, revision "
                               f"`{info['from']['revision'][:8]}`)")
    return tok, info


def check_vectors(tok, gguf: Path) -> dict:
    """llama.cpp's tokenizer test strings for the vocabulary, when it ships them."""
    inp, out = Path(str(gguf) + ".inp"), Path(str(gguf) + ".out")
    if not (inp.exists() and out.exists()):
        return {}
    texts = inp.read_text(encoding="utf-8").split("\n__ggml_vocab_test__\n")
    wants = out.read_text(encoding="utf-8").split("\n")
    n = min(len(texts), len(wants))
    same = sum(tok.encode(t, add_special_tokens=False).ids == [int(x) for x in w.split()]
               for t, w in zip(texts[:n], wants[:n]))
    return {"tested": n, "same": same}


def template_from(path: Path):
    import jinja2
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    def raise_exception(message):
        raise jinja2.exceptions.TemplateError(message)

    def tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False):
        # as transformers' chat-template renderer has it
        return json.dumps(x, ensure_ascii=ensure_ascii, indent=indent, separators=separators,
                          sort_keys=sort_keys)

    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                        extensions=["jinja2.ext.loopcontrols"])
    env.filters["tojson"] = tojson
    env.globals["raise_exception"] = raise_exception
    text = Path(path).read_text(encoding="utf-8")
    return env.from_string(text), {"description": "Qwen3.5's chat template",
                                   "source": shown(path), "sha256": hashlib.sha256(text.encode()).hexdigest()}


class Counter:
    def __init__(self, tok):
        self.tok = tok
        self.cache = {}

    def count(self, text: str) -> int:
        if len(text) >= CACHE_CHARS:
            if text not in self.cache:
                self.cache[text] = len(self.tok.encode(text, add_special_tokens=False).ids)
            return self.cache[text]
        return len(self.tok.encode(text, add_special_tokens=False).ids)

    def blocks(self, rendered: str):
        """(role, tokens) of each chat block: split before every <|im_start|>,
        an added token, so the counts add up to the whole text's."""
        parts = rendered.split("<|im_start|>")
        out = []
        if parts[0]:
            out.append(("", self.count(parts[0])))
        small = ["<|im_start|>" + p for p in parts[1:]]
        sizes = {}
        uncached = [i for i, b in enumerate(small) if len(b) < CACHE_CHARS]
        for i, enc in zip(uncached, self.tok.encode_batch([small[i] for i in uncached],
                                                           add_special_tokens=False)):
            sizes[i] = len(enc.ids)
        for i, b in enumerate(small):
            n = sizes[i] if i in sizes else self.count(b)
            role = b[len("<|im_start|>"):].split("\n", 1)[0]
            out.append((role, n))
        return out


def count_conversation(counter: Counter, template, conv: dict, tools: list):
    text = template.render(messages=conv["messages"], tools=tools, add_generation_prompt=False)
    blocks = counter.blocks(text)
    total = sum(n for _, n in blocks)
    # the fixed part: the system block (with the tools) and the task, the first user block
    prompt, users = 0, 0
    for role, n in blocks:
        if role == "system":
            prompt += n
        elif role == "user" and users == 0:
            prompt += n
            users += 1
        elif role == "assistant":
            break
    # the loss: every assistant block but those of a message with weight 0 (an injected fault's
    # broken turn); the template writes one block per assistant message, in order
    said = [n for role, n in blocks if role == "assistant"]
    weights = [m.get("weight", 1) for m in conv.get("messages") or [] if m.get("role") == "assistant"]
    if len(weights) != len(said):
        weights = [1] * len(said)
    assistant = sum(n for n, wt in zip(said, weights) if wt != 0)
    return [total, prompt, assistant]


def least_squares(xs: list, ys: list) -> list:
    """Coefficients of ``y ~ x`` (each x a row with a constant term), by the
    normal equations: a few unknowns, no numpy."""
    k = len(xs[0])
    a = [[sum(r[i] * r[j] for r in xs) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * y for r, y in zip(xs, ys)) for i in range(k)]
    for c in range(k):      # Gauss-Jordan with partial pivoting
        p = max(range(c, k), key=lambda r: abs(a[r][c]))
        a[c], a[p], b[c], b[p] = a[p], a[c], b[p], b[c]
        if abs(a[c][c]) < 1e-12:
            return [0.0] * k
        for r in range(k):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
                b[r] -= f * b[c]
    return [b[i] / a[i][i] for i in range(k)]


def calibrate(counter: Counter, template, path: Path, tools_doc: dict) -> dict:
    """Each request of each conversation counted here against the server's
    count; and how the gap grows with the calls and arguments the request
    holds (``gap ~ calls + arguments + 1``)."""
    deltas, rows = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        conv = json.loads(line)
        held = conv["header"].get("prompt_tokens") or []
        tools = tools_doc[conv["header"]["tools_sha256"]]["function_tools"]
        msgs = conv["messages"]
        at = [i for i, m in enumerate(msgs) if m["role"] == "assistant"]
        for k, i in enumerate(at):
            if k >= len(held) or not held[k]:
                continue
            text = template.render(messages=msgs[:i], tools=tools, add_generation_prompt=True)
            n = sum(c for _, c in counter.blocks(text))
            calls = [c for m in msgs[:i] if m["role"] == "assistant" for c in m.get("tool_calls") or []]
            deltas.append(n - held[k])
            rows.append({"id": conv["id"], "request": k + 1, "counted": n, "server": held[k],
                         "calls": len(calls),
                         "arguments": sum(len(c["function"]["arguments"] or {}) for c in calls)})
    if not deltas:
        return {}
    rel = [abs(r["counted"] - r["server"]) / r["server"] for r in rows]
    per_call, per_arg, const = least_squares([[r["calls"], r["arguments"], 1.0] for r in rows],
                                             [r["server"] - r["counted"] for r in rows])
    return {"source": str(path), "requests": len(rows), "conversations": len({r["id"] for r in rows}),
            "delta": {"min": min(deltas), "median": statistics.median(deltas), "max": max(deltas)},
            "worst_relative": max(rel),
            "server_minus_counted": {"per_call": round(per_call, 2), "per_argument": round(per_arg, 2),
                                     "constant": round(const, 1)},
            "rows": rows[:300],
            "text": _calibration_text(rows, deltas, rel, per_call, per_arg)}


def _calibration_text(rows, deltas, rel, per_call, per_arg) -> str:
    first = rows[0]
    said = (f"{len(rows)} requests of {len({r['id'] for r in rows})} Qwen3.5 9B episodes, each rendered as "
            f"the harness sent it and counted here, against the prompt tokens LM Studio reported. The first "
            f"request ({first['server']:,} tokens at the server) counts {first['counted']:,} here.")
    if not any(deltas):
        return said + " Every request counts exactly what the server reported, so the totals below are exact."
    side = "low" if statistics.median(deltas) < 0 else "high"
    return said + (f" The count runs {side}: {min(deltas):+,} to {max(deltas):+,} tokens against the server "
                   f"(at most {100 * max(rel):.2f}% of a request), growing by about {-per_call:+.1f} tokens a "
                   f"tool call and {-per_arg:+.1f} an argument (least squares over the requests), so the "
                   f"totals below are off by about that much on long conversations.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=Path, help="results/training: the conversations and tools.json")
    parser.add_argument("--gguf", type=Path, nargs="?", const=GGUF, default=None,
                        help="build the tokenizer from a GGUF vocabulary instead of a tokenizer.json")
    parser.add_argument("--tokenizer", type=Path, default=TOKENIZER, help="the model's tokenizer.json")
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    parser.add_argument("--calibrate", type=Path, help="conversations with server prompt counts")
    parser.add_argument("--calibration-only", action="store_true",
                        help="update the calibration in tokens.json and count nothing else")
    args = parser.parse_args(argv)
    folder = args.folder
    tok, tk_info = (tokenizer_from_gguf(args.gguf) if args.gguf
                    else tokenizer_from_json(args.tokenizer))
    if args.gguf:
        tk_info["test_vectors"] = check_vectors(tok, args.gguf)
    template, tp_info = template_from(args.template)
    counter = Counter(tok)
    tools_doc = json.loads((folder / "tools.json").read_text())
    out_path = folder / "tokens.json"
    doc = json.loads(out_path.read_text()) if out_path.exists() else {}
    doc.update({"tokenizer": tk_info, "template": tp_info})
    if args.calibrate:
        # a model's episodes may have run on another tool set: a tools.json beside them names it
        beside = args.calibrate.parent / "tools.json"
        known = dict(tools_doc, **(json.loads(beside.read_text()) if beside.exists() else {}))
        doc["calibration"] = calibrate(counter, template, args.calibrate, known)
        print(doc["calibration"].get("text", "calibration: no request carried a server count"))
    if not args.calibration_only:
        counts, started = {}, time.time()
        for path in sorted(folder.glob("*.jsonl")):
            n = 0
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    conv = json.loads(line)
                    tools = tools_doc[conv["header"]["tools_sha256"]]["function_tools"]
                    counts[conv["id"]] = count_conversation(counter, template, conv, tools)
                    n += 1
            print(f"{path.name}: {n} conversations", flush=True)
        doc["conversations"] = counts
        doc["counted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        doc["seconds"] = round(time.time() - started, 1)
    out_path.write_text(json.dumps(doc, indent=None, separators=(",", ":")) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

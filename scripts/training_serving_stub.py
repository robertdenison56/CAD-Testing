"""A stand-in GGUF for the serving side of the render check
(``scripts/training_render_check.py``): Qwen3.5's own tokenizer and chat
template on a one-layer, 64-wide random body.

The PC serves the 9B from a GGUF through LM Studio's llama.cpp engine, which
renders each chat request with llama.cpp's own Jinja engine (``jinja::`` in
the backend's ``libllm_engine.dylib``, through
``common_chat_templates_apply_jinja``) and tokenizes it with llama.cpp's
tokenizer.  LM Studio ships the same engine as a ``llama-server`` binary in
its backend folder, and llama-server has ``/apply-template`` (the prompt a
chat request renders to, nothing generated) and ``/tokenize``.  Both need a
model loaded; this file is the smallest one that carries the 9B's vocabulary
and template, so the server renders and tokenizes exactly as for the 9B
without the 5.6 GB of weights.

The vocabulary is written the way llama.cpp's ``convert_hf_to_gguf.py`` writes
a Qwen3.5 one (``gpt2`` model, ``qwen35`` pre-tokenizer, added tokens as
control or user-defined); the template is the model's ``chat_template.jinja``
unless ``--template`` names another.

    PYTHON -I scripts/training_serving_stub.py OUT.gguf

Needs ``gguf`` and ``numpy`` (Unsloth Studio's Python has them).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODEL = Path.home() / ".roaddraft" / "tokenizers" / "Qwen3.5-9B"
WIDTH = 64


def build(out: Path, tokenizer_json: Path, template: Path) -> dict:
    import gguf
    import numpy as np

    tj = json.loads(Path(tokenizer_json).read_text(encoding="utf-8"))
    vocab = tj["model"]["vocab"]
    added = {a["id"]: a for a in tj["added_tokens"]}
    n = max(max(vocab.values()), max(added)) + 1
    tokens = [f"[PAD{i}]" for i in range(n)]
    types = [gguf.TokenType.UNUSED] * n
    for text, i in vocab.items():
        tokens[i], types[i] = text, gguf.TokenType.NORMAL
    for i, a in added.items():
        tokens[i] = a["content"]
        types[i] = gguf.TokenType.CONTROL if a["special"] else gguf.TokenType.USER_DEFINED
    merges = [m if isinstance(m, str) else " ".join(m) for m in tj["model"]["merges"]]
    ids = {t: i for i, t in enumerate(tokens)}

    w = gguf.GGUFWriter(str(out), "llama")
    w.add_name("qwen3.5-9b-serving-stub")
    w.add_block_count(1)
    w.add_context_length(131072)
    w.add_embedding_length(WIDTH)
    w.add_feed_forward_length(WIDTH)
    w.add_head_count(1)
    w.add_head_count_kv(1)
    w.add_rope_dimension_count(WIDTH)
    w.add_layer_norm_rms_eps(1e-6)
    w.add_file_type(gguf.LlamaFileType.ALL_F32)
    w.add_tokenizer_model("gpt2")
    w.add_tokenizer_pre("qwen35")
    w.add_token_list(tokens)
    w.add_token_types(types)
    w.add_token_merges(merges)
    w.add_eos_token_id(ids["<|im_end|>"])
    w.add_pad_token_id(ids["<|endoftext|>"])
    w.add_bos_token_id(ids["<|endoftext|>"])
    w.add_add_bos_token(False)
    w.add_chat_template(Path(template).read_text(encoding="utf-8"))
    rng = np.random.default_rng(0)
    f = lambda *shape: (rng.standard_normal(shape) * 0.02).astype(np.float32)  # noqa: E731
    w.add_tensor("token_embd.weight", f(n, WIDTH))
    w.add_tensor("output_norm.weight", np.ones(WIDTH, np.float32))
    w.add_tensor("blk.0.attn_norm.weight", np.ones(WIDTH, np.float32))
    w.add_tensor("blk.0.ffn_norm.weight", np.ones(WIDTH, np.float32))
    for name in ("attn_q", "attn_k", "attn_v", "attn_output", "ffn_gate", "ffn_up", "ffn_down"):
        w.add_tensor(f"blk.0.{name}.weight", f(WIDTH, WIDTH))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return {"tokens": n, "merges": len(merges), "out": str(out)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("out", type=Path)
    p.add_argument("--tokenizer", type=Path, default=MODEL / "tokenizer.json")
    p.add_argument("--template", type=Path, default=MODEL / "chat_template.jinja")
    a = p.parse_args(argv)
    print(json.dumps(build(a.out, a.tokenizer, a.template)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

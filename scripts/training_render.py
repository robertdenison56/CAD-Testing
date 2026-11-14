"""The training text of a RoadDraft conversation, and what in it is trained
(training plan section 3, *Format*; section 7, "training text differs from
what the server sends").

Shared by the trainer (``scripts/training_lora.py``) and the render check
(``scripts/training_render_check.py``).  Pure Python: the chat template is
passed in as a ``render`` function, so the logic is testable without
``jinja2``, ``tokenizers`` or a GPU.

**The rule.**  At eval the harness sends, before each assistant turn, the
conversation so far rendered through the chat template with the generation
prompt (``<|im_start|>assistant\\n<think>\\n`` with thinking on,
``... <think>\\n\\n</think>\\n\\n`` with it off), and the model writes the rest
of the turn up to ``<|im_end|>``.  A training sequence is right when, for
every turn it trains, the text before the turn's target is exactly that
prompt, and the target is exactly what the model would have to write.

**Segments.**  One render of the whole conversation satisfies the rule for
most conversations, so a conversation is normally one sequence.  It fails
for the turns before a ``[harness]`` note: the note is a user message, so
Qwen3.5's template moves its "last query" there and renders the assistant
turns before it *without* their ``<think></think>`` block, while the model
wrote each of them after a prompt that had one.  Those turns are trained in
a shorter sequence that ends where they do (``plan_segments``), and the
whole conversation trains the turns after the note.

**Targets.**  A turn's target runs from the end of its prompt to its
``<|im_end|>`` (inclusive).  With ``thinking="off"`` the empty think block is
prompt, so the target starts at the turn's text or its first
``<tool_call>``.  With ``thinking="on"`` the prompt ends at ``<think>\\n`` and
the target starts with the ``\\n</think>\\n\\n`` that closes the block; the
tokenizer writes ``<think>\\n\\n</think>`` as ``<think>``, ``\\n\\n``,
``</think>``, so the token holding the boundary is context and the first
trained token is ``</think>`` (the check reports this).  An assistant
message with ``"weight": 0`` (an injected fault's broken turn) is never a
target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ASSISTANT_OPEN = "<|im_start|>assistant\n"
IM_END = "<|im_end|>"
IGNORE = -100
THINKING = ("off", "on")

#: render(messages, add_generation_prompt) -> text; the tools and enable_thinking are bound in
Render = Callable[[Sequence[dict], bool], str]
#: encode(text) -> (ids, offsets), offsets as (start, end) character spans of each token
Encode = Callable[[str], Tuple[List[int], List[Tuple[int, int]]]]


@dataclass
class Segment:
    """One training sequence: its text and the character spans trained."""
    text: str
    turns: List[int] = field(default_factory=list)       # message indices of the assistant turns it trains
    masked: List[int] = field(default_factory=list)      # weight-0 turns it holds as context
    spans: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class Plan:
    segments: List[Segment]
    prompts: Dict[int, str]                              # message index -> the serving prompt before that turn
    inconsistent: List[int] = field(default_factory=list)  # turns whose prompt is not a prefix even of their own render


def assistant_indices(messages: Sequence[dict]) -> List[int]:
    return [i for i, m in enumerate(messages) if m.get("role") == "assistant"]


def weight(message: dict) -> float:
    w = message.get("weight", 1)
    return 1.0 if w is None else float(w)


def target_span(text: str, prompt: str) -> Tuple[int, int]:
    """The target of the turn that follows ``prompt`` in ``text``."""
    start = len(prompt)
    end = text.find(IM_END, start)
    if end < 0:
        raise ValueError("no <|im_end|> after the turn's prompt")
    return start, end + len(IM_END)


def plan_segments(messages: Sequence[dict], render: Render) -> Plan:
    """The sequences that train every assistant turn of a conversation under
    the rule above, the fewest first: the whole conversation, then for any
    turn it cannot hold, the conversation cut after the latest such turn, and
    so on."""
    turns = assistant_indices(messages)
    prompts = {i: render(list(messages[:i]), True) for i in turns}
    left = list(turns)
    segments: List[Segment] = []
    inconsistent: List[int] = []
    cut = len(messages)
    while left:
        text = render(list(messages[:cut]), False)
        held = [i for i in left if text.startswith(prompts[i])]
        if not held:   # the latest turn left is not even a prefix of its own render: train it there anyway
            i = left[-1]
            inconsistent.append(i)
            held = [i]
        seg = Segment(text=text)
        for i in held:
            if weight(messages[i]) == 0:
                seg.masked.append(i)
                continue
            if i in inconsistent:
                start = text.rfind(ASSISTANT_OPEN) + len(ASSISTANT_OPEN)
                end = text.find(IM_END, start) + len(IM_END)
                seg.spans.append((start, end))
            else:
                seg.spans.append(target_span(text, prompts[i]))
            seg.turns.append(i)
        segments.append(seg)
        left = [i for i in left if i not in held]
        if left:
            cut = left[-1] + 1
    segments.reverse()   # in conversation order
    return Plan(segments=segments, prompts=prompts, inconsistent=inconsistent)


def labels_for(text: str, spans: Sequence[Tuple[int, int]], encode: Encode) -> Tuple[List[int], List[int]]:
    """Token ids of ``text`` and their labels: the id where the token lies
    wholly inside a trained span, ``IGNORE`` elsewhere (a token straddling a
    span's start is context)."""
    ids, offsets = encode(text)
    labels = [IGNORE] * len(ids)
    spans = sorted(spans)
    k = 0
    for t, (a, b) in enumerate(offsets):
        while k < len(spans) and spans[k][1] <= a:
            k += 1
        if k < len(spans) and spans[k][0] <= a and b <= spans[k][1] and b > a:
            labels[t] = ids[t]
    return ids, labels


def trained_text(text: str, ids: Sequence[int], labels: Sequence[int],
                 offsets: Sequence[Tuple[int, int]]) -> str:
    """The characters the labels train, for checking a mask by eye."""
    return "".join(text[a:b] for (a, b), lab in zip(offsets, labels) if lab != IGNORE)


def strip_for_request(messages: Sequence[dict]) -> List[dict]:
    """The messages as the harness sends them to an OpenAI-compatible server:
    no training-only keys, each call's arguments as a JSON string (what the
    server handed back and the harness returns unchanged)."""
    import json
    out = []
    for m in messages:
        m = {k: v for k, v in m.items() if k != "weight"}
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = dict(c["function"])
                if not isinstance(fn.get("arguments"), str):
                    fn["arguments"] = json.dumps(fn.get("arguments") or {}, ensure_ascii=False)
                calls.append(dict(c, function=fn))
            m["tool_calls"] = calls
        out.append(m)
    return out


# ------------------------------------------------------------ the tool-call parse, as the server does it

def parse_completion(completion: str, tools: Optional[Sequence[dict]] = None) -> dict:
    """Read a target back the way a Qwen3-Coder-format server parser does
    (llama.cpp's ``common_chat_params_init_qwen3_coder``, vLLM's
    ``qwen3_coder``): the text before the first ``<tool_call>``, then each
    call's name and parameters, a parameter's value taken as a string when
    its schema type is ``string`` and otherwise as JSON (Python's ``True``,
    ``False`` and ``None`` read as JSON's)."""
    import json
    import re
    types: Dict[str, Dict[str, object]] = {}
    for t in tools or []:
        fn = t.get("function", t)
        props = ((fn.get("parameters") or fn.get("input_schema") or {}).get("properties") or {})
        types[fn["name"]] = {k: (v or {}).get("type") for k, v in props.items()}
    body = completion
    if body.endswith(IM_END):
        body = body[: -len(IM_END)]
    if "</think>" in body:
        body = body.split("</think>", 1)[1]
    text, _, rest = body.partition("<tool_call>")
    calls = []
    for block in re.findall(r"<function=([^>\n]+)>\n(.*?)</function>", "<tool_call>" + rest, re.S):
        name, inner = block
        args = {}
        for pname, raw in re.findall(r"<parameter=([^>\n]+)>\n(.*?)\n</parameter>", inner, re.S):
            kind = types.get(name, {}).get(pname)
            if kind == "string" or (isinstance(kind, list) and kind == ["string"]):
                args[pname] = raw
                continue
            try:
                args[pname] = json.loads(raw)
            except ValueError:
                fixed = re.sub(r"\bTrue\b", "true", re.sub(r"\bFalse\b", "false", re.sub(r"\bNone\b", "null", raw)))
                try:
                    args[pname] = json.loads(fixed)
                except ValueError:
                    args[pname] = raw
        calls.append({"name": name, "arguments": args})
    return {"content": text.strip(), "tool_calls": calls}


def same_value(a, b) -> bool:
    """Equal as the bus would take them: 1 and 1.0 alike."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or (isinstance(a, bool) and isinstance(b, bool) and a == b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    return a == b


#: Qwen3.5's generation prompt, thinking on unless the request turns it off
GENERATION_SWITCH = ("    {%- if enable_thinking is defined and enable_thinking is false %}\n"
                     "        {{- '<think>\\n\\n</think>\\n\\n' }}\n"
                     "    {%- else %}\n"
                     "        {{- '<think>\\n' }}\n"
                     "    {%- endif %}\n")
GENERATION_CLOSED = "    {{- '<think>\\n\\n</think>\\n\\n' }}\n"


def nothink_template(template: str) -> str:
    """Qwen3.5's chat template with the generation prompt always closing the
    think block, whatever the request asks: the template a checkpoint trained
    with ``thinking="off"`` is served with, so the serving prompt is the
    training context without depending on a server passing
    ``enable_thinking``.  Everything else is unchanged."""
    if template.count(GENERATION_SWITCH) != 1:
        raise ValueError("the template's generation prompt is not Qwen3.5's: patch it by hand")
    return template.replace(GENERATION_SWITCH, GENERATION_CLOSED)


__all__ = ["nothink_template", "ASSISTANT_OPEN", "IM_END", "IGNORE", "Segment", "Plan", "plan_segments", "labels_for",
           "target_span", "strip_for_request", "parse_completion", "same_value", "trained_text",
           "assistant_indices", "weight"]

"""Enter a trained checkpoint in ``models.json`` so the local queue can run it (training plan, stage T1).

    python benchmarks/lmstudio/add_checkpoint.py NAME --lms-key KEY --check runs/x/gguf/check.json [--base qwen3.5-9b]

NAME is the short name the queue is given (``CKPT=NAME``), for example ``qwen3.5-9b-t1s``. KEY is the model key
``lms ls`` shows on the PC after ``lms import model-Q4_K_M.gguf``. The entry copies what a like-for-like run
needs from the base's entry (the sampling ``extra_body``, the context, the quantization) and records where the
file came from: the sha256 and the adapter from ``check.json`` (``scripts/training_merge_quantize.py``), or
``--sha256`` when there is no check file. ``vision`` is false: the merge drops the vision tower, so the queue
runs the text pilots only. The label, ``<NAME>-<quant>-lms``, is what the run ids and the board row carry; an
entry is never overwritten (``--replace`` to write it again).

Nothing is loaded and no server is asked: `lms_campaign.py check NAME` and `fit NAME` do that, on Robert's word.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

SPECS = Path(__file__).resolve().parent / "models.json"
CARRIED = ("quantization", "context", "extra_body")     # what makes the checkpoint's runs like the base's


def quant_tag(quantization: str) -> str:
    """``Q4_K_M`` -> ``q4km``, as the labels of the other entries spell it."""
    return quantization.lower().replace("_", "")


def entry(name: str, base_name: str, base: dict, lms_key: str, sha256: str = None, check: dict = None,
          note: str = None, today: str = None) -> dict:
    """The checkpoint's ``models.json`` entry, built from the base's."""
    missing = [k for k in CARRIED if k not in base]
    if missing:
        raise ValueError(f"the base entry {base_name!r} has no {', '.join(missing)}")
    check = check or {}
    sha = sha256 or check.get("gguf_sha256")
    e = {"name": f"{name} ({base['quantization']}, LM Studio; a trained checkpoint of {base_name})",
         "label": f"{name}-{quant_tag(base['quantization'])}-lms",
         "lms_key": lms_key}
    e.update({k: base[k] for k in CARRIED})
    e["vision"] = False
    e["checkpoint"] = {"base": base_name, "base_lms_key": base.get("lms_key"), "sha256": sha,
                       "adapter": check.get("adapter"), "thinking": "off (the no-think template is in the file)",
                       "added": today or datetime.date.today().isoformat()}
    if note:
        e["notes"] = note
    return e


def add(data: dict, name: str, base_name: str, lms_key: str, replace: bool = False, **kw) -> dict:
    models = data["models"]
    if base_name not in models:
        raise ValueError(f"no base model {base_name!r} in models.json; one of: {', '.join(models)}")
    if name in models and not replace:
        raise ValueError(f"{name!r} is in models.json already (--replace writes it again)")
    e = entry(name, base_name, models[base_name], lms_key, **kw)
    clash = [n for n, m in models.items() if n != name and (m.get("label") == e["label"] or m.get("lms_key") == lms_key)]
    if clash:
        raise ValueError(f"{', '.join(clash)} already carries the label {e['label']} or the key {lms_key}")
    models[name] = e
    return e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name")
    ap.add_argument("--lms-key", required=True, help="the model key `lms ls` shows on the PC")
    ap.add_argument("--base", default="qwen3.5-9b", help="the models.json name of the base it was trained from")
    ap.add_argument("--check", help="check.json written by scripts/training_merge_quantize.py")
    ap.add_argument("--sha256", help="the GGUF's sha256, when there is no check file")
    ap.add_argument("--note")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--specs", default=str(SPECS), help="the models.json to write (default: beside this script)")
    args = ap.parse_args(argv)
    specs = Path(args.specs)
    data = json.loads(specs.read_text())
    check = json.loads(Path(args.check).read_text()) if args.check else None
    try:
        e = add(data, args.name, args.base, args.lms_key, replace=args.replace, sha256=args.sha256, check=check,
                note=args.note)
    except ValueError as err:
        sys.exit(str(err))
    specs.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{args.name}: label {e['label']}, key {e['lms_key']}, context {e['context']:,}, text pilots only; "
          f"{specs} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())

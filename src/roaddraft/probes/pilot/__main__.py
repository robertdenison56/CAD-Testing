"""The harder-task pilots: list, set up, selftest and keep references.

    python -m roaddraft.probes.pilot list [--tag TAG]
    python -m roaddraft.probes.pilot setup ID --out DIR [--force]
    python -m roaddraft.probes.pilot selftest [ID ...] [--tag TAG]
    python -m roaddraft.probes.pilot reference --out benchmarks/pilot_references [ID ...]

``selftest`` is what keeps a pilot honest: its scripted solution must pass
its check, read back from the file it saved, and the untouched start must
fail it. ``reference`` keeps those solutions as finished projects (document,
journal, PDF, DXF), the way the 33 probes' references are kept.

To run a model on the pilots (only on Robert's go):

    python -m roaddraft.runners run --pilot --backend codex --model MODEL \\
        --out benchmarks/pilot_runs/<date>-<name> --label <label> [ID ...]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

from roaddraft.api.session import Session
from roaddraft.mcp import config as mcpconfig
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import PILOT_PROBES, BY_ID


def _chosen(ids, tag):
    unknown = [i for i in ids if i not in BY_ID]
    if unknown:
        raise SystemExit(f"no pilot {', '.join(unknown)}; pilots: {', '.join(BY_ID)}")
    return [p for p in PILOT_PROBES if (not ids or p.id in ids) and (not tag or tag in p.tags)]


def cmd_list(args) -> int:
    chosen = _chosen([], args.tag)
    for p in chosen:
        print(f"{p.id:32} {', '.join(p.tags):40} opens: {p.start}")
        print(f"  {p.prompt}")
        if p.note:
            print(f"  note: {p.note}")
        print()
    print(f"{len(chosen)} pilot probes")
    return 0


def cmd_setup(args) -> int:
    probe = BY_ID[args.probe]
    out = Path(args.out)
    if out.exists() and args.force:
        shutil.rmtree(out)
    doc = fixture.start_document(out, probe.start)
    extra = [a.replace("{project}", str(out.resolve())) for a in probe.server_args]
    print(f"project written to {out}\n  the document to open: {doc}\n")
    print(f"give the model this:\n  {probe.prompt}\n")
    print("point it at the project:")
    print("  " + mcpconfig.claude_mcp_add("roaddraft-pilot", mcpconfig.server_command(),
                                         mcpconfig.server_args(doc=str(doc), autosave=True) + extra))
    print(f"\nthen score it:\n  python -m roaddraft.probes score {probe.id} --doc {doc}")
    return 0


def cmd_selftest(args) -> int:
    chosen = [p for p in _chosen(args.probes, args.tag) if p.solve]
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        built = {}
        for probe in chosen:
            t0 = time.time()
            if probe.start not in built:
                built[probe.start] = Path(tmp) / "start" / probe.start
                fixture.start_document(built[probe.start], probe.start)
            start = built[probe.start]
            ref = reference.write(probe, Path(tmp) / probe.id, start, plots=False)
            mark = "ok  " if ref.result.passed else "FAIL"
            print(f"  {mark} {probe.id}: {ref.result.detail}  ({time.time() - t0:.0f} s)", flush=True)
            if not ref.result.passed:
                failures.append(probe.id)
            pristine = start / fixture.START[probe.start]
            empty = probe.check(Session.load(pristine, out_dir=start),
                                Session.load(pristine, out_dir=start))
            if empty.passed:
                print(f"  FAIL {probe.id}: the untouched start already passes")
                failures.append(probe.id + " (vacuous)")
    print(f"{len(chosen) - len(failures)}/{len(chosen)} pilot solutions pass and their "
          f"starts fail")
    return 1 if failures else 0


def cmd_reference(args) -> int:
    chosen = [p for p in _chosen(args.probes, args.tag) if p.solve]
    out = Path(args.out)
    failures = []
    for probe in chosen:
        folder = out / probe.id
        if folder.exists():
            if not (folder / reference.RECORD).exists():
                print(f"{folder} exists and was not written by this command")
                return 2
            shutil.rmtree(folder)
        ref = reference.write(probe, folder, plots=not args.no_plots)
        print(f"  {'ok  ' if ref.result.passed else 'FAIL'} {probe.id}: {folder / ref.document.name}",
              flush=True)
        if not ref.result.passed:
            print(f"       {ref.result.detail}")
            failures.append(probe.id)
    index = reference.write_index(out, shown=args.out)
    print(f"{len(chosen) - len(failures)}/{len(chosen)} pilot references pass; index: {index}")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.probes.pilot",
                                     description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command")
    lister = subs.add_parser("list")
    lister.add_argument("--tag")
    setup = subs.add_parser("setup")
    setup.add_argument("probe")
    setup.add_argument("--out", default="pilot_out")
    setup.add_argument("--force", action="store_true")
    st = subs.add_parser("selftest")
    st.add_argument("probes", nargs="*")
    st.add_argument("--tag")
    ref = subs.add_parser("reference")
    ref.add_argument("probes", nargs="*")
    ref.add_argument("--tag")
    ref.add_argument("--out", required=True)
    ref.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    handler = {"list": cmd_list, "setup": cmd_setup, "selftest": cmd_selftest,
               "reference": cmd_reference}.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())

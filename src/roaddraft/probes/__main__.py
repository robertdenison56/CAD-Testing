"""Run the probes: finding and annotating (T2), drafting from a description (T1),
the harder second tier of both (tier2), and a layout's line and curve data (tier3).

    python -m roaddraft.probes list [--tag draft|find|tier2|tier3]
    python -m roaddraft.probes setup edge-curve-c102 --out /tmp/probe
    python -m roaddraft.probes score edge-curve-c102 --doc /tmp/probe/SR-100.sheets.rdoc.json
    python -m roaddraft.probes selftest
    python -m roaddraft.probes reference --out benchmarks/probe_references

``setup`` writes a fresh copy of the project and prints the instruction to give
the model and the MCP command that points at it. Let the model work, then
``score`` the document it leaves behind. ``selftest`` runs the scripted solution
for every probe and scores the file it saves, which is what keeps the checks
honest. ``reference`` keeps those solutions: each probe's project, finished,
with its journal, a PDF and a DXF beside the completed document.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference, tasks


def _venv_bin() -> str:
    return str(Path(sys.executable).parent / "roaddraft-mcp")


def cmd_list(args) -> int:
    chosen = [p for p in tasks.PROBES if not args.tag or args.tag in p.tags]
    for probe in chosen:
        flag = "  [BLOCKED]" if probe.blocked_on else ""
        print(f"{probe.id:24} {', '.join(probe.tags):34} opens: {probe.start}{flag}")
        print(f"  {probe.prompt}")
        if probe.note:
            print(f"  note: {probe.note}")
        if probe.blocked_on:
            print(f"  blocked on: {probe.blocked_on}")
        print()
    blocked = sum(1 for p in chosen if p.blocked_on)
    print(f"{len(chosen)} probes, {blocked} blocked on a capability that does "
          f"not exist yet")
    return 0


def cmd_setup(args) -> int:
    probe = tasks.get(args.probe)
    out = Path(args.out)
    if out.exists() and args.force:
        shutil.rmtree(out)
    sheets = fixture.start_document(out, probe.start)
    print(f"project written to {out}")
    print(f"  the document to open: {sheets}")
    print()
    print("give the model this:")
    print(f"  {probe.prompt}")
    if probe.blocked_on:
        print(f"  [BLOCKED] {probe.blocked_on}")
    print()
    print("point it at the project:")
    print(f"  claude mcp add roaddraft-probe -- {_venv_bin()} --doc {sheets} --autosave")
    print()
    print("then score what it leaves behind:")
    print(f"  python -m roaddraft.probes score {probe.id} --doc {sheets}")
    return 0


def cmd_score(args) -> int:
    probe = tasks.get(args.probe)
    submitted = Session.load(args.doc)
    baseline = _baseline(probe, args.baseline)
    result = probe.check(baseline, submitted)
    print(f"{probe.id}: {'PASS' if result.passed else 'FAIL'}")
    print(f"  {result.detail}")
    if not result.passed and probe.note:
        print(f"  note: {probe.note}")
    return 0 if result.passed else 1


def _starts(tmp: Path):
    """Each start project built once, under ``tmp``: the L-2 start takes ~20 s."""
    built = {}

    def start_dir(probe) -> Path:
        if probe.start not in built:
            built[probe.start] = tmp / "start" / probe.start
            fixture.start_document(built[probe.start], probe.start)
        return built[probe.start]
    return start_dir


def cmd_selftest(args) -> int:
    """Every probe's scripted solution must pass its own check, read back from
    the file it saved, and the untouched start must not."""
    import tempfile
    failures = []
    runnable = [p for p in tasks.PROBES if p.solve]
    with tempfile.TemporaryDirectory() as tmp:
        start_dir = _starts(Path(tmp))
        for probe in runnable:
            start = start_dir(probe)
            ref = reference.write(probe, Path(tmp) / probe.id, start, plots=False)
            mark = "ok  " if ref.result.passed else "FAIL"
            print(f"  {mark} {probe.id}: {ref.result.detail}")
            if not ref.result.passed:
                failures.append(probe.id)
            # and the untouched start must NOT pass, or the check proves nothing
            pristine = start / fixture.START[probe.start]
            empty = probe.check(Session.load(pristine, out_dir=start),
                                Session.load(pristine, out_dir=start))
            if empty.passed:
                print(f"  FAIL {probe.id}: the untouched project already passes")
                failures.append(probe.id + " (vacuous)")
    blocked = [p.id for p in tasks.PROBES if p.blocked_on]
    print(f"{len(runnable) - len(failures)}/{len(runnable)} scripted solutions pass"
          + (f"; {len(blocked)} blocked: {', '.join(blocked)}" if blocked else ""))
    return 1 if failures else 0


def cmd_reference(args) -> int:
    """Each chosen probe's scripted solution, kept as a finished project under
    ``--out`` and scored from disk, with an index."""
    import tempfile
    known = {p.id for p in tasks.PROBES}
    unknown = [pid for pid in args.probes if pid not in known]
    if unknown:
        print(f"no probe {', '.join(unknown)}: see python -m roaddraft.probes list")
        return 2
    chosen = [p for p in tasks.PROBES if p.solve
              and (not args.probes or p.id in args.probes)
              and (not args.tag or args.tag in p.tags)]
    out = Path(args.out)
    for probe in chosen:
        folder = out / probe.id
        if folder.exists() and not (folder / reference.RECORD).exists():
            print(f"{folder} exists and was not written by this command: move it "
                  f"or choose another --out")
            return 2
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        start_dir = _starts(Path(tmp))
        for probe in chosen:
            folder = out / probe.id
            if folder.exists():
                shutil.rmtree(folder)
            ref = reference.write(probe, folder, start_dir(probe), plots=not args.no_plots)
            mark = "ok  " if ref.result.passed else "FAIL"
            print(f"  {mark} {probe.id}: {folder / ref.document.name}")
            if not ref.result.passed:
                print(f"       {ref.result.detail}")
                failures.append(probe.id)
    index = reference.write_index(out, shown=args.out)
    print(f"{len(chosen) - len(failures)}/{len(chosen)} references pass their checks, "
          f"read back from disk; index: {index}")
    return 1 if failures else 0


def _baseline(probe, explicit) -> Session:
    """A pristine copy of what the probe started from, to diff the submission
    against."""
    import tempfile
    if explicit:
        return Session.load(explicit)
    tmp = Path(tempfile.mkdtemp())
    return Session.load(fixture.start_document(tmp, probe.start), out_dir=tmp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.probes",
                                     description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command")

    lister = subs.add_parser("list", help="the probes and what each asks for")
    lister.add_argument("--tag", help="only probes with this tag, e.g. draft, find, paper")

    setup = subs.add_parser("setup", help="write a fresh project for one probe")
    setup.add_argument("probe")
    setup.add_argument("--out", default="probe_out")
    setup.add_argument("--force", action="store_true", help="overwrite --out")

    score = subs.add_parser("score", help="grade a finished document")
    score.add_argument("probe")
    score.add_argument("--doc", required=True)
    score.add_argument("--baseline", help="the untouched sheet file (default: rebuild)")

    subs.add_parser("selftest", help="run every scripted solution against its check")

    keep = subs.add_parser("reference", help="keep each scripted solution as a finished "
                                             "project: document, journal, PDF, DXF")
    keep.add_argument("probes", nargs="*", help="these probes (default: all)")
    keep.add_argument("--tag", help="only probes with this tag")
    keep.add_argument("--out", required=True)
    keep.add_argument("--no-plots", action="store_true", help="skip the PDF and DXF")

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "score":
        return cmd_score(args)
    if args.command == "selftest":
        return cmd_selftest(args)
    if args.command == "reference":
        return cmd_reference(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

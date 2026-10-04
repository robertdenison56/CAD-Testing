"""Run the probes: finding and annotating (T2), drafting from a description (T1),
and the harder second tier of both (tier2).

    python -m roaddraft.probes list [--tag draft|find|tier2]
    python -m roaddraft.probes setup edge-curve-c102 --out /tmp/probe
    python -m roaddraft.probes score edge-curve-c102 --doc /tmp/probe/SR-100.sheets.rdoc.json
    python -m roaddraft.probes selftest

``setup`` writes a fresh copy of the project and prints the instruction to give
the model and the MCP command that points at it. Let the model work, then
``score`` the document it leaves behind. ``selftest`` runs the scripted solution
for every probe, which is what keeps the checks honest.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from roaddraft.api.session import Session
from roaddraft.probes import fixture, tasks


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


def cmd_selftest(args) -> int:
    """Every probe's scripted solution must pass its own check."""
    import tempfile
    failures = []
    runnable = [p for p in tasks.PROBES if p.solve]
    for probe in runnable:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            sheets = fixture.start_document(out, probe.start)
            baseline = Session.load(sheets, out_dir=out)
            session = Session.load(sheets, out_dir=out)
            probe.solve(session)
            result = probe.check(baseline, session)
            mark = "ok  " if result.passed else "FAIL"
            print(f"  {mark} {probe.id}: {result.detail}")
            if not result.passed:
                failures.append(probe.id)
            # and the untouched fixture must NOT pass, or the check proves nothing
            empty = probe.check(baseline, Session.load(sheets, out_dir=out))
            if empty.passed:
                print(f"  FAIL {probe.id}: the untouched project already passes")
                failures.append(probe.id + " (vacuous)")
    blocked = [p.id for p in tasks.PROBES if p.blocked_on]
    print(f"{len(runnable) - len(failures)}/{len(runnable)} scripted solutions pass"
          + (f"; {len(blocked)} blocked: {', '.join(blocked)}" if blocked else ""))
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

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "score":
        return cmd_score(args)
    if args.command == "selftest":
        return cmd_selftest(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

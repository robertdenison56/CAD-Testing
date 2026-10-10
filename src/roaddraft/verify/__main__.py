"""``python -m roaddraft.verify DOCUMENT TRUTH [--journal J] [--level explicit|vague] [--json]``

Scores a saved drawing against a task's ``.truth.json`` (as written by
``python -m roaddraft.tasks``) and prints the per-check credit and findings,
or the whole report as JSON.  Exit status 0 for a clean 100, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys

from roaddraft.verify import verify_files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.verify",
                                     description="Score a drafted D1 sheet against its truth")
    parser.add_argument("document", help="a saved .rdoc.json / .rdraft")
    parser.add_argument("truth", help="the task's .truth.json")
    parser.add_argument("--journal", help="the episode's journal, for the audit")
    parser.add_argument("--level", default="explicit",
                        help="the prompt level the task was posed at (explicit or vague)")
    parser.add_argument("--json", action="store_true", help="print the whole report as JSON")
    ns = parser.parse_args(argv)
    report = verify_files(ns.document, ns.truth, ns.journal, prompt_level=ns.level)
    if ns.json:
        print(json.dumps(report.to_dict(include_timing=True), indent=2, ensure_ascii=False))
    else:
        print(f"{report.task_id} ({ns.level}; scope {', '.join(report.scope)}): "
              f"effective {report.effective_score:g} / 100, rubric {report.rubric_score:g}"
              + (", HARD FAIL" if report.hard_failed else "") + f"  [{report.timing_ms:.1f} ms]")
        for f in report.findings:
            print(f"  !! {f.code}: {f.note or ''}")
        for c in report.checks:
            if not c.in_scope:
                continue
            print(f"  {c.id} {c.points:6.2f}/{c.weight:<3g} {c.status:8s} {c.name}")
            for f in c.findings[:8]:
                where = f.anchor["ref"] if f.anchor else ", ".join(f.entity_ids)
                print(f"      {f.code:20s} {where}  {f.note or ''}")
            if len(c.findings) > 8:
                print(f"      ... {len(c.findings) - 8} more")
    clean = report.effective_score == 100.0 and not report.all_findings()
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())

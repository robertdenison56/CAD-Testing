"""Generate D1 task seed 42, run the reference solution, and write everything
(brief, ground truth, journal, document, LandXML, sheet PNG) into
examples/output/.

Run:  python examples/generate_task.py [SEED] [--equations]
"""
import sys
from pathlib import Path

from roaddraft.tasks.__main__ import write_task
from roaddraft.tasks.generator import generate_task

OUT = Path(__file__).parent / "output"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    equations = "--equations" in argv
    seeds = [int(a) for a in argv if not a.startswith("--")] or [42]
    for seed in seeds:
        task = generate_task(seed, equations=equations)
        report = write_task(task, OUT)
        m = report["match"]
        print(f"task {report['task_id']}: {task.brief.project['name']} "
              f"({task.truth.counts['curves']} curves, "
              f"1\"={task.brief.deliverable['feet_per_inch']:.0f}')")
        for key, path in report["paths"].items():
            print(f"    {key:9s} {path}")
        print(f"    reference {report['commands']} commands, replay "
              f"{'OK' if report['replay_ok'] else 'DIVERGED'}, truth match "
              f"{m['matched']}/{task.truth.counts['labels']} labels, "
              f"{len(m['missing'])} missing, {len(m['extra'])} extra")
    return 0


if __name__ == "__main__":
    sys.exit(main())

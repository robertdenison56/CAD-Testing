#!/bin/zsh
# Track D on Runpod, the fourth queue: two new image-reading models (Robert, 2026-11-11: "what about mistral?",
# "find more vision models for the hard pilots", "drop the GLM and create the nemotron and mistral", "Write the queue").
# Written 2026-11-11, NOT launched: it waits on Robert's go.
#
# Two models, one endpoint at a time, the cheaper first (a run that does not fit the budget is skipped and logged):
#   1. Mistral Small 4 119B       (6.5B active, NVFP4, `yeiyts8irltnwb`)  est. $3 d1-test, $10 the pilots
#   2. Nemotron 3.5 Super VL 120B (12B active, NVFP4, `y12d4fzbc8bz7r`)   est. $4 d1-test, $17 the pilots
# Each: warm (a 71-75 GB cold start), smoke (d1-dev[:5]), d1-test, one image pilot, then the hard-pilots cost
# subset (cost5): all 66 if the image pilot finished, else its 51 text pilots, marked text only on the board.
# Neither model has loaded on this worker (Hub release v2.30.3, vLLM v0.32.0): a failed warm or smoke skips the
# model's runs. Both on BLACKWELL_96 at $3.49/h. Estimates are scaled from Qwen3.6 and Gemma 4 31B on the same
# card; neither model is measured.
# Every run single mode, vague prompts, k = 1, from the worktree runpod-trackd at TRACKD_PIN (runpod_campaign.py),
# run ids ending -v3; the reports are written, NOT published (a look first).
#
# The image check is stricter than v5's: Gemma 4 26B-A4B's passed on an episode the proxy cut at 570 s after two
# steps. Here the image pilot must end by submit, or by a budget other than the turn clock, with a step.
#
# The budget guard is the earlier queues': before each run the balance is read; a run starts only if the spend since
# this queue began plus the run's mid estimate stays under BUDGET - RESERVE and the balance covers its high estimate.
# A self-hosted run cannot be capped while it runs, so one that outgrows its estimate can pass the line by its excess.
#
# Launch (after the go):  nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v6.sh > results/e3-runpod/queue-trackd-v6.out 2>&1 &
# Log: results/e3-runpod/queue-trackd-v6.log; each run's own output in results/e3-runpod/<run id>.log
REPO="/Volumes/RobertsExternalSSD/repos/CAD Testing"
PY="$REPO/.venv/bin/python"
CAMP="$REPO/benchmarks/runpod/runpod_campaign.py"
LMS="$REPO/benchmarks/lmstudio/lms_campaign.py"      # clear-errors (takes a run folder path)
WT="$REPO/.claude/worktrees/runpod-trackd"
OUT="$REPO/results/e3-runpod"
LOG="$OUT/queue-trackd-v6.log"
BUDGET=${BUDGET:-50}       # dollars this queue may spend (Robert, Nov 11: "think of different models for 50"; balance $54.65 that day)
RESERVE=${RESERVE:-3}      # kept back for the cold starts and idle tails the estimates leave out
mkdir -p "$OUT"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
balance() { runpodctl user 2>/dev/null | jq -r '.clientBalance'; }
park() { "$PY" "$CAMP" workers "$1" 0 >> "$LOG" 2>&1; log "parked $1"; }
park_all() { for n in mistral-small-4 nemotron-3.5-super-vl; do park $n; done; }
trap 'log "queue exiting (pid $$)"; park_all' EXIT
trap 'exit 130' INT TERM

START=$(balance)
[[ -z "$START" || "$START" == null ]] && { log "cannot read the balance; stopping"; exit 1; }
log "queue started (pid $$), balance \$$START, budget \$$BUDGET (reserve \$$RESERVE), code $(git -C "$WT" rev-parse --short HEAD 2>/dev/null)"

fits() {  # mid high: may a run with these estimates start?
  local now=$(balance)
  "$PY" - "$START" "$now" "$1" "$2" "$BUDGET" "$RESERVE" <<'PYEOF'
import sys
start, now, mid, high, budget, reserve = map(float, sys.argv[1:])
spent = start - now
ok = spent + mid <= budget - reserve and now >= high
print(f"spent ${spent:.2f} of ${budget:.0f}, balance ${now:.2f}, run est ${mid:.0f} (high ${high:.0f}): {'go' if ok else 'SKIP'}")
sys.exit(0 if ok else 1)
PYEOF
}
errors_in() {  # how many of the run's episodes ended in error (infrastructure: resets, 5xx; not the 570 s cut)
  "$PY" - "$OUT/$1/episodes" <<'PYEOF'
import glob, json, sys
n = 0
for f in glob.glob(sys.argv[1] + "/*.jsonl"):
    end = [r for r in (json.loads(l) for l in open(f) if l.strip()) if r.get("type") == "end"]
    n += bool(end) and end[-1].get("termination") == "error"
print(n)
PYEOF
}
ok_episode() {  # run_id: every episode ended (not in error) with a step: the smoke and the image check
  "$PY" - "$OUT/$1/episodes" <<'PYEOF'
import glob, json, sys
files = glob.glob(sys.argv[1] + "/*.jsonl")
if not files:
    print("no episode file"); sys.exit(1)
bad = 0
for f in files:
    end = [r for r in (json.loads(l) for l in open(f) if l.strip()) if r.get("type") == "end"]
    e = end[-1] if end else {}
    print(f"{f.rsplit('/', 1)[-1]}: termination={e.get('termination')} steps={e.get('steps')} effective={e.get('effective_score')}")
    bad += not (e.get("termination") in ("submit", "budget") and int(e.get("steps") or 0) > 0)
sys.exit(1 if bad > len(files) // 2 else 0)
PYEOF
}
run() {  # mid high name run_id taskset [extra e3 args...]: guard, run, one error pass, report
  local mid=$1 high=$2 name=$3 run_id=$4 taskset=$5
  shift 5
  if ! fits "$mid" "$high" >> "$LOG" 2>&1; then log "SKIP $run_id (budget)"; return 2; fi
  log "start $run_id ($name, $taskset)"
  "$PY" "$CAMP" e3 "$name" --taskset "$taskset" --samples 1 --run-id "$run_id" "$@" >> "$LOG" 2>&1
  log "end $run_id: exit $?"
  local errs=$(errors_in "$run_id")
  if (( errs > 0 )); then
    log "$run_id: $errs episode(s) ended in error; setting them aside and resuming once"
    "$PY" "$LMS" clear-errors "$OUT/$run_id" --apply >> "$LOG" 2>&1
    "$PY" "$CAMP" e3 "$name" --taskset "$taskset" --samples 1 --run-id "$run_id" "$@" >> "$LOG" 2>&1
    log "end $run_id (error pass): exit $?"
  fi
  PYTHONPATH="$WT/src" "$PY" -m roaddraft.eval report "$OUT/$run_id" >> "$LOG" 2>&1
  log "$run_id report written (not published)"
}
purge_queued() {  # a warm job that never met a worker stays queued on the parked endpoint (Nov 10's gpt-oss job): clear it
  local id=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['models'][sys.argv[2]]['endpoint'])" "$REPO/benchmarks/runpod/models.json" "$1")
  curl -s -m 30 -X POST -H "Authorization: Bearer $RUNPOD_API_KEY" "https://api.runpod.ai/v2/$id/purge-queue" >> "$LOG" 2>&1
  echo >> "$LOG"
}
warm() {  # name [seconds]: the worker started on the queue route first: a cold start on the streamed route meets the 570 s cut
  if ! fits 1 2 >> "$LOG" 2>&1; then log "SKIP warm $1 (budget)"; return 2; fi
  "$PY" "$CAMP" warm "$1" --wait "${2:-1500}" >> "$LOG" 2>&1 || { log "warm $1 failed"; purge_queued "$1"; return 1; }
  log "warm $1 done"
}
smoke() {  # name [e3-smoke args]: d1-dev[:5] at the vague prompt; the model's other runs need most of its five to end by submit or budget with steps
  local name=$1; shift
  "$PY" "$CAMP" e3-smoke "$name" --level vague "$@" >> "$LOG" 2>&1
  set -- "$name"
  ok_episode "e3-smoke-v3-$1" >> "$LOG" 2>&1 || { log "smoke $1 FAILED: its runs are skipped"; return 1; }
  log "smoke $1 ok"
}

finished_image() {  # run_id: the one image pilot ended by submit, or by a budget that is not the turn clock, with a step
  "$PY" - "$OUT/$1/episodes" <<'PYEOF'
import glob, json, sys
files = glob.glob(sys.argv[1] + "/*.jsonl")
if not files:
    print("no episode file"); sys.exit(1)
ok = 0
for f in files:
    end = [r for r in (json.loads(l) for l in open(f) if l.strip()) if r.get("type") == "end"]
    e = end[-1] if end else {}
    print(f"{f.rsplit('/', 1)[-1]}: termination={e.get('termination')} budget_tripped={e.get('budget_tripped')} steps={e.get('steps')}")
    done = e.get("termination") == "submit" or (e.get("termination") == "budget" and e.get("budget_tripped") != "turn_time")
    ok += bool(done and int(e.get("steps") or 0) > 0)
sys.exit(0 if ok == len(files) else 1)
PYEOF
}
model() {  # name test_mid test_high pilots_mid pilots_high: warm, smoke, d1-test, the image pilot, the cost5 pilots
  local name=$1 tm=$2 th=$3 pm=$4 ph=$5
  if warm $name && smoke $name; then
    run $tm $th $name e3-d1-test-$name-single-vague-v3 d1-test --level vague
    run 1 2 $name e3-imagecheck-vague-v3-$name hard-pilots --pilots images --limit 1 --level vague
    if finished_image e3-imagecheck-vague-v3-$name >> "$LOG" 2>&1; then
      run $pm $ph $name e3-hard-pilots-$name-single-vague-cost5-v3 hard-pilots --subset cost5 --level vague
    else
      log "$name: the image pilot did not finish; its hard-pilots run is the text pilots, marked text only"
      run $pm $ph $name e3-hard-pilots-$name-single-vague-cost5-text-v3 hard-pilots --subset cost5 --pilots text --level vague
    fi
  fi
  park $name
}

model mistral-small-4 3 6 10 16
model nemotron-3.5-super-vl 4 8 17 24

log "queue done: spent \$$("$PY" -c "print(f'{$START - $(balance):.2f}')") of \$$BUDGET"

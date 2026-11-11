#!/bin/zsh
# Track D on Runpod, the third queue: hard-pilots only (benchmarks/runpod/PLAN.md, "The third queue"). Robert,
# 2026-11-10, after stopping the second queue: "only run the hard pilots. suggest a nerw model list", then, to the
# list below, "run those for now and we can test a different one if needed".
#
# Four models on the hard-pilots cost subset (cost5: 66 pilots, 15 of them briefed by a page), one endpoint at a time,
# in priority order (a run that does not fit the budget is skipped and logged):
#   1. GLM-5.3          (753B, public, per token, text only) its 51 text pilots, under --cost-cap 40
#   2. gpt-oss-120b     (117B, mxfp4, text only, --send-reasoning) its 51 text pilots
#   3. Gemma 4 31B      (bf16, reads images) one image pilot, then all 66 (the 51 text pilots if it did not read it)
#   4. Gemma 4 26B-A4B  (bf16, reads images) smoke (d1-dev[:5]), one image pilot, then all 66 (or the 51)
# A run on the text pilots alone stays on the board in the cost5 table, marked "text only" (Robert, Nov 10).
# Every run single mode, vague prompts, k = 1, from the worktree runpod-trackd at TRACKD_PIN (runpod_campaign.py),
# run ids ending -v3; the reports are written, NOT published (a look first).
#
# The budget guard is the earlier queues': before each run the balance is read; a run starts only if the spend since
# this queue began plus the run's mid estimate stays under BUDGET - RESERVE and the balance covers its high estimate.
# BUDGET is $90: the $120 less the $29.64 the first two queues spent. A self-hosted run cannot be capped while it
# runs, so one that outgrows its estimate can pass the line by its excess; GLM-5.3's run carries a cost cap.
#
# Launch:  nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v5.sh > results/e3-runpod/queue-trackd-v5.out 2>&1 &
# Log: results/e3-runpod/queue-trackd-v5.log; each run's own output in results/e3-runpod/<run id>.log
REPO="/Volumes/RobertsExternalSSD/repos/CAD Testing"
PY="$REPO/.venv/bin/python"
CAMP="$REPO/benchmarks/runpod/runpod_campaign.py"
LMS="$REPO/benchmarks/lmstudio/lms_campaign.py"      # clear-errors (takes a run folder path)
WT="$REPO/.claude/worktrees/runpod-trackd"
OUT="$REPO/results/e3-runpod"
LOG="$OUT/queue-trackd-v5.log"
BUDGET=${BUDGET:-90}       # dollars this queue may spend: $120 in all (Robert, Nov 10), less the $29.64 spent by queues v3 and v4
RESERVE=${RESERVE:-3}      # kept back for the cold starts and idle tails the estimates leave out
mkdir -p "$OUT"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
balance() { runpodctl user 2>/dev/null | jq -r '.clientBalance'; }
park() { "$PY" "$CAMP" workers "$1" 0 >> "$LOG" 2>&1; log "parked $1"; }
park_all() { for n in gpt-oss-120b gemma-4-31b gemma-4-26b-a4b; do park $n; done; }   # GLM-5.3 is public: nothing to park
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

projected_100() {  # run_id: the mean cost an episode (the harness prices GLM-5.3 from prices.json) x 100, or fail
  "$PY" - "$OUT/$1/episodes" <<'PYEOF'
import glob, json, sys
costs = []
for f in glob.glob(sys.argv[1] + "/*.jsonl"):
    end = [r for r in (json.loads(l) for l in open(f) if l.strip()) if r.get("type") == "end"]
    if end and end[-1].get("cost_usd") is not None:
        costs.append(float(end[-1]["cost_usd"]))
if not costs:
    print("no priced episode"); sys.exit(1)
cached = []
for f in glob.glob(sys.argv[1] + "/*.jsonl"):
    for r in (json.loads(l) for l in open(f) if l.strip()):
        u = r.get("usage") or {}
        if u.get("input_tokens") is not None:
            cached.append((u.get("cache_read_input_tokens") or 0, (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)))
share = sum(c for c, _ in cached) / max(1, sum(t for _, t in cached))
proj = 100 * sum(costs) / len(costs)
print(f"{len(costs)} priced episodes, ${sum(costs):.2f}, cached share {share:.0%}: 100 episodes project ${proj:.2f}")
sys.exit(0 if proj <= 35 else 1)
PYEOF
}

GLM=glm-5.3; OSS=gpt-oss-120b; G31=gemma-4-31b; G26=gemma-4-26b-a4b

pilots() {  # mid high name: one image pilot, then the cost5 pilots: all 66 if the model read the page, else its 51 text pilots
  local mid=$1 high=$2 name=$3
  run 1 2 $name e3-imagecheck-vague-v3-$name hard-pilots --pilots images --limit 1 --level vague
  if ok_episode e3-imagecheck-vague-v3-$name >> "$LOG" 2>&1; then
    run $mid $high $name e3-hard-pilots-$name-single-vague-cost5-v3 hard-pilots --subset cost5 --level vague
  else
    log "$name: the image pilot failed; its hard-pilots run is the text pilots, marked text only"
    run $mid $high $name e3-hard-pilots-$name-single-vague-cost5-text-v3 hard-pilots --subset cost5 --pilots text --level vague
  fi
}

# 1. GLM-5.3: the 51 text pilots of cost5 (d1-test measured $0.043 an episode; the pilots send 6 times the input)
run 25 40 $GLM e3-hard-pilots-$GLM-single-vague-cost5-text-v3 hard-pilots --subset cost5 --cost-cap 40 --level vague

# 2. gpt-oss-120b: the 51 text pilots (its d1-test ran Nov 10: 70.3, tools called)
if warm $OSS; then
  run 8 14 $OSS e3-hard-pilots-$OSS-single-vague-cost5-text-v3 hard-pilots --subset cost5 --level vague
fi
park $OSS

# 3. Gemma 4 31B: the best open row on d1-test and d1-real (80.1 / 76.8), 2.5 times Qwen3.6's time an episode
if warm $G31; then
  pilots 30 40 $G31
fi
park $G31

# 4. Gemma 4 26B-A4B: not yet run under e3-v3, so a smoke first
if warm $G26 && smoke $G26; then
  pilots 12 18 $G26
fi
park $G26

log "queue done: spent \$$("$PY" -c "print(f'{$START - $(balance):.2f}')") of \$$BUDGET"

#!/bin/zsh
# Track D on Runpod, the fifth queue: finish the hard-pilots cost5 runs to the full set (Robert, 2026-11-12:
# "why did the cost set run shorter? how much is it to finsh them out", then "finish them").
#
# Each model's cost5 run held 66 of the 112 pilots (5 of each task type). Its 66 finished episodes were copied
# (episodes/ + projects/) into a new full-set run id, so the harness's resume skips them and runs only the other 46
# (gpt-oss-120b, text only: 51 copied, the other 38 text pilots of 89). The cost5 runs stay as they were.
# Same pin as the cost5 runs (ad6bf5e3; Qwen3.6's ran at f6725cbb, same verifier, spec hash and harness), same
# endpoints, same settings, single mode, vague prompts, k = 1. No smoke or image check: each model passed both
# before, and its cost5 run's pilots (all, or text for gpt-oss) fix which pilots this run takes.
#
# Order, cheapest first; the estimates are each cost5 run's spend scaled by task type (mid) and by count (high):
#   1. Mistral Small 4           $1  ($2)     4. Qwen3.6-35B-A3B    $4  ($9)
#   2. gpt-oss-120b (text)       $1  ($2)     5. Gemma 4 31B        $7  ($12)
#   3. Nemotron 3.5 Super VL     $3  ($6)     6. Gemma 4 26B-A4B    $5  ($8)
# Gemma 4 26B-A4B last: 25 of its 66 cost5 episodes ended on the proxy's 570 s streamed-turn cut, and these
# settings are the same, so its full row carries the same under-read.
#
# Budget guard as the earlier queues: before each warm and run the balance is read; it starts only if the spend
# since this queue began plus its mid estimate stays under BUDGET - RESERVE and the balance covers its high estimate.
#
# Launch:  nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v7.sh > results/e3-runpod/queue-trackd-v7.out 2>&1 &
# Log: results/e3-runpod/queue-trackd-v7.log; each run's own output in results/e3-runpod/<run id>.log
REPO="/Volumes/RobertsExternalSSD/repos/CAD Testing"
PY="$REPO/.venv/bin/python"
CAMP="$REPO/benchmarks/runpod/runpod_campaign.py"
LMS="$REPO/benchmarks/lmstudio/lms_campaign.py"      # clear-errors (takes a run folder path)
WT="$REPO/.claude/worktrees/runpod-trackd"
OUT="$REPO/results/e3-runpod"
LOG="$OUT/queue-trackd-v7.log"
BUDGET=${BUDGET:-35}       # balance $38.27 at setup (Nov 12); estimate ~$21 mid + warm-ups, ~$39 high
RESERVE=${RESERVE:-3}
MODELS=(mistral-small-4 gpt-oss-120b nemotron-3.5-super-vl qwen3.6-35b-a3b gemma-4-31b gemma-4-26b-a4b)
mkdir -p "$OUT"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
balance() { runpodctl user 2>/dev/null | jq -r '.clientBalance'; }
park() { "$PY" "$CAMP" workers "$1" 0 >> "$LOG" 2>&1; log "parked $1"; }
park_all() { for n in $MODELS; do park $n; done; }
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
purge_queued() {  # a warm job that never met a worker stays queued on the parked endpoint: clear it
  local id=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['models'][sys.argv[2]]['endpoint'])" "$REPO/benchmarks/runpod/models.json" "$1")
  curl -s -m 30 -X POST -H "Authorization: Bearer $RUNPOD_API_KEY" "https://api.runpod.ai/v2/$id/purge-queue" >> "$LOG" 2>&1
  echo >> "$LOG"
}
warm() {  # name [seconds]: the worker started on the queue route first: a cold start on the streamed route meets the 570 s cut
  if ! fits 1 2 >> "$LOG" 2>&1; then log "SKIP warm $1 (budget)"; return 2; fi
  "$PY" "$CAMP" warm "$1" --wait "${2:-1500}" >> "$LOG" 2>&1 || { log "warm $1 failed"; purge_queued "$1"; return 1; }
  log "warm $1 done"
}
finish() {  # name mid high [run id suffix]: warm, the rest of the full set, park
  local name=$1 mid=$2 high=$3 suffix=${4:-}
  warm $name && run $mid $high $name e3-hard-pilots-$name-single-vague$suffix-v3 hard-pilots --level vague
  park $name
}

finish mistral-small-4 1 2
finish gpt-oss-120b 1 2 -text        # vision false: the campaign runs the text pilots (89)
finish nemotron-3.5-super-vl 3 6
finish qwen3.6-35b-a3b 4 9
finish gemma-4-31b 7 12
finish gemma-4-26b-a4b 5 8

log "queue done: spent \$$("$PY" -c "print(f'{$START - $(balance):.2f}')") of \$$BUDGET"

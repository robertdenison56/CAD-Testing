#!/bin/zsh
# Track D on Runpod, the second queue: the large models on d1-test and hard-pilots (benchmarks/runpod/PLAN.md, "The
# second queue"). Robert, 2026-11-10: "still want to use the 100 for model testing", "i would like larger models on
# the test and hard pilots if possible", "add kimi", "Yes, raise to $120". Written 2026-11-10, NOT launched: it waits
# on Robert's go.
#
# Five steps, one endpoint at a time, in priority order (a step that does not fit the budget is skipped and logged):
#   1. gpt-oss-120b      (117B, mxfp4, self-hosted, --send-reasoning) warm, smoke (d1-dev[:5]), d1-test
#   2. Kimi K2.6         (1,027B, Runpod public endpoint, per token) smoke under a $5 cap; then d1-test under
#                        --cost-cap 40, only if the smoke's cost an episode projects 100 episodes at $35 or less
#   3. GLM-5.3           (753B, public, text only) hard-pilots cost5, its 51 text pilots, under --cost-cap 40
#   4. Qwen3.5-122B-A10B (125B, FP8, self-hosted on an H200 at $6.99/h) warm (a 125 GB cold start), smoke, d1-test,
#                        at 65k context and concurrency 2 (the card's KV room)
#   5. gpt-oss-120b      (text only) hard-pilots cost5, its 51 text pilots; only if step 1's smoke passed
# A text-only model runs the text pilots of the subset; the board keeps the row in the cost5 table marked "text only"
# (Robert, Nov 10: "mark any hard pilots that are text only as such, do not move off the board").
# Every run single mode, vague prompts, k = 1, from the worktree runpod-trackd at TRACKD_PIN (runpod_campaign.py),
# run ids ending -v3; the reports are written, NOT published (a look first).
#
# The budget guard is the first queue's: before each run the balance is read; a run starts only if the spend since
# this queue began plus the run's mid estimate stays under BUDGET - RESERVE and the balance covers its high estimate.
# BUDGET is $91: the $120 less the $28.62 the first queue spent. A self-hosted run cannot be capped while it runs, so
# a run that outgrows its estimate can pass the line by its excess; the two per-token runs carry a cost cap.
#
# Launch (after the go):  nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v4.sh > results/e3-runpod/queue-trackd-v4.out 2>&1 &
# Log: results/e3-runpod/queue-trackd-v4.log; each run's own output in results/e3-runpod/<run id>.log
REPO="/Volumes/RobertsExternalSSD/repos/CAD Testing"
PY="$REPO/.venv/bin/python"
CAMP="$REPO/benchmarks/runpod/runpod_campaign.py"
LMS="$REPO/benchmarks/lmstudio/lms_campaign.py"      # clear-errors (takes a run folder path)
WT="$REPO/.claude/worktrees/runpod-trackd"
OUT="$REPO/results/e3-runpod"
LOG="$OUT/queue-trackd-v4.log"
BUDGET=${BUDGET:-91}       # dollars this queue may spend: $120 in all (Robert, Nov 10), less the first queue's $28.62
RESERVE=${RESERVE:-3}      # kept back for the cold starts and idle tails the estimates leave out
mkdir -p "$OUT"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
balance() { runpodctl user 2>/dev/null | jq -r '.clientBalance'; }
park() { "$PY" "$CAMP" workers "$1" 0 >> "$LOG" 2>&1; log "parked $1"; }
park_all() { for n in gpt-oss-120b qwen3.5-122b-a10b; do park $n; done; }   # GLM-5.3 and Kimi are public: nothing to park
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

OSS=gpt-oss-120b; KIMI=kimi-k2.6; GLM=glm-5.3; Q122=qwen3.5-122b-a10b

# 1. gpt-oss-120b on d1-test (AMPERE_80 or BLACKWELL_96; its 20b sibling skipped tool calls in 76% of its probes)
if warm $OSS && smoke $OSS; then
  run 4 7 $OSS e3-d1-test-$OSS-single-vague-v3 d1-test --level vague
  OSSOK=1
fi
park $OSS

# 2. Kimi K2.6 on d1-test: the largest open-weight model on the route, billed per token, no cached rate listed
if fits 2 5 >> "$LOG" 2>&1 && smoke $KIMI --cost-cap 5; then
  if projected_100 e3-smoke-v3-$KIMI >> "$LOG" 2>&1; then
    run 27 35 $KIMI e3-d1-test-$KIMI-single-vague-v3 d1-test --cost-cap 40 --level vague
  else
    log "$KIMI: the smoke projects past \$35 for 100 episodes (or priced nothing); d1-test skipped"
  fi
fi

# 3. GLM-5.3 on hard-pilots: the 51 text pilots of cost5 (text only); d1-test measured $0.043 an episode
run 25 32 $GLM e3-hard-pilots-$GLM-single-vague-cost5-text-v3 hard-pilots --subset cost5 --cost-cap 40 --level vague

# 4. Qwen3.5-122B-A10B on d1-test: 125 GB of weights to pull, so the warm job waits up to 50 minutes
if warm $Q122 3000 && smoke $Q122 --concurrency 2; then
  run 12 18 $Q122 e3-d1-test-$Q122-single-vague-v3 d1-test --concurrency 2 --level vague
fi
park $Q122

# 5. gpt-oss-120b on hard-pilots: the 51 text pilots of cost5
if [[ -n "$OSSOK" ]] && warm $OSS; then
  run 14 20 $OSS e3-hard-pilots-$OSS-single-vague-cost5-text-v3 hard-pilots --subset cost5 --level vague
fi
park $OSS

log "queue done: spent \$$("$PY" -c "print(f'{$START - $(balance):.2f}')") of \$$BUDGET"

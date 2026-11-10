#!/bin/zsh
# Track D on Runpod under harness e3-v3: the $100 plan (benchmarks/runpod/PLAN.md, "The $100 plan"; Robert,
# 2026-11-04: "begin setting up the containers for runpod runs, select appropriate models and keep budget to $100
# for finishing track D"). Written 2026-11-04, NOT launched: a run waits on Robert's go and a balance top-up.
#
# Four models, one endpoint at a time, in priority order, so that if the money runs short the runs that drop are
# the last ones (Robert, Nov 4: "Yes, swap them": Gemma 26B and Qwen3.6's two hard sets out, GLM-5.3 and
# gpt-oss-120b in; "Yes, keep d1-test"):
#   A. Qwen3.6-35B-A3B   (bf16, self-hosted) smoke (d1-dev[:5]), one image pilot (the image route), d1-test,
#                        d1-real cost5
#   B. Gemma 4 31B       (bf16, self-hosted) smoke, d1-test, d1-real cost5
#   C. GLM-5.3           (Runpod public endpoint, per token) smoke under a $5 cap; then d1-test under --cost-cap 30,
#                        only if the smoke's cost an episode projects 100 episodes at $33 or less
#   D. gpt-oss-120b      (mxfp4, self-hosted, --send-reasoning) smoke; d1-test and d1-real cost5 only if the smoke
#                        calls tools
#   E. Qwen3.6-35B-A3B   hard-pilots cost5 (66; only if it read the image pilot), d1-test-hard cost5 (25),
#                        d1-real-hard cost5 (25)
# VAGUE PROMPTS ONLY (2026-11-08, Robert: "Update the runpod batches with vague prompts only", after "Stop all runs
# with explicit prompts and start the vague ones"): every run and every smoke is at the vague level, run ids
# -single-vague-v3 / -single-vague-cost5-v3. Qwen3.6's hard-pilots cost5 run and the image pilot that gates it were
# out for a few hours (a pilot then had one fixed brief) and are BACK at the vague level: since Nov 8 every pilot has a
# vague brief too (Robert: "Check if any of the eval tasks do not have a vague prompt style first, add them if
# needed"). The worktree must carry the vague-pilot code (benchmarks/runpod/PLAN.md); mid estimate back to ~$91.
# cost5 = the fixed cost subset of the set, 5 tasks of each task type (benchmarks/tasksets/cost-subsets.json;
# Robert, Nov 4: "limit the amount of episodes to save cost but still get at least 5 tasks from each category"). The
# board ranks such a run in its own table under the set, tagged partial to save cost, beside every full run re-scored
# on the same tasks, and only when it holds every task of the subset with none in error or unfinished; d1-test runs
# whole (its types hold 6-7 tasks, and its 10 ranked rows are the comparison).
# Every run single mode, vague prompts, k = 1 (no k = 3 or 5 anywhere: Robert, Nov 4), concurrency 4, from the
# worktree runpod-trackd at TRACKD_PIN (runpod_campaign.py), run ids ending -v3; the reports are written, NOT
# published (a look first, as the local and codex rows).
#
# The budget guard: before each run, the account balance is read (runpodctl user, the key never printed); a run
# starts only if the spend since this queue began plus the run's mid estimate stays under BUDGET - RESERVE, and the
# balance covers the run's high estimate. A run that does not fit is skipped and logged; the queue goes on to the
# next (a cheaper one may still fit). Each endpoint is parked (max workers 0) after its last run and on any exit.
#
# Launch (after the go):  nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v3.sh > results/e3-runpod/queue-trackd-v3.out 2>&1 &
# Log: results/e3-runpod/queue-trackd-v3.log; each run's own output in results/e3-runpod/<run id>.log
REPO="/Volumes/RobertsExternalSSD/repos/CAD Testing"
PY="$REPO/.venv/bin/python"
CAMP="$REPO/benchmarks/runpod/runpod_campaign.py"
LMS="$REPO/benchmarks/lmstudio/lms_campaign.py"      # clear-errors (takes a run folder path)
WT="$REPO/.claude/worktrees/runpod-trackd"
OUT="$REPO/results/e3-runpod"
LOG="$OUT/queue-trackd-v3.log"
BUDGET=${BUDGET:-100}      # dollars this queue may spend in all
RESERVE=${RESERVE:-3}      # kept back for the cold starts and idle tails the estimates leave out
mkdir -p "$OUT"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
balance() { runpodctl user 2>/dev/null | jq -r '.clientBalance'; }
park() { "$PY" "$CAMP" workers "$1" 0 >> "$LOG" 2>&1; log "parked $1"; }
park_all() { for n in qwen3.6-35b-a3b gemma-4-31b gpt-oss-120b; do park $n; done; }   # GLM-5.3 is public: nothing to park
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
warm() {  # the worker started on the queue route first: a cold start on the streamed route meets the 570 s cut
  if ! fits 1 2 >> "$LOG" 2>&1; then log "SKIP warm $1 (budget)"; return 2; fi
  "$PY" "$CAMP" warm "$1" >> "$LOG" 2>&1 || { log "warm $1 failed"; return 1; }
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
sys.exit(0 if proj <= 33 else 1)
PYEOF
}

Q=qwen3.6-35b-a3b; G31=gemma-4-31b; GLM=glm-5.3; OSS=gpt-oss-120b

# A. Qwen3.6-35B-A3B: the best open row so far (Track P 67.7%, d1-variance 86.7), the cheapest self-hosted one an episode
if warm $Q && smoke $Q; then
  run 1 2 $Q e3-imagecheck-vague-v3-$Q hard-pilots --pilots images --limit 1 --level vague
  ok_episode e3-imagecheck-vague-v3-$Q >> "$LOG" 2>&1 && QIMG=all || { QIMG=text; log "$Q image pilot failed: its hard-pilots runs text only"; }
  run 5 8  $Q e3-d1-test-$Q-single-vague-v3 d1-test --level vague
  run 4 6  $Q e3-d1-real-$Q-single-vague-cost5-v3 d1-real --subset cost5 --level vague
  QOK=1
fi
park $Q

# B. Gemma 4 31B: the top open-weight probe row (74.7%), dense, 2.5x Qwen3.6's cost an episode
if warm $G31 && smoke $G31; then
  run 13 18 $G31 e3-d1-test-$G31-single-vague-v3 d1-test --level vague
  run 10 14 $G31 e3-d1-real-$G31-single-vague-cost5-v3 d1-real --subset cost5 --level vague
fi
park $G31

# C. GLM-5.3: the largest open-weight model Track D can reach (Runpod serves it; billed per token, same balance)
if fits 2 5 >> "$LOG" 2>&1 && smoke $GLM --cost-cap 5; then
  if projected_100 e3-smoke-v3-$GLM >> "$LOG" 2>&1; then
    run 25 31 $GLM e3-d1-test-$GLM-single-vague-v3 d1-test --cost-cap 30 --level vague
  else
    log "$GLM: the smoke projects past \$33 for 100 episodes (or priced nothing); d1-test skipped"
  fi
fi

# D. gpt-oss-120b: OpenAI's open model, a fourth family (its 20b sibling skipped tool calls in 76% of its probes)
if warm $OSS && smoke $OSS; then
  run 5 8 $OSS e3-d1-test-$OSS-single-vague-v3 d1-test --level vague
  run 4 6 $OSS e3-d1-real-$OSS-single-vague-cost5-v3 d1-real --subset cost5 --level vague
fi
park $OSS

# E. Qwen3.6-35B-A3B on hard-pilots and the two hard sets, cost5: the one open model past 12B on them (the local three cover the small end)
if [[ -n "$QOK" ]] && warm $Q; then
  if [[ "$QIMG" == all ]]; then   # the subset holds 15 image pilots: a text-only run would be partial, not scored
    run 9 13 $Q e3-hard-pilots-$Q-single-vague-cost5-v3 hard-pilots --subset cost5 --level vague
  else
    log "$Q: no hard-pilots run (it did not read the image pilot; the subset needs images)"
  fi
  run 4 6 $Q e3-d1-test-hard-$Q-single-vague-cost5-v3 d1-test-hard --subset cost5 --level vague
  run 3 4 $Q e3-d1-real-hard-$Q-single-vague-cost5-v3 d1-real-hard --subset cost5 --level vague
fi
park $Q

log "queue done: spent \$$("$PY" -c "print(f'{$START - $(balance):.2f}')") of \$$BUDGET"

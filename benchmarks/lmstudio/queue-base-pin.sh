#!/bin/zsh
# The training pin's local queue: the 9B's base rerun, the same base with thinking off, and T0, on one pin and one rig
# (RoadDraft_Training_Plan.md section 3, decisions 1 and 3; benchmarks/training/T1_SMOKE.md section 1 for thinking off).
# Qwen3.5-9B Q4_K_M on RobertsPC through LM Studio, context as models.json loads it, vague prompt, single, k = 1.
#
#   zsh benchmarks/lmstudio/queue-base-pin.sh PIN_WORKTREE TAG --dry-run      # print every command, run nothing
#   nohup zsh benchmarks/lmstudio/queue-base-pin.sh PIN_WORKTREE TAG [--after PID] [--resume] > /dev/null 2>&1 &
#
# PIN_WORKTREE is the worktree checked out at TAG (git worktree add --detach PATH TAG). The queue refuses to start
# unless its HEAD is the tag's commit and its src, tests and benchmarks are clean. It runs the pin's own copy of
# lms_campaign.py (the one that passes --system-extra and --thinking), which keeps the interpreter and results/e3-lms
# in the main checkout.
#
# Three kinds of run, each a set at the vague prompt:
#   base     as the board rows ran: thinking left to the model (on)
#   nothink  --thinking off: the like-for-like base of a checkpoint served without thinking
#   t0       --system-extra benchmarks/training/conventions-v1.md (the pin's copy), thinking as base; d1-test, d1-real
# Order: the validation sets and d1-test first for base, then for nothink; T0 on d1-test; then d1-real three ways;
# then the hard sets (base, then nothink). Run ids end in the pin's suffix, so nothing resumes a board row; they
# carry the label models.json gives the model in use (MODEL; NOTHINK_MODEL for the nothink runs and the check).
#
# Before the nothink runs one d1-dev episode is run with --thinking off and read with `lms_campaign.py thinking`:
# if it carries reasoning tokens the server did not obey, and every nothink run is left out (logged, not an error).
# The same when the episode ended in error or reports no output tokens: that shows nothing about the server.
# Each nothink set is read the same way when it ends. Each launch checks on a fresh episode.
#
# As the local queues before it: it holds while the PC is off the LM Link, starts a stall watcher beside each run,
# retries a run that exits non-zero (ATTEMPTS, GAP_S apart), sets errored episodes aside once and resumes, and
# writes each report. Nothing is published: look first, then publish from main.
#
# Before its first run it waits for the PC to be free. Another queue shows no eval process in its retry gaps, its
# link waits, its error pass and each model load, so one look is not enough. In order: --after PID to end; every
# other local queue script alive at the start (results/e3-lms or benchmarks/lmstudio queue-*.sh) to end; then no
# local run or lms_campaign start for IDLE_POLLS looks in a row, POLL_S apart (10 min as set). The queue scripts
# are listed once, at the start, so two queues never wait on each other. Before each attempt of each run it looks
# again and holds, no attempt spent, while another local run is going.
#
# A queue that was stopped part-way is started again with --resume and the same SUFFIX: a finished run (every
# episode ended, report written) is not run again, the unfinished one is resumed under its run id (the harness skips
# the episodes that ended, and refuses a run whose finished episodes had another prompt or thinking setting), the
# rest run as planned. Only runs made at the tag's commit are carried on. Under the same QUEUE_NAME the log is
# carried on too. Without --resume an existing run or log is a reason not to start, as before.
#
# Settings (environment): SUFFIX=pin1  PHASES="base nothink t0"  SETS="" (all; or a list of set names)
#   MODEL=qwen3.5-9b  NOTHINK_MODEL=$MODEL (a models.json name; another one if the no-think base is its own file)
#   ATTEMPTS=30  GAP_S=180  POLL_S=120  IDLE_POLLS=6  QUEUE_NAME=queue-<date>-base-<suffix>
set -u
SELF=${0:A}          # this script, absolute before any cd: what the re-exec runs and what is stored beside the log
WT=${1:-}; TAG=${2:-}
if [[ -z $WT || -z $TAG ]]; then
  echo "usage: zsh queue-base-pin.sh PIN_WORKTREE TAG [--dry-run] [--after PID] [--resume]" >&2; exit 2
fi
shift 2
DRY=0; AFTER=""; RESUME=0
while (( $# )); do
  case $1 in
    --dry-run) DRY=1 ;;
    --resume) RESUME=1 ;;
    --after)
      [[ ${2:-} == <-> ]] || { echo "--after takes a process id" >&2; exit 2; }
      AFTER=$2; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
WT=${WT:A}
REPO=${REPO:-"/Volumes/RobertsExternalSSD/repos/CAD Testing"}
PY="$REPO/.venv/bin/python"
CAMP="$WT/benchmarks/lmstudio/lms_campaign.py"
OUT="$REPO/results/e3-lms"
SUFFIX=${SUFFIX:-pin1}
PHASES=${PHASES:-"base nothink t0"}
SETS=${SETS:-}
MODEL=${MODEL:-qwen3.5-9b}
NOTHINK_MODEL=${NOTHINK_MODEL:-$MODEL}
Q=""; QN=""          # the labels of MODEL and NOTHINK_MODEL in the pin's models.json, read with the checks below
ATTEMPTS=${ATTEMPTS:-30}
GAP_S=${GAP_S:-180}
POLL_S=${POLL_S:-120}
IDLE_POLLS=${IDLE_POLLS:-6}
SHEET=benchmarks/training/conventions-v1.md
QUEUE_NAME=${QUEUE_NAME:-queue-$(date +%Y-%m-%d)-base-$SUFFIX}
LOG="$OUT/$QUEUE_NAME.log"

# kind and set, in the order they run
STEPS=(
  "base d1-dev" "base d1-real-dev" "base pilot-dev" "base d1-test"
  "nothink d1-dev" "nothink d1-real-dev" "nothink pilot-dev" "nothink d1-test"
  "t0 d1-test"
  "base d1-real" "t0 d1-real" "nothink d1-real"
  "base d1-real-hard" "base d1-test-hard" "base hard-pilots"
  "nothink d1-real-hard" "nothink d1-test-hard" "nothink hard-pilots"
)

log() {
  if (( DRY )); then echo "# $*"; else echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; fi
}
refuse() {  # a reason not to start: fatal for a real run, a line of the dry run
  if (( DRY )); then echo "# dry run: a real run would refuse to start: $*"; else echo "NOT run: $*" >&2; exit 1; fi
}
label_of() {  # a models.json name -> its label there (what lms_campaign's own run ids carry); nothing when unknown
  "$PY" -c 'import json, sys; print(json.load(open(sys.argv[1]))["models"][sys.argv[2]]["label"])' \
    "$WT/benchmarks/lmstudio/models.json" "$1" 2> /dev/null
}
run_id_of() {  # kind set
  case $1 in
    base) echo "e3-$2-$Q-single-vague-$SUFFIX" ;;
    nothink) echo "e3-$2-$QN-single-vague-nothink-$SUFFIX" ;;
    t0) echo "e3-$2-$Q-single-vague-t0-$SUFFIX" ;;
  esac
}
e3_args() {  # kind set -> the e3 arguments after the model name, one per line
  print -l -- --taskset "$2" --samples 1 --run-id "$(run_id_of $1 $2)" --worktree "$WT" --level vague
  [[ $2 == hard-pilots ]] && print -l -- --pilots all
  [[ $1 == nothink ]] && print -l -- --thinking off
  [[ $1 == t0 ]] && print -l -- --system-extra "$SHEET"
  return 0
}
model_of() { [[ $1 == nothink ]] && echo "$NOTHINK_MODEL" || echo "$MODEL"; }
wanted() {  # kind set: in PHASES and (when given) in SETS
  [[ " $PHASES " == *" $1 "* ]] && { [[ -z $SETS ]] || [[ " $SETS " == *" $2 "* ]]; }
}
state_of() {  # run id -> new, partial, finished or other, then the detail (lms_campaign's run-state, at the tag's commit)
  [[ -e "$OUT/$1" ]] || { echo "new"; return; }
  "$PY" "$CAMP" run-state "$OUT/$1" --commit "${want:-}" 2> /dev/null
}

# The PC is one rig. A local run is the harness on localhost:1234, or lms_campaign starting one (preflight, model load).
LOCAL_RUN="roaddraft[.](runners|eval) run .*localhost:1234|lms_campaign[.]py (e3|k3|smoke|check|fit|vision|clear-errors) "
LOCAL_QUEUE="zsh .*(e3-lms|lmstudio)/queue-[^ /]*[.]sh( |\$)"
other_queues() {  # the pids of the other local queue scripts alive now: not this queue, nor the caffeinate above it
  local p
  for p in $(pgrep -f "$LOCAL_QUEUE"); do
    [[ $p == $$ || $p == $PPID ]] || print -- $p
  done
}
wait_pid() {  # hold while the process is alive
  while kill -0 "$1" 2> /dev/null; do sleep $POLL_S; done
}
wait_quiet() {  # looks: hold until no local run shows for that many looks in a row, POLL_S apart
  local need=$1 quiet=0 told=0
  while true; do
    if pgrep -f "$LOCAL_RUN" > /dev/null; then
      (( told )) || log "another local run is going; waiting until none shows for $need look(s) in a row, $POLL_S s apart"
      told=1; quiet=0
    else
      (( ++quiet >= need )) && break
    fi
    sleep $POLL_S
  done
  (( told )) && log "no other local run for $need look(s) in a row: going on"
  return 0
}

link_up() {  # lms_campaign's own check: RobertsPC listed as connected by `lms link status`
  "$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import lms_campaign as c; sys.exit(0 if c.link_ok() else 1)' \
    "$WT/benchmarks/lmstudio" 2> /dev/null
}
wait_link() {  # hold (no attempt spent) while the PC is off the link; check every 5 min
  link_up && return
  log "RobertsPC is not on the LM Link; waiting (checked every 5 min)"
  until link_up; do sleep 300; done
  log "RobertsPC is back on the LM Link"
}
run_e3() {  # kind set attempts: the run, retried while it exits non-zero
  local kind=$1 set=$2 attempts=$3 try=1 rc=1
  local run_id=$(run_id_of $kind $set)
  local -a args; args=("${(@f)$(e3_args $kind $set)}")
  while (( try <= attempts )); do
    wait_link
    wait_quiet 1                # another queue's run that started meanwhile: hold, no attempt spent
    log "start $run_id (attempt $try of $attempts) from $WT"
    "$PY" "$CAMP" e3 "$(model_of $kind)" "${args[@]}" >> "$LOG" 2>&1
    rc=$?
    log "end $run_id: exit $rc"
    (( rc == 0 )) && break
    (( try++ ))
    (( try <= attempts )) && { log "retry in $GAP_S s"; sleep $GAP_S; }
  done
  return $rc
}
watch_run() {  # a stall watcher on the run, detached, unless one is already on it; it ends by itself
  if pgrep -f "lms_campaign.py watch $1" > /dev/null; then log "watch $1 already running"; return; fi
  nohup "$PY" "$CAMP" watch "$1" >> "$OUT/watch-$1.out" 2>&1 &
  log "watch $1 started (pid $!)"
}
errors_in() {  # how many of the run's episodes ended in error
  "$PY" - "$OUT/$1/episodes" <<'PYEOF'
import glob, json, sys
n = 0
for f in glob.glob(sys.argv[1] + "/*.jsonl"):
    end = [r for r in (json.loads(l) for l in open(f) if l.strip()) if r.get("type") == "end"]
    n += bool(end) and end[-1].get("termination") == "error"
print(n)
PYEOF
}
night() {  # kind set: run, one error pass, report
  local kind=$1 set=$2
  local run_id=$(run_id_of $kind $set)
  wait_link                     # the PC first, so the stall watch starts beside a run that can start
  watch_run "$run_id"
  run_e3 $kind $set $ATTEMPTS
  local errs=$(errors_in "$run_id")
  if (( errs > 0 )); then
    log "$run_id: $errs episode(s) ended in error; setting them aside and resuming once"
    "$PY" "$CAMP" clear-errors "$run_id" --apply >> "$LOG" 2>&1
    watch_run "$run_id"
    run_e3 $kind $set 3
  fi
  PYTHONPATH="$WT/src" "$PY" -m roaddraft.eval report "$OUT/$run_id" >> "$LOG" 2>&1
  log "$run_id report written (not published)"
}
CHECK_ID=""          # e3-nothink-check-<label>-<suffix>, set with the checks below
nothink_holds() {  # one d1-dev episode with --thinking off, read for reasoning tokens; 0 when the server obeyed
  wait_link
  log "thinking-off check: one d1-dev episode as $CHECK_ID"
  local try=1
  while (( try <= 3 )); do
    wait_quiet 1
    "$PY" "$CAMP" e3 "$NOTHINK_MODEL" --taskset d1-dev --limit 1 --samples 1 --run-id "$CHECK_ID" \
      --worktree "$WT" --level vague --thinking off >> "$LOG" 2>&1 && break
    (( try++ )); sleep $GAP_S
  done
  "$PY" "$CAMP" thinking "$CHECK_ID" >> "$LOG" 2>&1
}

# ---------------------------------------------------------------- the checks before anything starts
[[ -x $PY ]] || refuse "no interpreter at $PY"
[[ -f $CAMP ]] || refuse "no lms_campaign.py in $WT (is it the pin worktree?)"
Q=$(label_of "$MODEL")
[[ -n $Q ]] || { refuse "no model $MODEL with a label in $WT/benchmarks/lmstudio/models.json"; Q=$MODEL; }
QN=$(label_of "$NOTHINK_MODEL")
[[ -n $QN ]] || { refuse "no model $NOTHINK_MODEL with a label in $WT/benchmarks/lmstudio/models.json"; QN=$NOTHINK_MODEL; }
CHECK_ID="e3-nothink-check-$QN-$SUFFIX"
head=$(git -C "$WT" rev-parse HEAD 2> /dev/null)
want=$(git -C "$WT" rev-parse --verify --quiet "refs/tags/$TAG^{commit}" 2> /dev/null)
if [[ -z $head ]]; then refuse "$WT is not a git worktree"
elif [[ -z $want ]]; then refuse "no tag $TAG"
elif [[ $head != $want ]]; then refuse "$WT is at ${head[1,8]}, not at $TAG (${want[1,8]})"
fi
dirty=$(git -C "$WT" status --porcelain -- src tests benchmarks 2> /dev/null)
[[ -z $dirty ]] || refuse "$WT has uncommitted changes in src, tests or benchmarks"
[[ -f "$WT/$SHEET" ]] || refuse "no $SHEET in $WT"
for flag in --system-extra --thinking; do
  grep -q -- "\"$flag\"" "$WT/src/roaddraft/eval/__main__.py" 2> /dev/null || refuse "the pin's harness has no $flag"
done
# another session writes results/e3-lms/queue-*.sh too: never over an existing name
if (( RESUME )); then   # a relaunch under its own name carries its log on; the stored script must be this one
  [[ ! -e "$OUT/$QUEUE_NAME.sh" ]] || cmp -s "$SELF" "$OUT/$QUEUE_NAME.sh" \
    || refuse "$OUT/$QUEUE_NAME.sh is another script than this one; give this relaunch another QUEUE_NAME"
else
  for f in "$OUT/$QUEUE_NAME.sh" "$LOG"; do
    test ! -e "$f" || refuse "$f exists already; give this queue another QUEUE_NAME (--resume starts a stopped queue again)"
  done
fi
# where each wanted run stands: a run that exists is carried on only with --resume, and only if this pin made it
typeset -A STATE DETAIL
for step in $STEPS; do
  kind=${step% *}; set=${step#* }
  wanted $kind $set || continue
  id=$(run_id_of $kind $set); st=$(state_of $id)
  STATE[$id]=${st%% *}; DETAIL[$id]=${st#* }
  case ${STATE[$id]} in
    new) ;;
    other) refuse "$id was not run at $TAG (${DETAIL[$id]}): it is not carried on; give this pin another SUFFIX" ;;
    partial|finished)
      (( RESUME )) || refuse "a run $id exists already (${DETAIL[$id]}); --resume carries it on, another SUFFIX starts anew" ;;
    *) refuse "the state of $id could not be read (lms_campaign.py run-state)" ;;
  esac
done
# the thinking-off check is run afresh by each launch: an earlier launch's episode is never the one judged
if [[ " $PHASES " == *" nothink "* && -e "$OUT/$CHECK_ID" ]]; then
  if (( RESUME )); then
    n=2; while [[ -e "$OUT/$CHECK_ID-r$n" ]]; do (( n++ )); done
    CHECK_ID="$CHECK_ID-r$n"
  else
    refuse "a check run $CHECK_ID exists already; give this pin another SUFFIX (--resume starts a stopped queue again)"
  fi
fi

# ---------------------------------------------------------------- the dry run: every command, nothing started
if (( DRY )); then
  echo "# dry run of $QUEUE_NAME: pin $WT at ${head[1,8]} (tag $TAG), phases '$PHASES', suffix $SUFFIX"
  echo "# a real run copies $SELF to $OUT/$QUEUE_NAME.sh and logs to $LOG"
  echo "# before the first run it waits for${AFTER:+ pid $AFTER to end, then for} the other local queue scripts alive at its start" \
       "(now: $(echo $(other_queues) | sed 's/^$/none/')) to end,"
  echo "#   then for $IDLE_POLLS looks in a row, $POLL_S s apart, with no local run; before each attempt it looks again"
  rc=0
  if [[ " $PHASES " == *" nothink "* ]]; then
    echo "# thinking-off check before the nothink runs:"
    "$PY" "$CAMP" e3 "$NOTHINK_MODEL" --taskset d1-dev --limit 1 --samples 1 --run-id "$CHECK_ID" \
      --worktree "$WT" --level vague --thinking off --print || rc=1
    echo "$PY $CAMP thinking $CHECK_ID"
  fi
  for step in $STEPS; do
    kind=${step% *}; set=${step#* }
    wanted $kind $set || continue
    args=("${(@f)$(e3_args $kind $set)}")
    id=$(run_id_of $kind $set)
    if [[ ${STATE[$id]:-new} == finished ]]; then
      echo "# $kind $set: $id is finished already (${DETAIL[$id]}): not run again"
      continue
    fi
    echo "# $kind $set$([[ ${STATE[$id]:-new} == partial ]] && echo " (resumes $id: ${DETAIL[$id]})")"
    "$PY" "$CAMP" e3 "$(model_of $kind)" "${args[@]}" --print || rc=1
    # the harness's own dry run: the command parses and the matrix builds; no model is asked
    "$PY" "$CAMP" e3 "$(model_of $kind)" "${args[@]}" --dry-run 2>&1 | grep -E "^run |thinking|system extra|error|usage" || rc=1
  done
  echo "# dry run done (exit $rc)"
  exit $rc
fi

# ---------------------------------------------------------------- the run
if [[ -z ${QUEUE_CAFFEINATED:-} ]]; then   # the Mac stays awake for the whole queue, its waits included
  export QUEUE_CAFFEINATED=1 QUEUE_NAME
  pass=(); [[ -n $AFTER ]] && pass+=(--after $AFTER); (( RESUME )) && pass+=(--resume)
  exec caffeinate -i zsh "$SELF" "$WT" "$TAG" $pass
fi
cd "$REPO" || exit 1
# what ran, beside its log, as the queues before it (a relaunch under the same name has it there already)
cmp -s "$SELF" "$OUT/$QUEUE_NAME.sh" || cp "$SELF" "$OUT/$QUEUE_NAME.sh" \
  || { echo "NOT run: could not store $SELF as $OUT/$QUEUE_NAME.sh" >&2; exit 1; }
log "$QUEUE_NAME (pid $$)$( (( RESUME )) && echo ', started again with --resume'): pin $WT at ${head[1,8]} (tag $TAG)," \
    "phases '$PHASES', suffix $SUFFIX, model $MODEL$([[ $NOTHINK_MODEL != $MODEL ]] && echo ", nothink model $NOTHINK_MODEL")"
if [[ -n $AFTER ]]; then
  log "waiting for pid $AFTER to end"
  wait_pid $AFTER
fi
others=($(other_queues))
if (( $#others )); then
  log "waiting for the other local queue script(s) alive at the start to end: pids $others"
  for p in $others; do wait_pid $p; done
fi
wait_quiet $IDLE_POLLS

nothink_ok=""
for step in $STEPS; do
  kind=${step% *}; set=${step#* }
  wanted $kind $set || continue
  id=$(run_id_of $kind $set)
  if [[ ${STATE[$id]:-new} == finished ]]; then
    log "$id is finished already (${DETAIL[$id]}): not run again"
    if [[ $kind == nothink && $nothink_ok != no ]]; then   # read as when it ended
      "$PY" "$CAMP" thinking "$id" >> "$LOG" 2>&1 \
        || { nothink_ok=no; log "$id did not pass the thinking read (the line above): the nothink sets left are not run"; }
    fi
    continue
  fi
  [[ ${STATE[$id]:-new} == partial ]] && log "$id is carried on (${DETAIL[$id]})"
  if [[ $kind == nothink ]]; then
    if [[ -z $nothink_ok ]]; then
      if nothink_holds; then nothink_ok=yes; log "thinking off holds on the check episode"
      else nothink_ok=no; log "NOT run: every nothink set. The check episode thought, ended in error or shows no output tokens (see above)"
      fi
    fi
    [[ $nothink_ok == yes ]] || continue
  fi
  night $kind $set
  if [[ $kind == nothink ]]; then
    "$PY" "$CAMP" thinking "$id" >> "$LOG" 2>&1 \
      || { nothink_ok=no; log "$id did not pass the thinking read (the line above): the nothink sets left are not run"; }
  fi
done
log "$QUEUE_NAME done. Nothing is published: read the reports, then from main"
log "  $PY -m roaddraft.eval report results/e3-lms/RUN --publish   and regenerate the board"

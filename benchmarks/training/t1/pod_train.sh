#!/usr/bin/env bash
# T1 training on the pod: the size check, then the run in the background under a time cap.
# Run from /workspace after pod_setup.sh printed SETUP OK.
#   bash benchmarks/training/t1/pod_train.sh            start
#   bash benchmarks/training/t1/pod_train.sh --resume   continue from the newest whole checkpoint
#   tail -f runs/t1.log                                 watch (one JSON row a step)
set -euo pipefail
cd /workspace
export HF_HUB_ENABLE_HF_TRANSFER=0

OUT=runs/t1
CAP=${T1_CAP:-19h}   # the trainer is stopped at this age whatever its state; the last checkpoint is the model
ARGS=(--data results/training --out "$OUT" --limit 3000
      --val-fraction 0.02 --val-max 24 --eval-steps 64 --save-steps 32
      --grad-accum 8 --epochs 1 --lr 1e-4 --workers 16)

# The numbers the Mac counted on 2026-11-20 for this selection (seed 3407, the dataset of 2026-11-18).
WANT_KEPT='"kept": 3064'
WANT_TOKENS='"tokens": 155993487'

mkdir -p runs
RESUME=()
if [ "${1:-}" = "--resume" ]; then
    LAST=$(ls -d "$OUT"/checkpoint-*/ 2>/dev/null | while read -r d; do
        [ -f "$d/trainer_state.pt" ] && echo "$d"; done | sort -t- -k2 -n | tail -1)
    [ -n "$LAST" ] || { echo "no whole checkpoint in $OUT"; exit 1; }
    RESUME=(--resume "${LAST%/}")
    echo "resuming from ${LAST%/}"
else
    python scripts/training_lora.py "${ARGS[@]}" --prepare-only 2>&1 | tee runs/t1-prepare.log
    grep -q "$WANT_KEPT" runs/t1-prepare.log && grep -q "$WANT_TOKENS" runs/t1-prepare.log || {
        echo "STOP: the selection is not the one counted on the Mac ($WANT_KEPT, $WANT_TOKENS)"; exit 1; }
fi

nohup timeout -s TERM "$CAP" python scripts/training_lora.py "${ARGS[@]}" "${RESUME[@]}" >> runs/t1.log 2>&1 &
echo $! > runs/t1.pid
echo "T1 started, pid $(cat runs/t1.pid), cap $CAP, 383 steps. Log: runs/t1.log, rows: $OUT/metrics.jsonl"

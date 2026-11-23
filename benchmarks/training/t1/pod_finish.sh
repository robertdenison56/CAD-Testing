#!/usr/bin/env bash
# T1 on the pod, after training: merge, quantize to Q4_K_M, check, and pack what goes home.
# Run from /workspace once runs/t1.log has stopped growing (the run ended, or the cap stopped it).
# Uses runs/t1/adapter when the run finished; otherwise the newest whole checkpoint.
set -euo pipefail
cd /workspace
export HF_HUB_ENABLE_HF_TRANSFER=0
OUT=runs/t1

if pgrep -f "training_lora.py" > /dev/null; then echo "the trainer is still running"; exit 1; fi

if [ -f "$OUT/adapter/adapter_model.safetensors" ]; then
    ADAPTER="$OUT/adapter"
else
    ADAPTER=$(ls -d "$OUT"/checkpoint-*/ 2>/dev/null | while read -r d; do
        [ -f "$d/trainer_state.pt" ] && echo "${d%/}"; done | sort -t- -k2 -n | tail -1)
    [ -n "$ADAPTER" ] || { echo "no adapter and no whole checkpoint in $OUT"; exit 1; }
    echo "the run did not finish: using $ADAPTER"
fi
echo "$ADAPTER" > "$OUT/merged-from.txt"

# Both are built for another torch and break `import peft` at the merge.
pip uninstall -y torchaudio torchao || true

python scripts/training_merge_quantize.py --adapter "$ADAPTER" --out "$OUT/gguf" \
    --llama-cpp /workspace/llama.cpp \
    --conversation results/training/d1-train-vague.jsonl D1-010000-fd165b673b09.vague 2>&1 | tee runs/t1-merge.log

python - <<'EOF'
import json
c = json.load(open("runs/t1/gguf/check.json"))
print(json.dumps({k: c[k] for k in c if k in ("verify_merge", "conversation_prompt_equal", "sha256", "bytes")}, indent=1)[:1200])
EOF

# The real file's embedded template against the training text: expect 0 issues.
llama.cpp/build/bin/llama-server -m "$OUT/gguf/model-Q4_K_M.gguf" -c 4096 --jinja --port 8099 > runs/t1-server.log 2>&1 &
SERVER=$!
sleep 45
python scripts/training_render_check.py results/training --server http://127.0.0.1:8099 \
    --serve-template nothink --thinking off --per-file 1 \
    --tokenizer tokenizer/tokenizer.json --template tokenizer/chat_template.jinja \
    --out runs/t1-render-check 2>&1 | tee runs/t1-render.log | tail -5
kill $SERVER || true

sha256sum "$OUT/gguf/model-Q4_K_M.gguf" | tee runs/t1-gguf.sha256
tar cf runs/t1-back.tar "$OUT/gguf/model-Q4_K_M.gguf" "$OUT/gguf/check.json" "$ADAPTER" "$OUT/merged-from.txt" \
    "$OUT/metrics.jsonl" "$OUT/run.json" "$OUT/prepared.json" \
    runs/t1.log runs/t1-prepare.log runs/t1-merge.log runs/t1-render.log runs/t1-gguf.sha256 runs/t1-render-check
ls -la runs/t1-back.tar
echo "FINISH OK: runpodctl send runs/t1-back.tar"

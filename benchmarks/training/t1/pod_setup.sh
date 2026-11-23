#!/usr/bin/env bash
# T1 pod setup: the T1 smoke's install (T1_SMOKE.md §5) with the changes §8 records, in one script.
# Run once on the pod, from /workspace, after `tar xzf t1-kit.tgz`. About 15 minutes.
# The versions are the ones the smoke's run.json recorded on 2026-11-18.
set -euo pipefail
cd /workspace

apt-get update -qq && apt-get install -y -qq cmake

# torch first, from the cu128 index: the image's nvcc is 12.8 and a bare install pulls a CUDA 13 torch.
pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
echo "torch==2.9.1" > /tmp/constraint.txt
pip install -c /tmp/constraint.txt unsloth==2026.11.6 transformers==5.17.0 peft==0.21.3 \
    flash-linear-attention==0.6.0 bitsandbytes==0.50.2 sentencepiece "protobuf<5"
pip install -c /tmp/constraint.txt --no-build-isolation causal-conv1d

# llama.cpp b12340, the build the Mac proved. Its requirements file is NOT installed (it pins a CPU torch).
if [ ! -d llama.cpp ]; then
    git clone --depth 1 --branch b12340 https://github.com/ggml-org/llama.cpp
fi
# llama-server's web UI bundle check fails on b12340: make it a warning.
sed -i '137s/FATAL_ERROR/WARNING/' llama.cpp/scripts/ui-assets.cmake
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON
cmake --build llama.cpp/build -j 32 --target llama-quantize llama-server

python - <<'EOF'
# unsloth first: a bare `import peft` fails here on the image's torchao (pod_finish.sh removes it for the merge).
import unsloth, torch, transformers
print("torch", torch.__version__, "cuda", torch.version.cuda, torch.cuda.get_device_name(0))
print("transformers", transformers.__version__, "unsloth", unsloth.__version__)
EOF
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
df -h /workspace | tail -1
echo "SETUP OK"

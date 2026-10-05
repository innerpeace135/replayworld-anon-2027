#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.5-397B-A17B}"

vllm serve "$MODEL" \
  --served-model-name "$MODEL" \
  --port 8000 \
  --tensor-parallel-size "${GPUS:-8}" \
  --max-model-len 131072 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml \
  "$@"

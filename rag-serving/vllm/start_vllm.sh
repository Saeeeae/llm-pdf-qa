#!/bin/bash
python -m vllm.entrypoints.openai.api_server \
    --model ${VLLM_MODEL_DIR:-/models/llm} \
    --served-model-name ${VLLM_MODEL_NAME:-qwen2.5-72b} \
    --tensor-parallel-size ${TP_SIZE:-1} \
    --quantization ${VLLM_QUANTIZATION:-awq} \
    --dtype bfloat16 \
    --gpu-memory-utilization ${VLLM_GPU_MEM_UTIL:-0.90} \
    --max-model-len ${VLLM_MAX_MODEL_LEN:-32768} \
    --host 0.0.0.0 \
    --port 8000

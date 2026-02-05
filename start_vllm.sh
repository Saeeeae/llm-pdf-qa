#!/bin/bash

# vLLM 서버 시작 스크립트
# Qwen2.5-20B-Instruct 모델을 OpenAI compatible API로 서빙

python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-20B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    --dtype auto

#!/bin/bash

echo "🚀 Starting PDF Q&A System for Linux GPU..."
echo ""
echo "Backend: vLLM (GPU)"
echo "Model: Qwen/Qwen2.5-20B-Instruct"
echo "GPU: NVIDIA L40s"
echo ""

# GPU 확인
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ Error: nvidia-smi not found. Please install NVIDIA drivers."
    exit 1
fi

echo "🔍 GPU Status:"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
echo ""

# Docker Compose 실행
docker-compose --profile linux up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

echo ""
echo "✅ Services started!"
echo ""
echo "📱 Streamlit UI: http://localhost:8501"
echo "🔧 vLLM API: http://localhost:8000"
echo ""
echo "💡 첫 실행시 모델 다운로드로 10-20분 소요될 수 있습니다."
echo ""
echo "📊 로그 확인: docker-compose logs -f"
echo "🛑 중지: docker-compose --profile linux down"

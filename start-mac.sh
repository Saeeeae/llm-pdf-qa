#!/bin/bash

echo "🍎 Starting PDF Q&A System for macOS M2..."
echo ""
echo "Backend: Ollama (CPU)"
echo "Model: qwen2.5:14b"
echo ""

# Docker Compose 실행
docker-compose --profile mac up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

echo ""
echo "✅ Services started!"
echo ""
echo "📱 Streamlit UI: http://localhost:8501"
echo "🔧 Ollama API: http://localhost:11434"
echo ""
echo "💡 첫 실행시 모델 다운로드로 5-10분 소요될 수 있습니다."
echo ""
echo "📊 로그 확인: docker-compose logs -f"
echo "🛑 중지: docker-compose --profile mac down"

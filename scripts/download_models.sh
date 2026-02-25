#!/bin/bash
# 모델 사전 다운로드 스크립트
# 호스트에서 한 번 실행하면 Docker 빌드 시 다운로드 불필요
#
# Usage:
#   ./scripts/download_models.sh              # 전체 다운로드
#   ./scripts/download_models.sh embedding    # 임베딩 모델만
#   ./scripts/download_models.sh mineru       # MinerU 모델만

set -e

# .env 파일에서 경로 로드 (없으면 기본값)
if [ -f .env ]; then
    source .env
fi

EMBEDDING_MODEL_DIR="${EMBEDDING_MODEL_DIR:-/data/models/embedding}"
MINERU_MODEL_DIR="${MINERU_MODEL_DIR:-/data/models/mineru}"
LLM_MODEL_DIR="${LLM_MODEL_DIR:-/data/models/llm}"
VLM_MODEL_DIR="${VLM_MODEL_DIR:-/data/models/vlm}"
EMBED_MODEL="${EMBED_MODEL:-intfloat/multilingual-e5-large}"

TARGET="${1:-all}"

download_embedding() {
    echo "=== Downloading embedding model: ${EMBED_MODEL} ==="
    mkdir -p "${EMBEDDING_MODEL_DIR}"

    # huggingface-cli가 있으면 사용, 없으면 pip install
    if ! command -v huggingface-cli &> /dev/null; then
        echo "Installing huggingface-cli..."
        pip install -q huggingface_hub[cli]
    fi

    huggingface-cli download "${EMBED_MODEL}" \
        --local-dir "${EMBEDDING_MODEL_DIR}" \
        --local-dir-use-symlinks False

    echo "Embedding model saved to: ${EMBEDDING_MODEL_DIR}"
}

download_mineru() {
    echo "=== Downloading MinerU models ==="
    mkdir -p "${MINERU_MODEL_DIR}"

    if ! command -v huggingface-cli &> /dev/null; then
        echo "Installing huggingface-cli..."
        pip install -q huggingface_hub[cli]
    fi

    # MinerU 2.5 VLM model (1.2B)
    echo "Downloading MinerU 2.5 model..."
    huggingface-cli download opendatalab/MinerU2.5-2509-1.2B \
        --local-dir "${MINERU_MODEL_DIR}/MinerU2.5-2509-1.2B" \
        --local-dir-use-symlinks False

    echo "MinerU models saved to: ${MINERU_MODEL_DIR}"
}

init_dirs() {
    echo "=== Creating directory structure ==="
    mkdir -p /data/db/postgres
    mkdir -p /data/db/redis
    mkdir -p /data/documents
    mkdir -p "${EMBEDDING_MODEL_DIR}"
    mkdir -p "${MINERU_MODEL_DIR}"
    mkdir -p "${LLM_MODEL_DIR}"
    mkdir -p "${VLM_MODEL_DIR}"
    echo "Directory structure created under /data/"
}

case "${TARGET}" in
    embedding)
        download_embedding
        ;;
    mineru)
        download_mineru
        ;;
    all)
        init_dirs
        download_embedding
        download_mineru
        ;;
    init)
        init_dirs
        ;;
    *)
        echo "Usage: $0 {all|embedding|mineru|init}"
        echo ""
        echo "  all       - 디렉토리 생성 + 전체 모델 다운로드"
        echo "  embedding - 임베딩 모델만 다운로드"
        echo "  mineru    - MinerU 모델만 다운로드"
        echo "  init      - 디렉토리 구조만 생성"
        exit 1
        ;;
esac

echo ""
echo "=== Done ==="

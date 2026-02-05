# PDF Q&A System with vLLM

PDF 문서에 대해 질의응답을 할 수 있는 시스템입니다.
- **vLLM**: GPU 가속 추론 엔진
- **Model**: Qwen2.5-20B-Instruct (로컬 weight 사용)

## 시스템 요구사항

- Docker & Docker Compose
- NVIDIA GPU (L40s 또는 40GB+ VRAM)
- NVIDIA Driver 535 이상
- CUDA 12.1 이상
- nvidia-docker2

## 설치

### 1. NVIDIA Docker 런타임 설치

#### Ubuntu 24.04
```bash
# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# NVIDIA Container Toolkit 설치
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# 설치 확인
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 2. 프로젝트 실행

```bash
# 프로젝트 디렉토리로 이동
cd /path/to/llm_again

# 실행
bash start.sh

# 또는 직접 docker-compose 사용
docker-compose up -d
```

## 모델 다운로드

### 방법 1: 자동 다운로드 (권장)
첫 실행시 자동으로 HuggingFace에서 모델을 다운로드합니다.

```bash
docker-compose up -d
docker-compose logs -f vllm  # 다운로드 진행 상황 확인
```

### 방법 2: 수동 다운로드
모델을 미리 다운로드하려면:

```bash
# Python 환경에서
pip install huggingface-hub

# 모델 다운로드
python -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen2.5-20B-Instruct', cache_dir='~/.cache/huggingface')
"
```

### 방법 3: 로컬 모델 사용
이미 다운로드된 모델이 있다면:

```bash
# 모델을 ./models 디렉토리에 복사
mkdir -p ./models
cp -r /path/to/your/model ./models/Qwen2.5-20B-Instruct

# docker-compose.yml에서 MODEL_NAME 수정
environment:
  - MODEL_NAME=/app/models/Qwen2.5-20B-Instruct
```

## 사용 방법

1. **서비스 시작 후 브라우저에서 접속**
   - Streamlit UI: http://localhost:8501

2. **PDF 업로드**
   - 왼쪽 사이드바에서 PDF 파일 선택

3. **설정 조정 (선택사항)**
   - 청크 크기: 500-2000 (기본값: 1000)
   - 청크 오버랩: 0-500 (기본값: 200)

4. **질문하기**
   - 질문 입력창에 질문 작성
   - "질문하기" 버튼 클릭
   - AI가 스트리밍으로 답변 생성

## API 엔드포인트

### vLLM API
- Base URL: http://localhost:8000
- OpenAI Compatible: http://localhost:8000/v1

### API 호출 예시

```bash
# Health Check
curl http://localhost:8000/health

# 모델 목록
curl http://localhost:8000/v1/models

# Chat Completion
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-20B-Instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "stream": true
  }'
```

## 모델 변경

다른 모델을 사용하려면 `docker-compose.yml` 수정:

```yaml
environment:
  - MODEL_NAME=meta-llama/Llama-3.1-70B-Instruct  # 예시
```

사용 가능한 모델:
- `Qwen/Qwen2.5-20B-Instruct` (20B, 권장)
- `Qwen/Qwen2.5-14B-Instruct` (14B, 더 빠름)
- `meta-llama/Llama-3.1-70B-Instruct` (70B, 더 큰 GPU 필요)
- `deepseek-ai/DeepSeek-V2-Lite` (16B)

## 트러블슈팅

### GPU 메모리 부족

```yaml
# docker-compose.yml 또는 Dockerfile.vllm 수정
--gpu-memory-utilization 0.9 → 0.7  # GPU 메모리 사용량 감소
--max-model-len 4096 → 2048  # 최대 시퀀스 길이 감소
```

또는 더 작은 모델 사용:
```yaml
environment:
  - MODEL_NAME=Qwen/Qwen2.5-14B-Instruct
```

### vLLM 서버 시작 실패

```bash
# GPU 상태 확인
nvidia-smi

# Docker GPU 접근 확인
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 로그 확인
docker-compose logs vllm
```

### 모델 다운로드 오류

HuggingFace 토큰이 필요한 경우:

```bash
# .env 파일 생성
echo "HF_TOKEN=your_huggingface_token" > .env

# docker-compose.yml에 환경변수 추가
environment:
  - HF_TOKEN=${HF_TOKEN}
```

### CUDA 버전 문제

```bash
# CUDA 버전 확인
nvidia-smi

# 12.1 미만인 경우 드라이버 업데이트
sudo apt-get update
sudo apt-get install -y nvidia-driver-535
sudo reboot
```

### 포트 충돌

```yaml
# docker-compose.yml에서 포트 변경
ports:
  - "8501:8501"  → "8502:8501"  # Streamlit
  - "8000:8000"  → "8001:8000"  # vLLM
```

### 서버 연결 실패

```bash
# 서비스 상태 확인
docker-compose ps

# 재시작
docker-compose restart

# 완전 재시작
docker-compose down
docker-compose up -d
```

## 성능 최적화

### Tensor Parallelism (다중 GPU)

2개 이상의 GPU를 사용하는 경우:

```yaml
# docker-compose.yml 수정
environment:
  - CUDA_VISIBLE_DEVICES=0,1  # 사용할 GPU 지정

# Dockerfile.vllm 수정
--tensor-parallel-size 1 → 2  # GPU 개수에 맞게
```

### 배치 처리 최적화

많은 요청을 처리할 때:

```dockerfile
# Dockerfile.vllm의 CMD에 추가
--max-num-batched-tokens 8192 \
--max-num-seqs 256 \
--enable-chunked-prefill
```

### Quantization (양자화)

메모리를 절약하려면:

```dockerfile
# Dockerfile.vllm의 CMD에 추가
--quantization awq  # 또는 gptq
--dtype half
```

## 파일 구조

```
.
├── docker-compose.yml          # Docker Compose 설정
├── Dockerfile.vllm            # vLLM 서버 이미지
├── Dockerfile.streamlit       # Streamlit UI 이미지
├── streamlit_app.py           # Streamlit 애플리케이션
├── download_model.py          # 모델 다운로드 스크립트
├── requirements.txt           # Python 의존성
├── start.sh                   # 시작 스크립트
├── .dockerignore             # Docker 빌드시 제외할 파일
├── .env.example              # 환경변수 예시
└── README.md                 # 이 파일
```

## 개발 모드

### 코드 수정 후 재시작

```bash
# Streamlit만 재빌드
docker-compose build streamlit
docker-compose up -d streamlit

# vLLM 서버만 재빌드
docker-compose build vllm
docker-compose up -d vllm

# 전체 재빌드
docker-compose build
docker-compose up -d
```

### 로컬에서 개발

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# Streamlit 실행 (vLLM 서버는 Docker로 실행)
export BACKEND=vllm
export VLLM_API_BASE=http://localhost:8000/v1
streamlit run streamlit_app.py
```

## 모니터링

### GPU 사용량 모니터링

```bash
# 실시간 GPU 상태
watch -n 1 nvidia-smi

# 컨테이너 내부에서
docker exec -it vllm-server nvidia-smi
```

### vLLM 메트릭

vLLM은 기본적으로 메트릭을 제공합니다:

```bash
# Prometheus 메트릭
curl http://localhost:8000/metrics
```

## 라이센스

MIT License

## 참고

- vLLM: https://github.com/vllm-project/vllm
- Qwen2.5: https://huggingface.co/Qwen/Qwen2.5-20B-Instruct
- Streamlit: https://streamlit.io/
